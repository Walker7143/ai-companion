"""Small admin API helpers kept outside the gateway command entrypoint."""

from __future__ import annotations

import hmac
import json
import os
from pathlib import Path
from typing import Any

import yaml

from .path_resolver import discover_bots, get_memory_db_path, project_bots_dir, user_bots_dir


MASKED_SECRET = "********"

PROVIDER_DEFAULTS = {
    "minimax": {"base_url": "https://api.minimax.chat/v1", "model": "MiniMax-M2.7"},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o"},
    "claude": {"base_url": "https://api.anthropic.com/v1", "model": "claude-sonnet-4-20250514"},
    "mimo": {"base_url": "https://token-plan-cn.xiaomimimo.com/v1", "model": "mimo-v2.5-pro"},
    "ollama": {"base_url": "http://localhost:11434", "model": "qwen2.5:7b"},
    "custom": {"base_url": "", "model": ""},
}


WEB_CONFIG_SCHEMA = {
    "sections": [
        {
            "id": "model",
            "title": "模型配置",
            "scope": "global",
            "description": "控制所有 Bot 默认使用的模型 provider、模型名和采样参数。",
            "restart": "保存后新请求生效；运行中 Gateway 不需要重启。",
            "fields": {
                "provider": "选择 MiniMax、OpenAI、Claude、MiMo、Ollama 或自定义兼容接口。",
                "api_key": "敏感字段。留空或保留掩码表示继续使用旧值。",
                "base_url": "Provider API 基础地址；Ollama 通常是 http://localhost:11434/v1。",
                "model": "具体模型名称，例如 gpt-4o、qwen2.5-14b。",
                "temperature": "回复随机性，推荐 0.6-1.0。",
                "max_tokens": "单次回复上限，过高会增加成本。",
            },
        },
        {
            "id": "memory",
            "title": "记忆与上下文",
            "scope": "global",
            "description": "控制工作记忆窗口、压缩阈值和情景记忆向量召回。",
            "restart": "保存后新建 Bot 实例或重启 Gateway 完全生效；部分运行中实例会在下一轮读取新阈值。",
            "fields": {
                "soft_limit_chars": "超过后可能后台压缩，推荐 3000-80000。",
                "hard_limit_chars": "超过后同步压缩，必须大于 soft limit。",
                "max_working_turns": "保留最近多少轮原文，越大上下文越长。",
                "embedding": "local 会启用 sentence-transformers；none 为纯 SQLite 检索。",
                "embedding_model": "本地向量模型名，默认 all-MiniLM-L6-v2。",
            },
        },
        {
            "id": "proactive",
            "title": "主动唤醒",
            "scope": "bot",
            "description": "控制 Bot 主动联系用户的频率、时段、情绪触发和投递平台。",
            "restart": "保存后会尝试热加载并重启调度器。",
            "fields": {
                "mode": "active 会主动联系；silent 只保留状态不主动发。",
                "idle_threshold_hours": "用户空闲多久后考虑主动联系。",
                "max_daily": "每日主动消息上限。",
                "preferred_contact_times": "允许主动联系的时间段，格式 HH:MM-HH:MM。",
            },
        },
        {
            "id": "life",
            "title": "人生轨迹",
            "scope": "bot",
            "description": "控制 Bot 自己的时间流速、日常事件、人生大事概率和事件去重策略。",
            "restart": "保存后会尝试热加载 LifeConfig；调度器下一轮使用新值。",
            "fields": {
                "time_ratio": "1 表示现实同步；24 表示现实 1 小时等于 Bot 1 天；1440 表示现实 1 分钟等于 Bot 1 天。",
                "daily_interval_seconds": "Bot 日常事件基础间隔，推荐 86400。",
                "major_interval_seconds": "人生大事基础检查间隔，推荐 604800。",
                "unexpected_event_probability": "低概率意外事件概率，过高会让人生轨迹失真。",
            },
        },
        {
            "id": "platforms",
            "title": "平台集成",
            "scope": "global",
            "description": "配置 CLI、飞书、Webhook 等入口和主动消息投递。",
            "restart": "飞书连接模式、路由和凭据通常需要重启 Gateway。",
            "fields": {
                "feishu.app_id": "飞书开放平台应用 ID。",
                "feishu.app_secret": "敏感字段。留空或保留掩码表示继续使用旧值。",
                "feishu.group_policy": "open 最开放；生产环境推荐 allowlist 或 admin_only。",
                "feishu.routing": "固定 Bot 绑定。飞书 App 与 Bot 必须双向一对一绑定。",
            },
        },
        {
            "id": "persona",
            "title": "Bot 人格",
            "scope": "bot",
            "description": "编辑基础档案、性格、说话风格、价值观和关键经历。",
            "restart": "对话前会重新读取 persona，保存后下一轮对话生效。",
            "fields": {
                "profile": "姓名、职业、初始年龄、性格标签等基础档案。",
                "speaking_style": "语气、口头禅和情绪表达方式。",
                "values": "原则、底线和软边界。",
                "backstory": "背景故事和关键经历。",
            },
        },
    ],
    "sensitive_fields": ["model.api_key", "platforms.feishu.extra.app_secret"],
}

