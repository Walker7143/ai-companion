import asyncio
import base64
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ai_companion.gateway.config import PlatformConfig
from ai_companion.gateway.platforms.weixin import (
    ITEM_FILE,
    ITEM_IMAGE,
    ITEM_VIDEO,
    ITEM_VOICE,
    MEDIA_FILE,
    MEDIA_IMAGE,
    MEDIA_VIDEO,
    WeixinAdapter,
    _mask_secret_for_log,
    _parse_aes_key,
    _split_text_for_weixin_delivery,
)
from ai_companion.bot.instance import BotInstance
from ai_companion.gateway.platforms.base import SendResult
from ai_companion.gateway.config import Platform
from ai_companion.gateway.session import SessionSource


class WeixinGatewayTest(unittest.IsolatedAsyncioTestCase):
    async def test_weixin_adapter_smoke_connect_send_process_disconnect(self):
        sent = []
        events = []

        async def fake_get_updates(*args, **kwargs):
            await asyncio.sleep(0.05)
            return {
                "ret": 0,
                "msgs": [],
                "get_updates_buf": kwargs.get("sync_buf", ""),
            }

        async def fake_send_message(session, *, to, text, context_token, client_id, **kwargs):
            sent.append(
                {
                    "to": to,
                    "text": text,
                    "context_token": context_token,
                    "client_id": client_id,
                }
            )
            return {"ret": 0}

        adapter = WeixinAdapter(
            PlatformConfig(
                enabled=True,
                token="token-1",
                extra={
                    "account_id": "wxbot",
                    "base_url": "https://example.invalid",
                    "dm_policy": "allowlist",
                    "allow_from": ["user-1"],
                    "group_policy": "disabled",
                    "send_chunk_delay_seconds": 0,
                    "send_chunk_retries": 0,
                },
            )
        )

        async def capture_event(event):
            events.append(event)

        async def noop_typing(*args, **kwargs):
            return None

        adapter.handle_message = capture_event
        adapter._maybe_fetch_typing_ticket = noop_typing

        with patch("ai_companion.gateway.platforms.weixin.check_weixin_requirements", return_value=True), patch(
            "ai_companion.gateway.platforms.weixin._get_updates", fake_get_updates
        ), patch(
            "ai_companion.gateway.platforms.weixin._send_message", fake_send_message
        ):
            connected = await adapter.connect()
            self.assertTrue(connected)

            adapter._token_store.set("wxbot", "user-1", "ctx-1")
            result = await adapter.send("user-1", "你好\n\n第二段")
            self.assertTrue(result.success)
            self.assertEqual(sent[0]["to"], "user-1")
            self.assertEqual(sent[0]["context_token"], "ctx-1")

            await adapter._process_message(
                {
                    "message_id": "msg-1",
                    "from_user_id": "user-1",
                    "to_user_id": "wxbot",
                    "context_token": "ctx-2",
                    "item_list": [{"type": 1, "text_item": {"text": "/status"}}],
                }
            )
            await adapter._process_message(
                {
                    "message_id": "msg-1",
                    "from_user_id": "user-1",
                    "to_user_id": "wxbot",
                    "context_token": "ctx-2",
                    "item_list": [{"type": 1, "text_item": {"text": "duplicate"}}],
                }
            )

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].text, "/status")
            self.assertEqual(events[0].source.platform.value, "weixin")
            self.assertEqual(events[0].source.chat_id, "user-1")
            self.assertEqual(adapter._token_store.get("wxbot", "user-1"), "ctx-2")

            await adapter.disconnect()
            self.assertFalse(adapter.is_connected)

    async def test_weixin_send_retries_without_expired_context_token(self):
        sent_contexts = []

        async def fake_send_message(session, *, context_token, **kwargs):
            sent_contexts.append(context_token)
            if context_token:
                return {"errcode": -14, "errmsg": "session expired"}
            return {"ret": 0}

        adapter = WeixinAdapter(
            PlatformConfig(
                enabled=True,
                token="token-1",
                extra={
                    "account_id": "wxbot",
                    "send_chunk_retries": 0,
                    "send_chunk_retry_delay_seconds": 0,
                },
            )
        )
        adapter._send_session = object()
        adapter._token_store.set("wxbot", "user-1", "ctx-old")

        with patch("ai_companion.gateway.platforms.weixin._send_message", fake_send_message):
            result = await adapter.send("user-1", "hello")

        self.assertTrue(result.success)
        self.assertEqual(sent_contexts, ["ctx-old", None])
        self.assertIsNone(adapter._token_store.get("wxbot", "user-1"))

    async def test_bot_wrap_gateway_send_uses_weixin_home_channel(self):
        class FakeAdapter:
            async def send(self, chat_id, content):
                self.chat_id = chat_id
                self.content = content
                return SendResult(success=True, message_id="m1")

        bot = BotInstance(
            {
                "id": "wxbot",
                "name": "微信 Bot",
            },
            model=SimpleNamespace(provider="test", model="test"),
            refusal_enabled=False,
        )
        bot.proactive_config = SimpleNamespace(
            to_dict=lambda: {
                "platform": {
                    "type": "weixin",
                    "home_channel": "wx-user-1",
                }
            }
        )
        adapter = FakeAdapter()

        ok = await bot._wrap_gateway_send("主动消息", adapter, "weixin")

        self.assertTrue(ok)
        self.assertEqual(adapter.chat_id, "wx-user-1")
        self.assertEqual(adapter.content, "主动消息")

    async def test_weixin_group_policy_disabled_allowlist_and_open(self):
        base_config = {
            "account_id": "wxbot",
            "dm_policy": "disabled",
            "group_policy": "disabled",
            "group_allow_from": ["room-allowed"],
        }
        message = {
            "message_id": "group-msg-1",
            "from_user_id": "user-1",
            "to_user_id": "room-allowed",
            "room_id": "room-allowed",
            "msg_type": 1,
            "item_list": [{"type": 1, "text_item": {"text": "hello group"}}],
        }
        events = []

        async def capture_event(event):
            events.append(event)

        async def noop_typing(*args, **kwargs):
            return None

        adapter = WeixinAdapter(PlatformConfig(enabled=True, token="token-1", extra=base_config))
        adapter._poll_session = object()
        adapter.handle_message = capture_event
        adapter._maybe_fetch_typing_ticket = noop_typing

        await adapter._process_message(dict(message))
        self.assertEqual(events, [])

        adapter = WeixinAdapter(
            PlatformConfig(
                enabled=True,
                token="token-1",
                extra={**base_config, "group_policy": "allowlist"},
            )
        )
        adapter._poll_session = object()
        adapter.handle_message = capture_event
        adapter._maybe_fetch_typing_ticket = noop_typing
        await adapter._process_message({**message, "message_id": "group-msg-2"})
        self.assertEqual(len(events), 1)
        self.assertEqual(events[-1].source.chat_type, "group")
        self.assertEqual(events[-1].source.chat_id, "room-allowed")

        adapter = WeixinAdapter(
            PlatformConfig(
                enabled=True,
                token="token-1",
                extra={**base_config, "group_policy": "open", "group_allow_from": []},
            )
        )
        adapter._poll_session = object()
        adapter.handle_message = capture_event
        adapter._maybe_fetch_typing_ticket = noop_typing
        await adapter._process_message({**message, "message_id": "group-msg-3", "room_id": "room-open", "to_user_id": "room-open"})
        self.assertEqual(len(events), 2)
        self.assertEqual(events[-1].source.chat_id, "room-open")

    async def test_weixin_inbound_media_paths_for_image_file_voice_video(self):
        events = []

        async def capture_event(event):
            events.append(event)

        async def noop_typing(*args, **kwargs):
            return None

        async def fake_download_and_decrypt_media(*args, **kwargs):
            return b"\xff\xd8\xff\xe0image-bytes"

        fake_paths = {
            "image": "/tmp/wx-image.jpg",
            "doc": "/tmp/wx-doc.txt",
            "audio": "/tmp/wx-audio.silk",
        }
        adapter = WeixinAdapter(
            PlatformConfig(
                enabled=True,
                token="token-1",
                extra={
                    "account_id": "wxbot",
                    "dm_policy": "allowlist",
                    "allow_from": ["user-1"],
                },
            )
        )
        adapter._poll_session = object()
        adapter.handle_message = capture_event
        adapter._maybe_fetch_typing_ticket = noop_typing

        item_list = [
            {"type": ITEM_IMAGE, "image_item": {"media": {"full_url": "https://novac2c.cdn.weixin.qq.com/image.jpg"}}},
            {
                "type": ITEM_FILE,
                "file_item": {
                    "file_name": "report.txt",
                    "media": {"full_url": "https://novac2c.cdn.weixin.qq.com/report.txt"},
                },
            },
            {"type": ITEM_VOICE, "voice_item": {"media": {"full_url": "https://novac2c.cdn.weixin.qq.com/audio.silk"}}},
            {"type": ITEM_VIDEO, "video_item": {"media": {"full_url": "https://novac2c.cdn.weixin.qq.com/video.mp4"}}},
        ]

        with patch(
            "ai_companion.gateway.platforms.weixin._download_and_decrypt_media",
            fake_download_and_decrypt_media,
        ), patch(
            "ai_companion.gateway.platforms.weixin.cache_image_from_bytes",
            return_value=fake_paths["image"],
        ), patch(
            "ai_companion.gateway.platforms.weixin.cache_document_from_bytes",
            side_effect=[fake_paths["doc"], "/tmp/wx-video.mp4"],
        ), patch(
            "ai_companion.gateway.platforms.weixin.cache_audio_from_bytes",
            return_value=fake_paths["audio"],
        ):
            await adapter._process_message(
                {
                    "message_id": "media-msg-1",
                    "from_user_id": "user-1",
                    "to_user_id": "wxbot",
                    "item_list": item_list,
                }
            )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].message_type.value, "photo")
        self.assertEqual(events[0].media_urls, ["/tmp/wx-image.jpg", "/tmp/wx-doc.txt", "/tmp/wx-audio.silk", "/tmp/wx-video.mp4"])
        self.assertEqual(events[0].media_types, ["image/jpeg", "text/plain", "audio/silk", "video/mp4"])

    async def test_weixin_outbound_media_builders_for_image_file_voice_video(self):
        sent_media_types = []

        async def fake_get_upload_url(session, *, media_type, **kwargs):
            sent_media_types.append(media_type)
            return {"upload_full_url": "https://novac2c.cdn.weixin.qq.com/upload"}

        async def fake_upload_ciphertext(session, *, ciphertext, upload_url):
            self.assertTrue(ciphertext)
            return "encrypted-param"

        async def fake_api_post(session, *, payload, **kwargs):
            self.assertIn("msg", payload)
            return {"ret": 0}

        adapter = WeixinAdapter(
            PlatformConfig(
                enabled=True,
                token="token-1",
                extra={"account_id": "wxbot"},
            )
        )
        adapter._send_session = object()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            image = tmp / "image.jpg"
            document = tmp / "report.txt"
            voice = tmp / "voice.silk"
            video = tmp / "clip.mp4"
            for path in (image, document, voice, video):
                path.write_bytes(b"sample-bytes")

            with patch("ai_companion.gateway.platforms.weixin._get_upload_url", fake_get_upload_url), patch(
                "ai_companion.gateway.platforms.weixin._aes128_ecb_encrypt",
                return_value=b"ciphertext",
            ), patch(
                "ai_companion.gateway.platforms.weixin._upload_ciphertext", fake_upload_ciphertext
            ), patch("ai_companion.gateway.platforms.weixin._api_post", fake_api_post):
                self.assertTrue((await adapter.send_image_file("user-1", str(image))).success)
                self.assertTrue((await adapter.send_document("user-1", str(document))).success)
                self.assertTrue((await adapter.send_voice("user-1", str(voice))).success)
                self.assertTrue((await adapter.send_video("user-1", str(video))).success)

        self.assertEqual(sent_media_types, [MEDIA_IMAGE, MEDIA_FILE, MEDIA_FILE, MEDIA_VIDEO])

    def test_weixin_aes_key_compat_and_log_masking(self):
        key = b"0123456789abcdef"
        key_hex = key.hex()
        self.assertEqual(_parse_aes_key(base64.b64encode(key).decode("ascii")), key)
        self.assertEqual(_parse_aes_key(base64.b64encode(key_hex.encode("ascii")).decode("ascii")), key)

        masked = _mask_secret_for_log("wxbot-account-id-123456")
        self.assertNotIn("account-id-123456", masked)
        self.assertIn("...", masked)

    def test_gateway_runtime_status_redacts_weixin_sensitive_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(os.environ, {"AI_COMPANION_HOME": tmpdir}, clear=False):
            from ai_companion.gateway.status import read_runtime_status, write_runtime_status

            write_runtime_status(
                platform="weixin",
                platform_state="connected",
                platform_details={
                    "account_id": "wxbot-account-id-123456",
                    "token": "token-secret",
                    "context_token": "ctx-secret",
                },
            )
            payload = read_runtime_status()

        weixin = payload["platforms"]["weixin"]
        self.assertEqual(weixin["account_id"], "***")
        self.assertEqual(weixin["token"], "***")
        self.assertEqual(weixin["context_token"], "***")
        self.assertTrue(weixin["account_id_hint"].startswith("wxbot-ac"))

    def test_weixin_text_splitting_compact_and_per_line_modes(self):
        structured = "【标题】\n\n第一段\n\n第二段"
        compact = _split_text_for_weixin_delivery(structured, 4000, split_per_line=False)
        per_line = _split_text_for_weixin_delivery(structured, 4000, split_per_line=True)

        self.assertEqual(compact, [structured])
        self.assertEqual(per_line, ["【标题】", "第一段", "第二段"])


