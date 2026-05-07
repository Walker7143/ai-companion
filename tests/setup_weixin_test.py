import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ai_companion import setup


class WeixinSetupTest(unittest.IsolatedAsyncioTestCase):
    async def test_configure_weixin_channel_preserves_existing_config_and_syncs_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            config_dir = data_dir / "config"
            config_dir.mkdir(parents=True)
            (config_dir / "bots.yaml").write_text(
                yaml.dump(
                    {
                        "bots": [
                            {"id": "lin_wanqing", "name": "林晚晴"},
                            {"id": "zhou_yan", "name": "周妍"},
                        ]
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            (config_dir / "config.yaml").write_text(
                yaml.dump(
                    {
                        "platforms": {
                            "cli": {"enabled": True},
                            "feishu": {
                                "enabled": True,
                                "extra": {"app_id": "cli_old"},
                                "routing": {"mode": "dedicated", "bot_id": "lin_wanqing"},
                            },
                        },
                        "logging": {"level": "INFO"},
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            (data_dir / ".env").write_text('MINIMAX_API_KEY="old"\nWEIXIN_TOKEN="old-token"\n', encoding="utf-8")

            async def fake_prompt_weixin_platform_config(**kwargs):
                self.assertEqual(kwargs["existing_weixin"], {})
                self.assertEqual([bot["id"] for bot in kwargs["binding_bots"]], ["lin_wanqing", "zhou_yan"])
                return {
                    "enabled": True,
                    "token": "new-token",
                    "extra": {
                        "account_id": "wxbot-1",
                        "base_url": "https://ilinkai.weixin.qq.com",
                        "cdn_base_url": "https://novac2c.cdn.weixin.qq.com/c2c",
                        "dm_policy": "allowlist",
                        "allow_from": ["wxid_a"],
                        "group_policy": "disabled",
                        "group_allow_from": [],
                        "split_multiline_messages": False,
                    },
                    "routing": {"mode": "dedicated", "bot_id": "lin_wanqing"},
                    "home_channel": {"platform": "weixin", "chat_id": "wxid_a", "name": "微信私聊"},
                }

            with patch.object(setup, "_prompt_weixin_platform_config", fake_prompt_weixin_platform_config):
                ok = await setup.configure_weixin_channel(data_dir=data_dir, sync_env=True)

            self.assertTrue(ok)
            saved = yaml.safe_load((config_dir / "config.yaml").read_text(encoding="utf-8"))
            self.assertEqual(saved["platforms"]["feishu"]["extra"]["app_id"], "cli_old")
            self.assertEqual(saved["platforms"]["weixin"]["token"], "new-token")
            self.assertEqual(saved["platforms"]["weixin"]["extra"]["account_id"], "wxbot-1")
            self.assertEqual(saved["logging"]["level"], "INFO")

            env_text = (data_dir / ".env").read_text(encoding="utf-8")
            self.assertIn('MINIMAX_API_KEY="old"', env_text)
            self.assertIn('WEIXIN_TOKEN="new-token"', env_text)
            self.assertIn('WEIXIN_ACCOUNT_ID="wxbot-1"', env_text)
            self.assertIn('WEIXIN_BOT_ID="lin_wanqing"', env_text)
            self.assertIn('WEIXIN_HOME_CHANNEL="wxid_a"', env_text)


if __name__ == "__main__":
    unittest.main()