LIFE_TIME_PRESETS = [
    {"id": "realtime", "label": "现实同步 1:1", "time_ratio": 1, "description": "现实 1 天 = Bot 1 天"},
    {"id": "hourly", "label": "轻度加速 24x", "time_ratio": 24, "description": "现实 1 小时 = Bot 1 天"},
    {"id": "minute", "label": "观察测试 1440x", "time_ratio": 1440, "description": "现实 1 分钟 = Bot 1 天"},
    {"id": "stress", "label": "极速压测 86400x", "time_ratio": 86400, "description": "现实 1 秒 = Bot 1 天"},
]


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    value = str(value)
    if len(value) <= 8:
        return MASKED_SECRET
    return f"{value[:4]}...{value[-4:]}"


def is_masked_secret(value: str | None) -> bool:
    if not value:
        return False
    value = str(value)
    return value == MASKED_SECRET or ("..." in value and len(value) <= 16)


def public_model_config(model_cfg: dict) -> dict:
    provider = model_cfg.get("provider", "minimax")
    defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["minimax"])
    return {
        "provider": provider,
        "api_key": mask_secret(model_cfg.get("api_key", "")),
        "base_url": model_cfg.get("base_url", defaults["base_url"]),
        "model": model_cfg.get("model", defaults["model"]),
        "temperature": model_cfg.get("temperature", 0.7),
        "max_tokens": model_cfg.get("max_tokens", 2000),
    }