class WeixinGatewayConfigTest(unittest.TestCase):
    def test_build_weixin_adapter_profile_requires_one_bot_and_preserves_env_fallbacks(self):
        from ai_companion.gateway.cmd import _build_weixin_adapter_profiles

        with patch.dict(
            os.environ,
            {
                "WEIXIN_BOT_ID": "envbot",
                "WEIXIN_ACCOUNT_ID": "env-account",
                "WEIXIN_TOKEN": "env-token",
            },
            clear=False,
        ):
            profiles = _build_weixin_adapter_profiles(
                {
                    "enabled": True,
                    "extra": {"dm_policy": "allowlist", "allow_from": ["user-1"]},
                }
            )

        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["bot_id"], "envbot")
        self.assertEqual(profiles[0]["extra"]["dm_policy"], "allowlist")
        self.assertEqual(profiles[0]["routing"], {"mode": "dedicated", "bot_id": "envbot"})

    def test_build_weixin_adapter_profile_rejects_unbound_config(self):
        from ai_companion.gateway.cmd import _build_weixin_adapter_profiles

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "未绑定 Bot"):
                _build_weixin_adapter_profiles(
                    {
                        "enabled": True,
                        "token": "token-1",
                        "extra": {"account_id": "account-1"},
                    }
                )

    def test_gateway_profile_builders_allow_feishu_and_weixin_side_by_side(self):
        from ai_companion.gateway.cmd import (
            _build_feishu_adapter_profiles,
            _build_weixin_adapter_profiles,
        )

        feishu_profiles = _build_feishu_adapter_profiles(
            {
                "enabled": True,
                "bot_bindings": {
                    "lin_wanqing": {
                        "extra": {
                            "app_id": "cli_lin",
                            "app_secret": "secret-lin",
                            "connection_mode": "websocket",
                        }
                    }
                },
            }
        )
        weixin_profiles = _build_weixin_adapter_profiles(
            {
                "enabled": True,
                "token": "wx-token",
                "extra": {"account_id": "wx-account"},
                "routing": {"mode": "dedicated", "bot_id": "lin_wanqing"},
            }
        )

        self.assertEqual(feishu_profiles[0]["app_id"], "cli_lin")
        self.assertEqual(feishu_profiles[0]["bot_id"], "lin_wanqing")
        self.assertEqual(weixin_profiles[0]["platform"].value, "weixin")
        self.assertEqual(weixin_profiles[0]["bot_id"], "lin_wanqing")
        self.assertEqual(weixin_profiles[0]["token"], "wx-token")

    def test_gateway_memory_context_shares_user_memory_across_platforms(self):
        from ai_companion.gateway.cmd import (
            _memory_session_id_from_source,
            _memory_user_id_from_source,
        )

        feishu_source = SessionSource(
            platform=Platform.FEISHU,
            chat_id="chat-1",
            chat_type="dm",
            user_id="same-user",
            user_id_alt="union-1",
        )
        weixin_source = SessionSource(
            platform=Platform.WEIXIN,
            chat_id="same-user",
            chat_type="dm",
            user_id="same-user",
        )

        self.assertEqual(_memory_user_id_from_source(feishu_source), "default_user")
        self.assertEqual(_memory_user_id_from_source(weixin_source), "default_user")
        self.assertEqual(_memory_user_id_from_source(weixin_source, {"memory_user_id": "owner"}), "owner")
        self.assertNotEqual(
            _memory_session_id_from_source(feishu_source),
            _memory_session_id_from_source(weixin_source),
        )


if __name__ == "__main__":
    unittest.main()
