import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_companion import autostart


class AutostartRegistrationTest(unittest.TestCase):
    def test_windows_registration_writes_startup_vbs(self):
        with tempfile.TemporaryDirectory(prefix="autostart-win-") as td:
            appdata = Path(td) / "AppData" / "Roaming"
            app_home = Path(td) / "home"
            python = Path(td) / "Python Dir" / "python.exe"

            with patch.dict("os.environ", {"APPDATA": str(appdata)}):
                result = autostart.register_gateway_autostart(
                    python_executable=str(python),
                    app_home=app_home,
                    platform="win32",
                )

            self.assertTrue(result.ok)
            self.assertEqual(result.method, "windows-startup")
            self.assertIsNotNone(result.path)
            self.assertTrue(result.path.exists())

            content = result.path.read_text(encoding="utf-8")
            self.assertIn("ai_companion.gateway", content)
            self.assertIn("--daemon", content)
            self.assertIn("python.exe", content)

    def test_launch_agent_registration_writes_plist(self):
        with tempfile.TemporaryDirectory(prefix="autostart-mac-") as td:
            home = Path(td) / "user"
            app_home = Path(td) / "app-home"
            python = Path(td) / "venv" / "bin" / "python"

            with patch.object(Path, "home", return_value=home):
                result = autostart.register_gateway_autostart(
                    python_executable=str(python),
                    app_home=app_home,
                    platform="darwin",
                )

            self.assertTrue(result.ok)
            self.assertEqual(result.method, "launchd")
            self.assertIsNotNone(result.path)
            with result.path.open("rb") as handle:
                payload = plistlib.load(handle)
            self.assertEqual(payload["Label"], autostart.LAUNCHD_LABEL)
            self.assertEqual(payload["ProgramArguments"], [str(python.resolve()), "-m", "ai_companion.gateway", "--daemon"])
            self.assertTrue(payload["RunAtLoad"])
            self.assertTrue(payload["KeepAlive"])

    def test_linux_registration_writes_systemd_user_service(self):
        with tempfile.TemporaryDirectory(prefix="autostart-linux-") as td:
            home = Path(td) / "user"
            app_home = Path(td) / "app-home"
            python = Path(td) / "venv" / "bin" / "python"

            with patch.object(Path, "home", return_value=home):
                result = autostart.register_gateway_autostart(
                    python_executable=str(python),
                    app_home=app_home,
                    platform="linux",
                    activate=False,
                )

            self.assertTrue(result.ok)
            self.assertEqual(result.method, "systemd-user")
            self.assertIsNotNone(result.path)
            content = result.path.read_text(encoding="utf-8")
            self.assertIn("ExecStart=/bin/sh -lc", content)
            self.assertIn("ai_companion.gateway", content)
            self.assertIn("--daemon", content)
            self.assertIn("WantedBy=default.target", content)


if __name__ == "__main__":
    unittest.main()