def _deep_merge(base: dict, updates: dict) -> dict:
    result = dict(base or {})
    for key, value in (updates or {}).items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _write_yaml(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _as_int(value: Any, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _as_float(value: Any, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [value]


def _is_masked_or_empty(value: Any) -> bool:
    return value in (None, "") or is_masked_secret(str(value))


def _validate_feishu_one_to_one_binding(feishu: dict):
    if not isinstance(feishu, dict):
        return

    default_extra = feishu.get("extra", {}) if isinstance(feishu.get("extra"), dict) else {}
    bindings = feishu.get("bot_bindings")
    if bindings is None:
        bindings = feishu.get("bots")
    binding_values = bindings.values() if isinstance(bindings, dict) else []
    has_binding_app_id = any(
        isinstance(binding, dict)
        and (
            (isinstance(binding.get("extra"), dict) and binding["extra"].get("app_id"))
            or binding.get("app_id")
        )
        for binding in binding_values
    )
    enabled = bool(feishu.get("enabled", False))
    has_default_app_id = bool(default_extra.get("app_id"))
    if not enabled and not has_default_app_id and not has_binding_app_id:
        return
    if enabled and not has_default_app_id and not has_binding_app_id:
        raise ValueError("启用飞书时必须填写 App ID，并绑定一个 Bot。")

    def _routing_bot_id(routing: Any, path: str) -> str:
        routing = routing if isinstance(routing, dict) else {}
        mode = routing.get("mode", "dedicated")
        if mode != "dedicated":
            raise ValueError(
                f"{path}.mode={mode} 不允许保存。飞书 App 与 Bot 必须一对一绑定，"
                "请使用 dedicated 模式。"
            )
        if routing.get("group_bot_map"):
            raise ValueError(
                f"{path}.group_bot_map 不允许保存。飞书 App 与 Bot 必须一对一绑定。"
            )
        return str(routing.get("bot_id") or "")

    def _extra_app_id(extra: Any) -> str:
        return str(extra.get("app_id") or "") if isinstance(extra, dict) else ""

    app_id_by_bot_id: dict[str, str] = {}
    bot_id_by_app_id: dict[str, str] = {}

    def _register(app_id: str, bot_id: str, path: str):
        if not app_id:
            return
        if not bot_id:
            raise ValueError(f"飞书 App {app_id} 未绑定 Bot：请配置 {path}。")

        existing_bot_id = bot_id_by_app_id.get(app_id)
        if existing_bot_id and existing_bot_id != bot_id:
            raise ValueError(
                f"飞书 App {app_id} 同时绑定了多个 Bot：{existing_bot_id}, {bot_id}。"
                "一个飞书 App 只能绑定一个 Bot。"
            )

        existing_app_id = app_id_by_bot_id.get(bot_id)
        if existing_app_id and existing_app_id != app_id:
            raise ValueError(
                f"飞书 Bot {bot_id} 同时绑定了多个 App：{existing_app_id}, {app_id}。"
                "飞书 App 与 Bot 必须双向一对一绑定。"
            )

        bot_id_by_app_id[app_id] = bot_id
        app_id_by_bot_id[bot_id] = app_id

    default_app_id = _extra_app_id(default_extra)
    default_bot_id = _routing_bot_id(feishu.get("routing", {}), "platforms.feishu.routing")
    if default_app_id and default_bot_id:
        _register(default_app_id, default_bot_id, "platforms.feishu.routing.bot_id")

    if isinstance(bindings, dict):
        for bot_id, binding in bindings.items():
            if not isinstance(binding, dict):
                continue
            binding_routing = binding.get("routing")
            if isinstance(binding_routing, dict):
                routing_bot_id = _routing_bot_id(binding_routing, f"platforms.feishu.bot_bindings.{bot_id}.routing")
                if routing_bot_id and routing_bot_id != str(bot_id):
                    raise ValueError(
                        f"飞书 Bot 绑定不一致：bot_bindings.{bot_id}.routing.bot_id={routing_bot_id}，"
                        "应与绑定键一致。"
                    )
            nested_extra = binding.get("extra") if isinstance(binding.get("extra"), dict) else {}
            binding_app_id = _extra_app_id(nested_extra) or _extra_app_id(binding) or default_app_id
            _register(binding_app_id, str(bot_id), f"platforms.feishu.bot_bindings.{bot_id}")

    if default_app_id and default_app_id not in bot_id_by_app_id:
        raise ValueError("飞书 App 未绑定 Bot：请配置 platforms.feishu.routing.bot_id 或 bot_bindings。")


def _feishu_bindings(feishu: dict) -> dict:
    bindings = feishu.get("bot_bindings")
    if bindings is None:
        bindings = feishu.get("bots")
    return bindings if isinstance(bindings, dict) else {}


def _feishu_routing_bot_id(feishu: dict) -> str:
    routing = feishu.get("routing", {}) if isinstance(feishu.get("routing"), dict) else {}
    if routing.get("mode", "dedicated") != "dedicated":
        return ""
    return str(routing.get("bot_id") or "")


def _feishu_extra_for_bot(feishu: dict, bot_id: str) -> dict:
    binding = _feishu_bindings(feishu).get(bot_id)
    if isinstance(binding, dict):
        nested_extra = binding.get("extra") if isinstance(binding.get("extra"), dict) else {}
        flat_extra = {k: v for k, v in binding.items() if k in {"app_id", "app_secret", "domain", "connection_mode", "group_policy", "allowed_users", "admins", "webhook_host", "webhook_port", "encrypt_key", "verification_token"}}
        return {**flat_extra, **nested_extra}

    if _feishu_routing_bot_id(feishu) == bot_id:
        return dict(feishu.get("extra", {}) if isinstance(feishu.get("extra"), dict) else {})
    return {}


def _mask_feishu_extra(extra: dict) -> dict:
    public_extra = dict(extra or {})
    if "app_secret" in public_extra:
        public_extra["app_secret"] = mask_secret(public_extra.get("app_secret"))
    return public_extra


class ConfigAdminService:
    """Read/write Web UI configuration without changing on-disk formats."""

    def __init__(self, config, bot_manager=None):
        self.config = config
        self.bot_manager = bot_manager
        self.config_dir = Path(config.config_dir)
        self.models_path = self.config_dir / "models.yaml"
        self.main_config_path = self.config_dir / "config.yaml"

    def get_bot_config(self, bot_id: str) -> dict | None:
        bot = self.bot_manager.get_bot(bot_id) if self.bot_manager else None
        persona_dir = self._persona_dir(bot_id, bot)
        if not persona_dir.exists():
            return None

        profile = _load_json(persona_dir / "profile.json")
        bot_name = getattr(bot, "name", None) or profile.get("name") or bot_id
        models_data = _load_yaml(self.models_path) or getattr(self.config, "models", {})
        main_config = _load_yaml(self.main_config_path) or getattr(self.config, "config", {})
        model_cfg = self.config.get_model_config()
        proactive_raw = self._load_proactive(persona_dir)
        life_raw = self._load_life(persona_dir)

        return {
            "bot_id": bot_id,
            "name": bot_name,
            "schema": WEB_CONFIG_SCHEMA,
            "model": public_model_config(model_cfg),
            "memory": self._public_memory(models_data.get("memory", {})),
            "proactive": self._public_proactive(proactive_raw),
            "life": self._public_life(life_raw),
            "platforms": self._public_platforms(main_config.get("platforms", {}), bot_id),
            "session_reset": self._public_session_reset(main_config.get("session_reset", {})),
            "persona_summary": self._public_persona(persona_dir),
            "diagnostics": self._diagnostics(bot),
        }

    def update_bot_config(self, bot_id: str, body: dict) -> dict:
        bot = self.bot_manager.get_bot(bot_id) if self.bot_manager else None
        persona_dir = self._persona_dir(bot_id, bot)
        persona_dir.mkdir(parents=True, exist_ok=True)
        changed: list[str] = []
        warnings: list[str] = []

        if "model" in body:
            warnings.extend(self._save_model(body["model"]))
            changed.append(str(self.models_path))

        if "memory" in body:
            self._save_memory(body["memory"])
            changed.append(str(self.models_path))
            warnings.append("记忆配置对新会话立即生效，运行中的 Bot 可能需要重启 Gateway 才完全应用。")

        if "proactive" in body:
            proactive_path = persona_dir / "proactive.json"
            self._save_proactive(proactive_path, body["proactive"])
            changed.append(str(proactive_path))
            self._reload_bot_runtime(bot)

        if "life" in body:
            life_path = persona_dir / "life.json"
            warnings.extend(self._save_life(life_path, body["life"]))
            changed.append(str(life_path))
            self._reload_bot_runtime(bot)

        if "platforms" in body or "feishu" in body or "webhook" in body or "session_reset" in body:
            self._save_main_config(bot_id, body)
            changed.append(str(self.main_config_path))
            if "platforms" in body or "feishu" in body:
                warnings.append("平台连接与飞书路由通常需要重启 Gateway 才会重新建立连接。")

        if "persona" in body:
            changed.extend(self._save_persona(persona_dir, body["persona"]))
            self._reload_bot_runtime(bot)

        if self.config is not None:
            self.config._models = None
            self.config._config = None

        return {
            "ok": True,
            "changed_files": sorted(set(changed)),
            "warnings": warnings,
            "config": self.get_bot_config(bot_id),
        }

    def _persona_dir(self, bot_id: str, bot=None) -> Path:
        if bot is not None and getattr(bot, "persona_loader", None):
            return Path(bot.persona_loader.dir)
        user_dir = user_bots_dir() / bot_id / "persona"
        if user_dir.exists():
            return user_dir
        return project_bots_dir() / bot_id / "persona"

    def _load_proactive(self, persona_dir: Path) -> dict:
        from ai_companion.proactive.config import ProactiveConfig

        raw = _load_json(persona_dir / "proactive.json")
        return _deep_merge(ProactiveConfig.DEFAULT_CONFIG, raw)

    def _load_life(self, persona_dir: Path) -> dict:
        from ai_companion.proactive.life_config import DEFAULT_CONFIG

        raw = _load_json(persona_dir / "life.json")
        return _deep_merge(DEFAULT_CONFIG, raw)

    def _public_memory(self, memory: dict) -> dict:
        return {
            "hard_limit_chars": _as_int(memory.get("hard_limit_chars"), 100000, 1000),
            "soft_limit_chars": _as_int(memory.get("soft_limit_chars"), 80000, 500),
            "max_working_turns": _as_int(memory.get("max_working_turns"), 20, 1, 200),
            "max_summaries": _as_int(memory.get("max_summaries"), 5, 1, 50),
            "semantic_char_limit": _as_int(memory.get("semantic_char_limit"), 4400, 500),
            "embedding": memory.get("embedding", "local"),
            "embedding_model": memory.get("embedding_model", "all-MiniLM-L6-v2"),
        }

    def _public_proactive(self, cfg: dict) -> dict:
        scheduler = cfg.get("scheduler", {})
        triggers = cfg.get("triggers", {})
        emotion = triggers.get("emotion_trigger", {})
        idle = triggers.get("idle_reminder", {})
        platform = cfg.get("platform", {})
        return {
            "enabled": bool(cfg.get("enabled", True)),
            "mode": cfg.get("mode", "active"),
            "check_interval_seconds": _as_int(scheduler.get("check_interval_seconds"), 600, 10),
            "idle_threshold_hours": _as_int(scheduler.get("idle_threshold_hours"), 24, 1),
            "min_interval_hours": _as_float(scheduler.get("min_interval_hours"), 4, 0.1),
            "max_daily": _as_int(scheduler.get("max_daily"), 5, 0, 100),
            "max_idle_days": _as_int(scheduler.get("max_idle_days"), 7, 1),
            "idle_reminder_enabled": bool(idle.get("enabled", True)),
            "idle_reminder_hours": _as_int(idle.get("idle_hours"), scheduler.get("idle_threshold_hours", 24), 1),
            "emotion_trigger_enabled": bool(emotion.get("enabled", True)),
            "emotion_keywords": emotion.get("keywords", []),
            "emotion_response_delay_minutes": _as_int(emotion.get("response_delay_minutes"), 5, 0),
            "preferred_contact_times": cfg.get("preferred_contact_times", ["09:00-23:00"]),
            "timezone": cfg.get("timezone", "Asia/Shanghai"),
            "random_trigger_prob": _as_float(cfg.get("random_trigger_prob"), 0.05, 0, 1),
            "random_trigger_min_ratio": _as_float(cfg.get("random_trigger_min_ratio"), 0.5, 0, 1),
            "platform_type": platform.get("type", "cli"),
            "webhook_url": platform.get("webhook_url") or "",
            "home_channel": cfg.get("home_channel") or platform.get("home_channel") or platform.get("chat_id") or "",
        }

    def _public_life(self, cfg: dict) -> dict:
        event_policy = cfg.get("event_policy", {})
        season = cfg.get("season", {})
        time_ratio = _as_int(cfg.get("time_ratio"), 1, 1)
        preset = next((p["id"] for p in LIFE_TIME_PRESETS if p["time_ratio"] == time_ratio), "custom")
        return {
            "preset": preset,
            "presets": LIFE_TIME_PRESETS,
            "daily_interval_seconds": _as_int(cfg.get("daily_interval_seconds"), 86400, 1),
            "major_interval_seconds": _as_int(cfg.get("major_interval_seconds"), 604800, 1),
            "time_ratio": time_ratio,
            "time_ratio_warning_threshold": _as_int(cfg.get("time_ratio_warning_threshold"), 500, 1),
            "daily_event_min_gap_days": _as_int(cfg.get("daily_event_min_gap_days"), 2, 1),
            "major_event_fixed_probability": _as_float(cfg.get("major_event_fixed_probability"), 0.05, 0, 1),
            "max_events": _as_int(cfg.get("max_events"), 100, 1, 100),
            "max_context_bits": _as_int(cfg.get("max_context_bits"), 2000, 100),
            "birth_date": cfg.get("birth_date") or "",
            "season": {
                "hemisphere": season.get("hemisphere", "north"),
                "birthday_month": _as_int(season.get("birthday_month"), 1, 1, 12),
            },
            "event_policy": {
                "scenario_cooldown_days": _as_int(event_policy.get("scenario_cooldown_days"), 14, 0),
                "major_scenario_cooldown_days": _as_int(event_policy.get("major_scenario_cooldown_days"), 180, 0),
                "unexpected_event_probability": _as_float(event_policy.get("unexpected_event_probability"), 0.01, 0, 1),
                "unexpected_event_cooldown_days": _as_int(event_policy.get("unexpected_event_cooldown_days"), 365, 0),
                "llm_daily_candidate_limit": _as_int(event_policy.get("llm_daily_candidate_limit"), 12, 3, 20),
            },
            "milestones": cfg.get("milestones", []),
            "holidays": cfg.get("holidays", []),
        }

    def _public_platforms(self, platforms: dict, bot_id: str) -> list[dict]:
        result = []
        for name in ("cli", "feishu", "webhook"):
            cfg = platforms.get(name, {}) if isinstance(platforms.get(name), dict) else {}
            public_cfg = dict(cfg)
            if name == "feishu":
                extra = _feishu_extra_for_bot(cfg, bot_id)
                public_cfg = {
                    "extra": _mask_feishu_extra(extra),
                    "routing": {"mode": "dedicated", "bot_id": bot_id},
                }
                if extra:
                    binding = _feishu_bindings(cfg).get(bot_id)
                    if isinstance(binding, dict):
                        for key in ("home_channel", "chat_id", "group_id"):
                            if key in binding:
                                public_cfg[key] = binding[key]
                    elif isinstance(cfg.get("home_channel"), dict):
                        public_cfg["home_channel"] = cfg["home_channel"]
            result.append({
                "name": name,
                "enabled": bool(extra) if name == "feishu" else bool(cfg.get("enabled", name == "cli")),
                "config": public_cfg,
            })
        return result

    def _public_session_reset(self, session_reset: dict) -> dict:
        return {
            "mode": session_reset.get("mode", "daily"),
            "at_hour": _as_int(session_reset.get("at_hour"), 0, 0, 23),
            "idle_minutes": _as_int(session_reset.get("idle_minutes"), 30, 1),
            "notify": bool(session_reset.get("notify", True)),
        }

    def _public_persona(self, persona_dir: Path) -> dict:
        profile = _load_json(persona_dir / "profile.json")
        backstory = _load_json(persona_dir / "backstory.json")
        values = _load_json(persona_dir / "values.json")
        speaking_style = _load_json(persona_dir / "speaking_style.json")
        return {
            "profile": {
                "name": profile.get("name", ""),
                "age": profile.get("age", ""),
                "birth_date": profile.get("birth_date", ""),
                "occupation": profile.get("occupation", ""),
                "gender": profile.get("gender", ""),
                "personality_tags": profile.get("personality_tags", []),
                "relationship_to_user": profile.get("relationship_to_user", ""),
                "interests": profile.get("interests", []),
                "appearance": profile.get("appearance", ""),
                "summary": profile.get("summary", ""),
            },
            "backstory": {
                "summary": backstory.get("summary", ""),
                "key_moments": backstory.get("key_moments", []),
                "meeting_user": backstory.get("meeting_user", ""),
                "now": backstory.get("now", ""),
            },
            "values": {
                "non_negotiable": values.get("non_negotiable", []),
                "soft_boundaries": values.get("soft_boundaries", []),
            },
            "speaking_style": {
                "tone": speaking_style.get("tone", ""),
                "catchphrases": speaking_style.get("口头禅", []),
                "greeting_style": speaking_style.get("greeting_style", ""),
                "farewell_style": speaking_style.get("farewell_style", ""),
            },
        }

    def _diagnostics(self, bot) -> dict:
        life_status = {}
        if bot is not None and getattr(bot, "life_engine", None):
            try:
                life_status = bot.life_engine.get_status()
            except Exception:
                life_status = {}
        return {
            "requires_restart": [],
            "life_status": life_status,
        }

    def _save_model(self, model_data: dict) -> list[str]:
        warnings = []
        models_data = _load_yaml(self.models_path)
        provider = model_data.get("provider", models_data.get("model", {}).get("provider", "minimax"))
        existing_provider = dict(models_data.get(provider, {}) if isinstance(models_data.get(provider), dict) else {})
        incoming_api_key = model_data.get("api_key")
        if _is_masked_or_empty(incoming_api_key):
            incoming_api_key = existing_provider.get("api_key", "")
        defaults = PROVIDER_DEFAULTS.get(provider, {})
        models_data[provider] = {
            "api_key": incoming_api_key,
            "base_url": model_data.get("base_url") or existing_provider.get("base_url") or defaults.get("base_url", ""),
            "model": model_data.get("model") or existing_provider.get("model") or defaults.get("model", ""),
        }
        existing_global = dict(models_data.get("model", {}) if isinstance(models_data.get("model"), dict) else {})
        existing_global.update({
            "provider": provider,
            "temperature": _as_float(model_data.get("temperature"), existing_global.get("temperature", 0.7), 0, 2),
            "max_tokens": _as_int(model_data.get("max_tokens"), existing_global.get("max_tokens", 2000), 1),
        })
        models_data["model"] = existing_global
        _write_yaml(self.models_path, models_data)
        if provider in {"minimax", "openai", "claude", "mimo"} and not incoming_api_key:
            warnings.append(f"{provider} 需要 API Key，当前保存后可能无法启动模型。")
        return warnings

    def _save_memory(self, memory_data: dict):
        models_data = _load_yaml(self.models_path)
        existing = dict(models_data.get("memory", {}) if isinstance(models_data.get("memory"), dict) else {})
        existing.update({
            "hard_limit_chars": _as_int(memory_data.get("hard_limit_chars"), existing.get("hard_limit_chars", 100000), 1000),
            "soft_limit_chars": _as_int(memory_data.get("soft_limit_chars"), existing.get("soft_limit_chars", 80000), 500),
            "max_working_turns": _as_int(memory_data.get("max_working_turns"), existing.get("max_working_turns", 20), 1, 200),
            "max_summaries": _as_int(memory_data.get("max_summaries"), existing.get("max_summaries", 5), 1, 50),
            "semantic_char_limit": _as_int(memory_data.get("semantic_char_limit"), existing.get("semantic_char_limit", 4400), 500),
            "embedding": memory_data.get("embedding", existing.get("embedding", "local")),
            "embedding_model": memory_data.get("embedding_model", existing.get("embedding_model", "all-MiniLM-L6-v2")),
        })
        if existing["soft_limit_chars"] >= existing["hard_limit_chars"]:
            existing["soft_limit_chars"] = max(500, existing["hard_limit_chars"] - 1000)
        models_data["memory"] = existing
        _write_yaml(self.models_path, models_data)

    def _save_proactive(self, path: Path, proactive_data: dict):
        from ai_companion.proactive.config import ProactiveConfig

        existing = _deep_merge(ProactiveConfig.DEFAULT_CONFIG, _load_json(path))
        scheduler = existing.setdefault("scheduler", {})
        triggers = existing.setdefault("triggers", {})
        idle = triggers.setdefault("idle_reminder", {})
        emotion = triggers.setdefault("emotion_trigger", {})
        platform = existing.setdefault("platform", {})
        existing["enabled"] = bool(proactive_data.get("enabled", existing.get("enabled", True)))
        existing["mode"] = proactive_data.get("mode", existing.get("mode", "active"))
        scheduler["check_interval_seconds"] = _as_int(proactive_data.get("check_interval_seconds"), scheduler.get("check_interval_seconds", 600), 10)
        scheduler["idle_threshold_hours"] = _as_int(proactive_data.get("idle_threshold_hours"), scheduler.get("idle_threshold_hours", 24), 1)
        scheduler["min_interval_hours"] = _as_float(proactive_data.get("min_interval_hours"), scheduler.get("min_interval_hours", 4), 0.1)
        scheduler["max_daily"] = _as_int(proactive_data.get("max_daily"), scheduler.get("max_daily", 5), 0, 100)
        scheduler["max_idle_days"] = _as_int(proactive_data.get("max_idle_days"), scheduler.get("max_idle_days", 7), 1)
        idle["enabled"] = bool(proactive_data.get("idle_reminder_enabled", idle.get("enabled", True)))
        idle["idle_hours"] = _as_int(proactive_data.get("idle_reminder_hours"), idle.get("idle_hours", scheduler["idle_threshold_hours"]), 1)
        emotion["enabled"] = bool(proactive_data.get("emotion_trigger_enabled", emotion.get("enabled", True)))
        emotion["keywords"] = _as_list(proactive_data.get("emotion_keywords", emotion.get("keywords", [])))
        emotion["response_delay_minutes"] = _as_int(proactive_data.get("emotion_response_delay_minutes"), emotion.get("response_delay_minutes", 5), 0)
        existing["preferred_contact_times"] = _as_list(proactive_data.get("preferred_contact_times", existing.get("preferred_contact_times", ["09:00-23:00"])))
        existing["timezone"] = proactive_data.get("timezone", existing.get("timezone", "Asia/Shanghai"))
        existing["random_trigger_prob"] = _as_float(proactive_data.get("random_trigger_prob"), existing.get("random_trigger_prob", 0.05), 0, 1)
        existing["random_trigger_min_ratio"] = _as_float(proactive_data.get("random_trigger_min_ratio"), existing.get("random_trigger_min_ratio", 0.5), 0, 1)
        platform["type"] = proactive_data.get("platform_type", platform.get("type", "cli"))
        platform["webhook_url"] = proactive_data.get("webhook_url", platform.get("webhook_url"))
        if proactive_data.get("home_channel"):
            platform["home_channel"] = proactive_data.get("home_channel")
        _write_json(path, existing)

    def _save_life(self, path: Path, life_data: dict) -> list[str]:
        from ai_companion.proactive.life_config import DEFAULT_CONFIG

        warnings = []
        existing = _deep_merge(DEFAULT_CONFIG, _load_json(path))
        existing["daily_interval_seconds"] = _as_int(life_data.get("daily_interval_seconds"), existing.get("daily_interval_seconds", 86400), 1)
        existing["major_interval_seconds"] = _as_int(life_data.get("major_interval_seconds"), existing.get("major_interval_seconds", 604800), 1)
        existing["time_ratio"] = _as_int(life_data.get("time_ratio"), existing.get("time_ratio", 1), 1, 86400)
        existing["time_ratio_warning_threshold"] = _as_int(life_data.get("time_ratio_warning_threshold"), existing.get("time_ratio_warning_threshold", 500), 1)
        existing["daily_event_min_gap_days"] = _as_int(life_data.get("daily_event_min_gap_days"), existing.get("daily_event_min_gap_days", 2), 1)
        existing["major_event_fixed_probability"] = _as_float(life_data.get("major_event_fixed_probability"), existing.get("major_event_fixed_probability", 0.05), 0, 1)
        existing["max_events"] = _as_int(life_data.get("max_events"), existing.get("max_events", 100), 1, 100)
        existing["max_context_bits"] = _as_int(life_data.get("max_context_bits"), existing.get("max_context_bits", 2000), 100)
        existing["birth_date"] = life_data.get("birth_date") or existing.get("birth_date")
        if isinstance(life_data.get("season"), dict):
            existing["season"] = _deep_merge(existing.get("season", {}), life_data["season"])
        if isinstance(life_data.get("event_policy"), dict):
            policy = _deep_merge(existing.get("event_policy", {}), life_data["event_policy"])
            policy["unexpected_event_probability"] = _as_float(policy.get("unexpected_event_probability"), 0.01, 0, 1)
            policy["llm_daily_candidate_limit"] = _as_int(policy.get("llm_daily_candidate_limit"), 12, 3, 20)
            existing["event_policy"] = policy
        if isinstance(life_data.get("milestones"), list):
            existing["milestones"] = life_data["milestones"]
        if isinstance(life_data.get("holidays"), list):
            existing["holidays"] = life_data["holidays"]
        if existing["time_ratio"] > existing.get("time_ratio_warning_threshold", 500):
            warnings.append("当前时间倍率较高，可能让事件过快生成，建议仅用于观察测试。")
        _write_json(path, existing)
        return warnings

    def _save_main_config(self, bot_id: str, body: dict):
        config_data = _load_yaml(self.main_config_path)
        platforms = config_data.setdefault("platforms", {})
        for platform in body.get("platforms", []) or []:
            name = platform.get("name")
            if not name:
                continue
            if name == "feishu":
                # Feishu is bot-scoped in the Web UI. Handle it below so one
                # bot page cannot leak its app_id into every other bot page.
                continue
            current = dict(platforms.get(name, {}) if isinstance(platforms.get(name), dict) else {})
            current["enabled"] = bool(platform.get("enabled", current.get("enabled", name == "cli")))
            if isinstance(platform.get("config"), dict):
                current = _deep_merge(current, platform["config"])
            platforms[name] = current

        feishu = body.get("feishu")
        if isinstance(feishu, dict):
            platforms["feishu"] = self._save_feishu_for_bot(
                bot_id,
                dict(platforms.get("feishu", {}) if isinstance(platforms.get("feishu"), dict) else {}),
                feishu,
            )

        if isinstance(body.get("session_reset"), dict):
            config_data["session_reset"] = self._public_session_reset(body["session_reset"])
        _validate_feishu_one_to_one_binding(platforms.get("feishu", {}))
        _write_yaml(self.main_config_path, config_data)

    def _save_feishu_for_bot(self, bot_id: str, current: dict, incoming: dict) -> dict:
        incoming_extra = incoming.get("extra", {}) if isinstance(incoming.get("extra"), dict) else {}
        enabled = bool(incoming.get("enabled", current.get("enabled", False)))
        has_incoming_app = bool(incoming_extra.get("app_id"))
        has_incoming_secret = "app_secret" in incoming_extra and not _is_masked_or_empty(incoming_extra.get("app_secret"))

        bindings = _feishu_bindings(current)
        current_global_bot_id = _feishu_routing_bot_id(current)
        use_binding = bool(bindings) or (current_global_bot_id and current_global_bot_id != bot_id)

        if not enabled and not has_incoming_app and not has_incoming_secret:
            if use_binding:
                next_bindings = dict(bindings)
                next_bindings.pop(bot_id, None)
                current["bot_bindings"] = next_bindings
                if not next_bindings and not current.get("extra"):
                    current["enabled"] = False
            elif current_global_bot_id == bot_id:
                current.pop("extra", None)
                current.pop("routing", None)
                current["enabled"] = False
            return current

        current["enabled"] = True
        existing_extra = _feishu_extra_for_bot(current, bot_id)
        next_extra = dict(existing_extra)
        for key, value in incoming_extra.items():
            if key == "app_secret" and _is_masked_or_empty(value):
                continue
            next_extra[key] = value

        if use_binding:
            next_bindings = dict(bindings)
            existing_binding = next_bindings.get(bot_id, {})
            if not isinstance(existing_binding, dict):
                existing_binding = {}
            next_binding = {k: v for k, v in existing_binding.items() if k not in {"extra", "routing", "app_id", "app_secret"}}
            next_binding["extra"] = next_extra
            if isinstance(incoming.get("home_channel"), dict):
                next_binding["home_channel"] = incoming["home_channel"]
            next_bindings[bot_id] = next_binding
            current["bot_bindings"] = next_bindings
            return current

        current["extra"] = next_extra
        current["routing"] = {"mode": "dedicated", "bot_id": bot_id}
        current.pop("bot_bindings", None)
        return current

    def _save_persona(self, persona_dir: Path, persona_data: dict) -> list[str]:
        changed = []
        file_map = {
            "profile": "profile.json",
            "backstory": "backstory.json",
            "values": "values.json",
            "speaking_style": "speaking_style.json",
        }
        for section, filename in file_map.items():
            if not isinstance(persona_data.get(section), dict):
                continue
            path = persona_dir / filename
            existing = _load_json(path)
            updates = dict(persona_data[section])
            if section == "speaking_style" and "catchphrases" in updates:
                updates["口头禅"] = updates.pop("catchphrases")
            merged = _deep_merge(existing, updates)
            _write_json(path, merged)
            changed.append(str(path))
        return changed

    def _reload_bot_runtime(self, bot):
        if not bot:
            return
        try:
            bot._refresh_runtime_settings()
        except Exception:
            pass


def admin_host(config: dict) -> str:
    admin_cfg = config.get("admin", {}) if isinstance(config, dict) else {}
    return os.environ.get("AI_COMPANION_ADMIN_HOST") or admin_cfg.get("host") or "127.0.0.1"


def admin_port(config: dict) -> int:
    admin_cfg = config.get("admin", {}) if isinstance(config, dict) else {}
    raw = os.environ.get("AI_COMPANION_ADMIN_PORT") or admin_cfg.get("port") or 8642
    return int(raw)


def allowed_cors_origins(config: dict) -> set[str]:
    admin_cfg = config.get("admin", {}) if isinstance(config, dict) else {}
    raw = os.environ.get("AI_COMPANION_ADMIN_CORS_ORIGINS") or admin_cfg.get("cors_origins")
    if isinstance(raw, str) and raw.strip():
        return {item.strip() for item in raw.split(",") if item.strip()}
    if isinstance(raw, list):
        return {str(item).strip() for item in raw if str(item).strip()}
    return {"http://localhost:1421", "http://127.0.0.1:1421"}


def list_sessions(bot_id: str | None = None) -> list[dict]:
    import sqlite3

    sessions: list[dict] = []
    bots = [b for b in discover_bots() if not bot_id or b["id"] == bot_id]
    for bot in bots:
        current_bot_id = bot["id"]
        db_path = get_memory_db_path(current_bot_id, "working.db")
        if not db_path:
            continue
        try:
            conn = sqlite3.connect(str(db_path))
            rows = conn.execute(
                """
                SELECT session_id,
                       COUNT(*) as msg_count,
                       MAX(id) as last_msg_id,
                       MIN(created_at) as first_at,
                       MAX(created_at) as last_at,
                       COALESCE(SUM(LENGTH(content)), 0) as total_chars
                FROM messages
                GROUP BY session_id
                ORDER BY last_msg_id DESC
                LIMIT 100
                """
            ).fetchall()
            conn.close()
        except Exception:
            continue

        for row in rows:
            sessions.append(
                {
                    "session_key": f"{current_bot_id}:{row[0]}",
                    "session_id": row[0],
                    "bot_id": current_bot_id,
                    "platform": "cli",
                    "user": "用户",
                    "created_at": row[3],
                    "updated_at": row[4],
                    "last_at": row[4],
                    "status": "active",
                    "reset_reason": None,
                    "total_tokens": row[5] // 2,
                }
            )
    sessions.sort(key=lambda item: item.get("last_at") or "", reverse=True)
    return sessions


def working_messages(bot_id: str, session_id: str | None = None) -> list[dict]:
    import sqlite3

    db_path = get_memory_db_path(bot_id, "working.db")
    if not db_path:
        return []
    conn = sqlite3.connect(str(db_path))
    if session_id:
        rows = conn.execute(
            """
            SELECT id, role, content, created_at
            FROM messages
            WHERE session_id = ? AND compressed = 0
            ORDER BY id DESC
            LIMIT 50
            """,
            (session_id,),
        ).fetchall()
        conn.close()
        rows = list(reversed(rows))
    else:
        row = conn.execute(
            """
            SELECT session_id FROM messages
            WHERE compressed = 0
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        if not row:
            conn.close()
            return []
        rows = conn.execute(
            """
            SELECT id, role, content, created_at
            FROM messages
            WHERE session_id = ? AND compressed = 0
            ORDER BY id ASC
            """,
            (row[0],),
        ).fetchall()
        conn.close()

    return [{"id": str(r[0]), "role": r[1], "content": r[2], "created_at": r[3]} for r in rows]


def append_audit_record(path: Path, record: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(record.rstrip() + "\n")


def constant_time_token_match(actual: str | None, provided: str | None) -> bool:
    if not actual:
        return True
    return hmac.compare_digest(str(actual), str(provided or ""))
