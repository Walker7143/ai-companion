"""Gateway slash commands shared by platform adapters."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from typing import Any

from ai_companion.config.loader import Config
from ai_companion.model.factory import ModelFactory


SUPPORTED_GATEWAY_COMMANDS = frozenset({"new", "reset", "models", "model", "status", "memory", "dream"})
_PROVIDER_ENV_KEYS = {
    "minimax": "MINIMAX_API_KEY",
    "openai": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "mimo": "MIMO_API_KEY",
}


@dataclass(frozen=True)
class ParsedGatewayCommand:
    name: str
    args: str


def parse_gateway_command(text: str) -> ParsedGatewayCommand | None:
    stripped = (text or "").strip()
    if not stripped.startswith("/"):
        return None

    first, _, rest = stripped.partition(" ")
    name = first[1:].lower()
    if "@" in name:
        name = name.split("@", 1)[0]
    if "/" in name or name not in SUPPORTED_GATEWAY_COMMANDS:
        return None
    return ParsedGatewayCommand(name=name, args=rest.strip())


def is_gateway_command_name(command_name: str | None) -> bool:
    return bool(command_name and command_name.lower() in SUPPORTED_GATEWAY_COMMANDS)


def _current_model_info(bot: Any) -> tuple[str, str]:
    model = getattr(bot, "model", None)
    provider = getattr(model, "provider", "") or "unknown"
    model_name = getattr(model, "model", "") or "unknown"
    return str(provider), str(model_name)


def _configured_providers(config: Config) -> list[str]:
    providers: list[str] = []
    models = config.models
    for provider in ModelFactory.list_providers():
        if isinstance(models.get(provider), dict):
            providers.append(provider)
    return providers


def _provider_model_name(config: Config, provider: str) -> str:
    provider_cfg = config.models.get(provider, {})
    if isinstance(provider_cfg, dict):
        return str(provider_cfg.get("model") or "")
    return ""


def _resolve_api_key(provider: str, model_cfg: dict) -> str:
    env_key = _PROVIDER_ENV_KEYS.get(provider)
    api_key = os.environ.get(env_key, "") if env_key else ""
    if not api_key:
        api_key = str(model_cfg.get("api_key", ""))
    if provider in _PROVIDER_ENV_KEYS and (not api_key or api_key.startswith("${")):
        raise ValueError(
            f"{provider} API Key 未配置。请设置环境变量 {env_key}，或运行 ai-companion setup。"
        )
    return api_key


def _create_model_from_config(
    config: Config,
    provider: str,
    model_name: str | None = None,
):
    model_cfg = dict(config.get_model_config(provider))
    if not model_cfg:
        raise ValueError(f"models.yaml 中找不到 provider: {provider}")
    if model_name:
        model_cfg["model"] = model_name

    api_key = _resolve_api_key(provider, model_cfg)
    return ModelFactory.create_from_runtime_config(
        model_config=model_cfg,
        provider=provider,
        api_key=api_key if provider in _PROVIDER_ENV_KEYS else None,
    )


class GatewayCommandHandler:
    """Handle lightweight slash commands before messages enter the bot loop."""

    def __init__(self, config: Config):
        self.config = config

    async def handle(self, text: str, bot: Any, event: Any = None) -> str | None:
        command = parse_gateway_command(text)
        if command is None:
            return None

        if command.name in {"new", "reset"}:
            return self._handle_new(bot)
        if command.name == "models":
            return self._handle_models(bot)
        if command.name == "model":
            return self._handle_model(bot, command.args)
        if command.name == "status":
            return await self._handle_status(bot, event)
        if command.name == "memory":
            return await self._handle_memory(bot)
        if command.name == "dream":
            return await self._handle_dream(bot, command.args)
        return None

    def _handle_new(self, bot: Any) -> str:
        bot.reset_history()
        return "已开启新会话。"

    def _handle_models(self, bot: Any) -> str:
        active_provider, active_model = _current_model_info(bot)
        providers = _configured_providers(self.config)
        lines = [f"当前模型: {active_provider} / {active_model}", "", "可用模型:"]
        if not providers:
            lines.append("- 未在 models.yaml 中找到可用 provider")
        for provider in providers:
            marker = " *" if provider == active_provider else ""
            model_name = _provider_model_name(self.config, provider) or "(未配置 model)"
            lines.append(f"- {provider}: {model_name}{marker}")
        lines.extend([
            "",
            "用法:",
            "/model 查看当前模型",
            "/model <provider> 切换 provider",
            "/model <provider> <model> 切换 provider 并指定模型",
            "/model <model> 在当前 provider 下切换模型名",
        ])
        return "\n".join(lines)

    def _handle_model(self, bot: Any, args: str) -> str:
        if not args.strip():
            provider, model_name = _current_model_info(bot)
            return f"当前模型: {provider} / {model_name}\n使用 /models 查看可用配置。"

        try:
            tokens = shlex.split(args)
        except ValueError as exc:
            return f"/model 参数解析失败: {exc}"

        try:
            provider, model_name, global_requested = self._parse_model_args(bot, tokens)
        except ValueError as exc:
            return f"/model 参数解析失败: {exc}"
        if not provider:
            return "无法确定 provider。请使用 /models 查看可用配置。"

        configured = set(_configured_providers(self.config))
        if provider not in configured:
            return f"provider 未配置: {provider}\n请先在 models.yaml 或管理后台配置后再切换。"

        try:
            model = _create_model_from_config(self.config, provider, model_name)
        except Exception as exc:
            return f"模型切换失败: {exc}"

        bot.set_model(model)
        _, active_model = _current_model_info(bot)
        suffix = "\n提示: 飞书内的 /model 只切换当前 Bot 的运行时模型，不会写回 models.yaml。" if global_requested else ""
        return f"已切换模型: {provider} / {active_model}{suffix}"

    def _parse_model_args(self, bot: Any, tokens: list[str]) -> tuple[str, str | None, bool]:
        provider = ""
        model_tokens: list[str] = []
        global_requested = False
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token == "--provider":
                if i + 1 >= len(tokens):
                    raise ValueError("--provider 需要指定 provider")
                provider = tokens[i + 1].lower()
                i += 2
                continue
            if token == "--global":
                global_requested = True
                i += 1
                continue
            model_tokens.append(token)
            i += 1

        configured = set(_configured_providers(self.config))
        all_providers = set(ModelFactory.list_providers())
        if not provider and model_tokens:
            first = model_tokens[0].lower()
            if first in configured or first in all_providers:
                provider = first
                model_tokens = model_tokens[1:]

        if not provider:
            current_provider, _ = _current_model_info(bot)
            provider = current_provider if current_provider != "unknown" else self.config.default_provider

        model_name = " ".join(model_tokens).strip() or None
        return provider, model_name, global_requested

    async def _handle_status(self, bot: Any, event: Any = None) -> str:
        provider, model_name = _current_model_info(bot)
        lines = [
            "状态:",
            f"- Bot: {getattr(bot, 'name', 'unknown')} ({getattr(bot, 'id', 'unknown')})",
            f"- 模型: {provider} / {model_name}",
        ]

        source = getattr(event, "source", None)
        if source is not None:
            chat_type = getattr(source, "chat_type", "") or "unknown"
            chat_name = getattr(source, "chat_name", "") or getattr(source, "chat_id", "") or "unknown"
            lines.append(f"- 会话: {chat_type} / {chat_name}")

        memory = getattr(bot, "memory", None)
        if memory:
            try:
                status = await memory.get_memory_status()
                lines.append(f"- 工作记忆轮数: {status.get('working_turns', 0)}")
                lines.append(f"- 情景记忆条数: {status.get('episodic_count', 0)}")
                lines.append(f"- 语义记忆事实数: {status.get('fact_count', 0)}")
            except Exception as exc:
                lines.append(f"- 记忆状态: 读取失败 ({exc})")
        else:
            lines.append("- 记忆状态: 未启用")

        try:
            proactive = bot.get_proactive_status()
            proactive_cfg = proactive.get("config", {}) if isinstance(proactive, dict) else {}
            scheduler_lock = proactive.get("scheduler_lock", {}) if isinstance(proactive, dict) else {}
            lines.append(f"- 主动唤醒: {'开启' if proactive_cfg.get('enabled') else '关闭'}")
            for label, key in (("主动唤醒", "proactive"), ("人生轨迹", "life")):
                lock_info = scheduler_lock.get(key, {}) if isinstance(scheduler_lock, dict) else {}
                if lock_info.get("held") is False and lock_info.get("owner"):
                    owner = lock_info["owner"]
                    owner_pid = owner.get("pid") or "unknown"
                    lines.append(f"- {label}轮询: 已由其他进程持有 (PID {owner_pid})")
        except Exception:
            pass

        return "\n".join(lines)

    async def _handle_memory(self, bot: Any) -> str:
        memory = getattr(bot, "memory", None)
        if not memory:
            return "记忆状态: 未启用"
        try:
            status = await memory.get_memory_status()
        except Exception as exc:
            return f"记忆状态: 读取失败 ({exc})"

        lines = [
            "记忆状态:",
            f"- 工作记忆轮数: {status.get('working_turns', 0)}",
            f"- 情景记忆条数: {status.get('episodic_count', 0)}",
            f"- 语义记忆事实数: {status.get('fact_count', 0)}",
        ]
        relationship = status.get("relationship") or {}
        if relationship:
            lines.append(
                f"- 关系状态: {relationship.get('relationship_label', '朋友')} "
                f"({float(relationship.get('relationship_score') or 0):.0f}/100)"
            )

        trust = status.get("memory_trust_view") or {}
        anchor = trust.get("relationship_anchor") or {}
        if anchor.get("narrative"):
            lines.append("")
            lines.append("记忆信任视图:")
            lines.append(f"- 关系锚点: {anchor.get('narrative')}")

        for title, key, limit in [
            ("最近正在记住", "recently_remembered", 5),
            ("稳定理解", "stable_understanding", 5),
            ("可能需要确认", "pending_confirmation", 5),
            ("最近已纠正", "corrected_memories", 5),
            ("已归档/压制", "archived_or_suppressed", 5),
        ]:
            items = trust.get(key) if isinstance(trust.get(key), list) else []
            if not items:
                continue
            lines.append(f"- {title}:")
            for item in items[:limit]:
                lines.append(f"  - {_format_memory_view_item(item, key)}")

        health = status.get("health") or {}
        if health.get("reason"):
            lines.append(f"- 健康提示: {health.get('reason')}")
        return "\n".join(lines)

    async def _handle_dream(self, bot: Any, args: str) -> str:
        memory = getattr(bot, "memory", None)
        dreaming = getattr(memory, "dreaming", None) if memory else None
        if not dreaming:
            return "记忆整理: 未启用"

        action = (args or "").strip().lower()
        if not action:
            action = "status"

        if action == "on":
            await dreaming.set_enabled(True)
            return "已开启记忆整理。"
        if action == "off":
            await dreaming.set_enabled(False)
            return "已关闭记忆整理。"
        if action == "run":
            result = await dreaming.run(trigger_source="gateway_command", trigger_reason="/dream run")
            report = result.get("report") or {}
            return "\n".join(
                [
                    "记忆整理已完成。",
                    f"- 候选数: {result.get('run', {}).get('candidate_count', 0)}",
                    f"- 提升到长期层: {result.get('run', {}).get('promoted_count', 0)}",
                    f"- 保留为短期连续性: {result.get('run', {}).get('kept_short_term_count', 0)}",
                    report.get("user_summary") or "",
                ]
            ).strip()
        if action == "doctor":
            doctor = await dreaming.doctor_status()
            lines = ["记忆整理诊断:"]
            if doctor.get("ok"):
                lines.append("- 状态: 正常")
            else:
                lines.append("- 状态: 需要关注")
                for issue in doctor.get("issues") or []:
                    lines.append(f"- 问题: {issue}")
            for suggestion in doctor.get("suggestions") or []:
                lines.append(f"- 建议: {suggestion}")
            return "\n".join(lines)
        if action == "report":
            report = await dreaming.latest_report()
            if not report:
                return "最近还没有记忆整理报告。"
            return report.get("user_summary") or "最近还没有可展示的整理摘要。"
        if action == "delete":
            deleted = await dreaming.delete_latest_promotions()
            if not deleted.get("ok"):
                return deleted.get("message") or "最近没有可删除的整理结果。"
            parts = deleted.get("deleted") or {}
            return (
                "已删除最近一次整理新增的自动记忆："
                f" semantic={parts.get('semantic', 0)}"
                f" understanding={parts.get('understanding_projection', 0)}"
            )

        status = await dreaming.status()
        latest = status.get("latest_report") or {}
        return "\n".join(
            [
                "记忆整理状态:",
                f"- 开关: {'开启' if status.get('enabled') else '关闭'}",
                f"- 自动运行: {'开启' if status.get('auto_run_enabled') else '关闭'}",
                f"- 最近状态: {status.get('last_status') or '暂无'}",
                f"- 最近运行时间: {status.get('last_run_at') or '暂无'}",
                f"- 最近摘要: {latest.get('user_summary') or status.get('last_summary') or '暂无'}",
                "",
                "用法:",
                "/dream on",
                "/dream off",
                "/dream status",
                "/dream run",
                "/dream doctor",
                "/dream report",
                "/dream delete",
            ]
        )


def _format_memory_view_item(item: dict, section: str) -> str:
    if section == "corrected_memories":
        return f"{item.get('key')}: {item.get('old_value')} -> {item.get('new_value')}"
    if section == "archived_or_suppressed":
        return f"{item.get('key')}: {item.get('action')} / {item.get('reason')}"
    value = str(item.get("value") or "")
    confidence = item.get("confidence")
    suffix = f" ({float(confidence):.2f})" if isinstance(confidence, (int, float)) and section == "pending_confirmation" else ""
    confirmed = " ✓" if item.get("confirmed") else ""
    return f"{item.get('key')}: {value}{suffix}{confirmed}"
