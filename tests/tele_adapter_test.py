import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp import web

from ai_companion.model.adapters import tele_adapter
from ai_companion.model.adapters.tele_adapter import TeleAdapter, default_auth_state_file


class TeleAuthStatePathTest(unittest.TestCase):
    def test_env_override_wins(self):
        with patch.dict("os.environ", {"TELECLAW_AUTH_STATE_FILE": "/tmp/tele/state.json"}, clear=True):
            self.assertEqual(default_auth_state_file(), Path("/tmp/tele/state.json"))

    def test_windows_appdata_path(self):
        with (
            patch("sys.platform", "win32"),
            patch.dict("os.environ", {"APPDATA": r"C:\Users\alice\AppData\Roaming"}, clear=True),
            patch.object(tele_adapter, "PROJECT_AUTH_STATE_FILE", Path("/tmp/missing-tele-state.json")),
        ):
            self.assertEqual(
                default_auth_state_file(),
                Path(r"C:\Users\alice\AppData\Roaming") / "TeleClaw" / "app-auth" / "state.json",
            )

    def test_macos_application_support_path(self):
        with (
            patch("sys.platform", "darwin"),
            patch.dict("os.environ", {}, clear=True),
            patch("pathlib.Path.home", return_value=Path("/Users/alice")),
            patch.object(tele_adapter, "PROJECT_AUTH_STATE_FILE", Path("/tmp/missing-tele-state.json")),
        ):
            self.assertEqual(
                default_auth_state_file(),
                Path("/Users/alice/Library/Application Support/TeleClaw/app-auth/state.json"),
            )

    def test_linux_xdg_config_path(self):
        with (
            patch("sys.platform", "linux"),
            patch.dict("os.environ", {"XDG_CONFIG_HOME": "/home/alice/.config"}, clear=True),
            patch.object(tele_adapter, "PROJECT_AUTH_STATE_FILE", Path("/tmp/missing-tele-state.json")),
        ):
            self.assertEqual(
                default_auth_state_file(),
                Path("/home/alice/.config/TeleClaw/app-auth/state.json"),
            )

    def test_project_local_fallback_is_used_when_system_state_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            local_state = Path(tmp) / ".local" / "teleclaw" / "state.json"
            with (
                patch("sys.platform", "linux"),
                patch.dict("os.environ", {"XDG_CONFIG_HOME": str(Path(tmp) / "missing-config")}, clear=True),
                patch.object(tele_adapter, "PROJECT_AUTH_STATE_FILE", local_state),
            ):
                self.assertEqual(default_auth_state_file(), Path(tmp) / "missing-config" / "TeleClaw" / "app-auth" / "state.json")
                local_state.parent.mkdir(parents=True)
                local_state.write_text("{}", encoding="utf-8")
                self.assertEqual(default_auth_state_file(), local_state)


class TeleAdapterRequestContractTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state_file = Path(self._tmp.name) / "state.json"
        self.state_file.write_text(
            json.dumps(
                {
                    "token": "login-token",
                    "deviceId": "device-id",
                    "installId": "install-id",
                }
            ),
            encoding="utf-8",
        )
        self.seen = {}

        async def handle_chat(request):
            self.seen["path"] = request.path
            self.seen["headers"] = dict(request.headers)
            self.seen["body"] = await request.json()
            return web.json_response({
                "choices": [
                    {"message": {"content": "tele-ok", "reasoning_content": "hidden"}}
                ]
            })

        app = web.Application()
        app.router.add_post("/v1/chat/completions", handle_chat)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await self.site.start()
        sockets = self.site._server.sockets if self.site._server else []
        self.port = sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        await self.runner.cleanup()
        self._tmp.cleanup()

    async def test_chat_sends_teleclaw_auth_headers(self):
        adapter = TeleAdapter(
            api_key="test-key",
            base_url=f"http://127.0.0.1:{self.port}/v1",
            model="ignored-model",
            auth_state_file=str(self.state_file),
        )
        try:
            response = await adapter.chat(
                [{"role": "user", "content": "hello"}],
                system_prompt="sys",
                temperature=0.5,
                max_tokens=123,
            )
        finally:
            await adapter.close()

        self.assertEqual(response, "tele-ok")
        self.assertEqual(self.seen["path"], "/v1/chat/completions")
        self.assertEqual(self.seen["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(self.seen["headers"]["X-Token"], "login-token")
        self.assertTrue(self.seen["headers"]["X-SuperAgent-Timestamp"].isdigit())
        self.assertTrue(self.seen["headers"]["X-SuperAgent-Nonce"])
        self.assertEqual(self.seen["headers"]["X-SuperAgent-Device-Id"], "device-id")
        self.assertEqual(self.seen["headers"]["X-SuperAgent-Install-Id"], "install-id")
        self.assertEqual(self.seen["body"]["model"], "glm-5-turbo")
        self.assertEqual(self.seen["body"]["max_tokens"], 123)
        self.assertEqual(self.seen["body"]["messages"][0], {"role": "system", "content": "sys"})
        self.assertEqual(self.seen["body"]["messages"][1], {"role": "user", "content": "hello"})

    async def test_api_key_is_optional_when_login_state_is_available(self):
        adapter = TeleAdapter(
            base_url=f"http://127.0.0.1:{self.port}/v1",
            auth_state_file=str(self.state_file),
        )
        try:
            response = await adapter.chat([{"role": "user", "content": "hello"}])
        finally:
            await adapter.close()

        self.assertEqual(response, "tele-ok")
        self.assertNotIn("Authorization", self.seen["headers"])
        self.assertEqual(self.seen["headers"]["X-Token"], "login-token")
        self.assertTrue(self.seen["headers"]["X-SuperAgent-Timestamp"].isdigit())
        self.assertTrue(self.seen["headers"]["X-SuperAgent-Nonce"])

    async def test_missing_login_state_reports_actionable_error(self):
        adapter = TeleAdapter(
            api_key="test-key",
            base_url=f"http://127.0.0.1:{self.port}/v1",
            auth_state_file=str(Path(self._tmp.name) / "missing.json"),
        )
        try:
            with self.assertRaisesRegex(RuntimeError, "请先登录 TeleClaw"):
                await adapter.chat([{"role": "user", "content": "hello"}])
        finally:
            await adapter.close()


if __name__ == "__main__":
    unittest.main()
