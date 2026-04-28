#!/usr/bin/env python3
"""
Rebuilt system-level test suite for AI Companion.

This suite is intentionally independent from legacy test scripts.
It enforces strict PASS/FAIL accounting and writes structured artifacts.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Coroutine

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass
class CaseResult:
    case_id: str
    name: str
    status: str  # PASS | FAIL | ERROR
    detail: str
    duration_sec: float
    log_file: str


class FakeModel:
    """Offline model used for deterministic system tests."""

    def __init__(self):
        self.chat_calls: list[dict] = []

    @property
    def provider(self) -> str:
        return "fake"

    async def chat(self, messages: list[dict], system_prompt: str = "", **kwargs) -> str:
        self.chat_calls.append({"messages": messages, "system_prompt": system_prompt})
        text = messages[-1].get("content", "") if messages else ""

        # Refusal / proactive / semantic prompts
        if "NO_FACT" in text:
            return "NO_FACT"
        if "NO_CHANGE" in text:
            return "NO_CHANGE"
        if "NO_MOMENT" in text:
            return "NO_MOMENT"
        if "should_contact" in text:
            return '{"should_contact": true, "reason": "test", "urgency": "low"}'
        if '"opening"' in text and '"topic"' in text and '"ending"' in text:
            return '{"opening":"hi","topic":"","ending":"there"}'
        if "-5 到 +5" in text or "只输出数字" in text:
            return "0"

        return "offline-reply"

    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        return [[0.0, 0.0, 0.0] for _ in texts]

    async def close(self):
        return None


class SystemTestSuite:
    def __init__(self, root: Path):
        self.root = root
        ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        self.artifacts_dir = self.root / ".artifacts" / f"system-test-rebuilt-{ts}"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.results: list[CaseResult] = []
        self.python_bin = Path(sys.executable)

    def _write_log(self, case_id: str, content: str) -> Path:
        path = self.artifacts_dir / f"{case_id}.log"
        path.write_text(content, encoding="utf-8")
        return path

    def _run_cmd(
        self,
        cmd: list[str],
        cwd: Path | None = None,
        env: dict | None = None,
        timeout: int = 120,
    ) -> tuple[int, str, str, bool]:
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd or self.root),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return proc.returncode, proc.stdout, proc.stderr, False
        except subprocess.TimeoutExpired as exc:
            return 124, exc.stdout or "", exc.stderr or "", True

    def _fmt_cmd_output(
        self,
        cmd: list[str],
        rc: int,
        stdout: str,
        stderr: str,
        timed_out: bool,
    ) -> str:
        parts = [
            f"$ {' '.join(shlex.quote(c) for c in cmd)}",
            f"return_code: {rc}",
            f"timed_out: {timed_out}",
            "",
            "----- STDOUT -----",
            stdout or "<empty>",
            "",
            "----- STDERR -----",
            stderr or "<empty>",
            "",
        ]
        return "\n".join(parts)

    def _run_case(
        self,
        case_id: str,
        name: str,
        fn: Callable[[], tuple[bool, str, str]] | Callable[[], Coroutine[None, None, tuple[bool, str, str]]],
    ) -> None:
        start = time.time()
        status = "ERROR"
        detail = ""
        log_text = ""
        try:
            if inspect.iscoroutinefunction(fn):
                passed, detail, log_text = asyncio.run(fn())  # type: ignore[arg-type]
            else:
                passed, detail, log_text = fn()  # type: ignore[misc]
            status = "PASS" if passed else "FAIL"
        except Exception as exc:
            status = "ERROR"
            detail = f"{type(exc).__name__}: {exc}"
            log_text = traceback.format_exc()

        duration = time.time() - start
        log_path = self._write_log(case_id, log_text)
        self.results.append(
            CaseResult(
                case_id=case_id,
                name=name,
                status=status,
                detail=detail,
                duration_sec=round(duration, 3),
                log_file=str(log_path),
            )
        )
        print(f"[{status}] {case_id} {name} :: {detail}")

    def run(self) -> int:
        print("=" * 80)
        print("AI Companion Rebuilt System Test Suite")
        print("=" * 80)
        print(f"Root: {self.root}")
        print(f"Python: {self.python_bin}")
        print(f"Artifacts: {self.artifacts_dir}")
        print("")

        self._run_case("T00", "Legacy test scripts removed", self.case_legacy_tests_removed)
        self._run_case("T01", "CLI help", self.case_cli_help)
        self._run_case("T02", "CLI status", self.case_cli_status)
        self._run_case("T03", "CLI bot list", self.case_cli_bot_list)
        self._run_case("T04", "Config loader", self.case_config_loader)
        self._run_case("T05", "ModelFactory provider registry", self.case_model_factory_registry)
        self._run_case("T06", "Context compressor behavior", self.case_context_compressor)
        self._run_case("T07", "Memory engine offline roundtrip", self.case_memory_engine_roundtrip)
        self._run_case("T08", "BotInstance offline full flow", self.case_bot_instance_offline)
        self._run_case("T09", "Proactive silent mode semantics", self.case_proactive_silent_mode)
        self._run_case("T10", "Proactive no duplicate send", self.case_proactive_no_duplicate_send)
        self._run_case("T11", "Model entrypoints use factory", self.case_model_entrypoints_use_factory)
        self._run_case("T12", "Gateway lifecycle + admin API", self.case_gateway_lifecycle_admin_api)
        self._run_case("T13", "UI provider contract match", self.case_ui_provider_contract)
        self._run_case("T14", "UI clear-all memory implementation", self.case_ui_clear_all_implemented)
        self._run_case("T15", "Frontend production build", self.case_frontend_build)
        self._run_case("T16", "No hardcoded Feishu credentials", self.case_no_hardcoded_feishu_credentials)
        self._run_case("T17", "Life daily progression + event journal", self.case_life_journal_records)
        self._run_case("T18", "Life fallback daily + fixed major probability", self.case_life_fallback_and_fixed_major_probability)
        self._run_case("T19", "Life scenario cooldown blocks repeats", self.case_life_scenario_cooldown)
        self._run_case("T20", "Persona updater applies patch", self.case_persona_updater_patch)
        self._run_case("T21", "Life timeline context enters persona prompt", self.case_life_context_persona_prompt)
        self._run_case("T22", "BotInstance refreshes runtime persona settings", self.case_bot_instance_runtime_persona_refresh)
        self._run_case("T23", "Life daily event lenient JSON parsing", self.case_life_daily_lenient_json)
        self._run_case("T24", "Proactive missing sender is not counted as sent", self.case_proactive_missing_sender_not_sent)
        self._run_case("T25", "Life daily events hard cap at 100", self.case_life_daily_events_hard_cap)
        self._run_case("T26", "Major fallback events are concrete", self.case_major_fallback_events_concrete)
        self._run_case("T27", "Unexpected major events use separate low-probability channel", self.case_unexpected_major_events_low_probability)

        return self._finalize()

    def _finalize(self) -> int:
        totals = {
            "total": len(self.results),
            "pass": sum(1 for r in self.results if r.status == "PASS"),
            "fail": sum(1 for r in self.results if r.status == "FAIL"),
            "error": sum(1 for r in self.results if r.status == "ERROR"),
        }
        failed = totals["fail"] + totals["error"]

        json_report = {
            "generated_at": datetime.now().isoformat(),
            "root": str(self.root),
            "python": str(self.python_bin),
            "artifacts_dir": str(self.artifacts_dir),
            "totals": totals,
            "results": [asdict(r) for r in self.results],
        }
        report_json_path = self.artifacts_dir / "system_test_report.json"
        report_json_path.write_text(json.dumps(json_report, ensure_ascii=False, indent=2), encoding="utf-8")

        md_lines = [
            "# Rebuilt System Test Report",
            "",
            f"- generated_at: `{json_report['generated_at']}`",
            f"- python: `{self.python_bin}`",
            f"- artifacts_dir: `{self.artifacts_dir}`",
            "",
            "## Totals",
            "",
            f"- total: {totals['total']}",
            f"- pass: {totals['pass']}",
            f"- fail: {totals['fail']}",
            f"- error: {totals['error']}",
            "",
            "## Cases",
            "",
            "| ID | Name | Status | Detail | Log |",
            "|---|---|---|---|---|",
        ]
        for r in self.results:
            md_lines.append(
                f"| {r.case_id} | {r.name} | {r.status} | {r.detail} | `{Path(r.log_file).name}` |"
            )

        report_md_path = self.artifacts_dir / "system_test_report.md"
        report_md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

        print("")
        print("=" * 80)
        print("Rebuilt system test summary")
        print("=" * 80)
        print(f"PASS: {totals['pass']}  FAIL: {totals['fail']}  ERROR: {totals['error']}")
        print(f"JSON report: {report_json_path}")
        print(f"MD report:   {report_md_path}")
        return 0 if failed == 0 else 1

    # ------------------------------------------------------------------
    # Test cases
    # ------------------------------------------------------------------

    def case_legacy_tests_removed(self) -> tuple[bool, str, str]:
        legacy = sorted((self.root / "tests").glob("test_*.py"))
        passed = len(legacy) == 0
        detail = "no legacy tests found" if passed else f"found {len(legacy)} legacy test files"
        log = "\n".join(str(p) for p in legacy) if legacy else "none"
        return passed, detail, log

    def case_cli_help(self) -> tuple[bool, str, str]:
        cmd = [str(self.python_bin), "-m", "ai_companion", "--help"]
        rc, out, err, to = self._run_cmd(cmd, timeout=40)
        passed = (rc == 0) and ("gateway" in out) and ("setup" in out) and ("bot" in out)
        detail = "commands listed" if passed else "help output missing expected commands"
        return passed, detail, self._fmt_cmd_output(cmd, rc, out, err, to)

    def case_cli_status(self) -> tuple[bool, str, str]:
        cmd = [str(self.python_bin), "-m", "ai_companion", "status"]
        rc, out, err, to = self._run_cmd(cmd, timeout=40)
        passed = (rc == 0) and ("已配置 Bot" in out)
        detail = "status command healthy" if passed else "status command failed"
        return passed, detail, self._fmt_cmd_output(cmd, rc, out, err, to)

    def case_cli_bot_list(self) -> tuple[bool, str, str]:
        cmd = [str(self.python_bin), "-m", "ai_companion", "bot", "list"]
        rc, out, err, to = self._run_cmd(cmd, timeout=40)
        passed = (rc == 0) and ("Bot" in out)
        detail = "bot list available" if passed else "bot list unavailable"
        return passed, detail, self._fmt_cmd_output(cmd, rc, out, err, to)

    def case_config_loader(self) -> tuple[bool, str, str]:
        from ai_companion.config.loader import Config

        cfg = Config()
        bots = cfg.get_enabled_bots()
        model_cfg = cfg.get_model_config()
        has_required = all(k in model_cfg for k in ("provider", "api_key", "base_url", "model"))
        passed = bool(bots) and has_required
        detail = f"enabled_bots={len(bots)} provider={model_cfg.get('provider', '<none>')}"
        log = json.dumps(
            {
                "enabled_bot_ids": [b.get("id") for b in bots],
                "model_cfg_keys": sorted(model_cfg.keys()),
            },
            ensure_ascii=False,
            indent=2,
        )
        return passed, detail, log

    def case_model_factory_registry(self) -> tuple[bool, str, str]:
        from ai_companion.model.factory import ModelFactory

        providers = set(ModelFactory.list_providers())
        expected = {"minimax", "openai", "claude", "ollama", "custom"}
        passed = providers == expected
        detail = f"providers={sorted(providers)}"
        log = json.dumps({"providers": sorted(providers), "expected": sorted(expected)}, indent=2)
        return passed, detail, log

    def case_context_compressor(self) -> tuple[bool, str, str]:
        from ai_companion.context.compressor import ContextCompressor

        compressor = ContextCompressor(
            {
                "threshold_percent": 0.75,
                "tail_token_budget": 4000,
                "protect_first_n": 2,
                "model_context": 128000,
            }
        )
        short_msgs = [{"role": "user", "content": "hello"}]
        short_should = compressor.should_compress(short_msgs)

        long_payload = "测试" * 200
        long_msgs = [{"role": "user", "content": long_payload} for _ in range(400)]
        long_should = compressor.should_compress(long_msgs)

        passed = (short_should is False) and (long_should is True)
        detail = f"short={short_should} long={long_should}"
        log = json.dumps(
            {
                "short_should_compress": short_should,
                "long_should_compress": long_should,
                "long_message_count": len(long_msgs),
                "single_message_chars": len(long_payload),
            },
            ensure_ascii=False,
            indent=2,
        )
        return passed, detail, log

    async def case_memory_engine_roundtrip(self) -> tuple[bool, str, str]:
        from ai_companion.memory.engine import MemoryEngine

        with tempfile.TemporaryDirectory(prefix="sys-test-memory-") as td:
            root = Path(td)
            config = {
                "embedding": "none",
                "max_working_turns": 20,
                "hard_limit_chars": 5000,
                "soft_limit_chars": 3000,
            }
            engine = MemoryEngine(bot_id="sys_memory_bot", memory_dir=root, config=config)
            await engine.init()
            engine.start_session("sid-system")
            await engine.on_message("hello", "world")
            context = await engine.load_context("hello again")
            status = await engine.get_memory_status()
            await engine.close()

            memory_dir = root / "sys_memory_bot" / "memory"
            files = [memory_dir / "working.db", memory_dir / "episodic.db", memory_dir / "semantic.db"]

            passed = (
                "working_history" in context
                and isinstance(context.get("working_history"), list)
                and status.get("working_turns", 0) >= 1
                and all(p.exists() for p in files)
            )
            detail = f"working_turns={status.get('working_turns', 0)}"
            log = json.dumps(
                {
                    "context_keys": sorted(context.keys()),
                    "status": status,
                    "memory_dir": str(memory_dir),
                    "db_files": [str(p) for p in files],
                },
                ensure_ascii=False,
                indent=2,
            )
            return passed, detail, log

    async def case_bot_instance_offline(self) -> tuple[bool, str, str]:
        from ai_companion.bot.instance import BotInstance
        from ai_companion.config.loader import Config

        cfg = Config()
        enabled = cfg.get_enabled_bots()
        if not enabled:
            return False, "no enabled bots in config", "empty bot list"

        bot_cfg = enabled[0]
        fake_model = FakeModel()
        memory_config = {
            "embedding": "none",
            "max_working_turns": 20,
            "hard_limit_chars": 5000,
            "soft_limit_chars": 3000,
        }

        with tempfile.TemporaryDirectory(prefix="sys-test-bot-") as td:
            data_dir = Path(td)
            bot = BotInstance(
                config=bot_cfg,
                model=fake_model,
                memory_config=memory_config,
                data_dir=data_dir,
                refusal_enabled=False,
            )

            try:
                await bot.init()
                reply = await bot.handle_message("system test ping")
                await asyncio.sleep(0.6)
                memory_status = await bot.memory.get_memory_status() if bot.memory else {}
                life_loader_ok = getattr(bot.life_engine, "_persona_loader", None) is not None
                proactive_running = bool(bot.proactive_scheduler and bot.proactive_scheduler.get_status().get("running"))
                life_running = bool(bot.life_scheduler and bot.life_scheduler.get_status().get("running"))
                chat_prompts = [
                    call.get("system_prompt", "")
                    for call in fake_model.chat_calls
                    if call.get("messages")
                    and call["messages"][-1].get("content") == "system test ping"
                ]
                prompt_has_life_context = any("当前人生轨迹状态" in prompt for prompt in chat_prompts)

                passed = (
                    isinstance(reply, str)
                    and len(reply) > 0
                    and memory_status.get("working_turns", 0) >= 1
                    and proactive_running
                    and life_running
                    and life_loader_ok
                    and prompt_has_life_context
                )
                detail = (
                    f"reply_len={len(reply)} working_turns={memory_status.get('working_turns', 0)} "
                    f"life_loader_ok={life_loader_ok} prompt_life_context={prompt_has_life_context}"
                )
                log = json.dumps(
                    {
                        "bot_id": bot.id,
                        "reply": reply,
                        "memory_status": memory_status,
                        "proactive_running": proactive_running,
                        "life_running": life_running,
                        "life_loader_ok": life_loader_ok,
                        "prompt_excerpt": chat_prompts[-1][:800] if chat_prompts else "",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                return passed, detail, log
            finally:
                await bot.close()

    def case_proactive_silent_mode(self) -> tuple[bool, str, str]:
        from ai_companion.proactive.config import ProactiveConfig

        with tempfile.TemporaryDirectory(prefix="sys-test-proactive-silent-") as td:
            persona_dir = Path(td) / "persona"
            persona_dir.mkdir(parents=True, exist_ok=True)
            config_path = persona_dir / "proactive.json"
            config_path.write_text(
                json.dumps(
                    {
                        "enabled": True,
                        "mode": "silent",
                        "scheduler": {"check_interval_seconds": 60},
                        "triggers": {"idle_reminder": {"enabled": True, "idle_hours": 24}},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            cfg = ProactiveConfig(persona_dir)
            passed = cfg.is_active is False
            detail = f"enabled={cfg.enabled} mode={cfg.mode} is_active={cfg.is_active}"
            return passed, detail, config_path.read_text(encoding="utf-8")

    async def case_proactive_no_duplicate_send(self) -> tuple[bool, str, str]:
        from ai_companion.proactive.config import ProactiveConfig
        from ai_companion.proactive.engine import ProactiveDecision, ProactiveEngine
        from ai_companion.proactive.scheduler import ProactiveScheduler
        from ai_companion.proactive.state import ProactiveState
        import ai_companion.proactive.engine as proactive_engine_module

        with tempfile.TemporaryDirectory(prefix="sys-test-proactive-dup-") as td:
            root = Path(td)
            persona_dir = root / "persona"
            persona_dir.mkdir(parents=True, exist_ok=True)
            (persona_dir / "proactive.json").write_text(
                json.dumps(
                    {
                        "enabled": True,
                        "mode": "active",
                        "scheduler": {
                            "check_interval_seconds": 60,
                            "idle_threshold_hours": 1,
                            "max_daily": 5,
                            "min_interval_hours": 1,
                            "max_idle_days": 7,
                        },
                        "triggers": {"idle_reminder": {"enabled": True, "idle_hours": 1}},
                        "preferred_contact_times": ["00:00-23:59"],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            cfg = ProactiveConfig(persona_dir)
            state = ProactiveState("dup_bot", root)
            engine = ProactiveEngine(
                bot_id="dup_bot",
                config=cfg,
                state=state,
                model=None,
                memory=None,
                personality_type="default",
            )
            scheduler = ProactiveScheduler(engine)
            scheduler._is_golden_hour = lambda: True  # force path

            send_counter = {"count": 0}

            async def _sender(message: str):
                send_counter["count"] += 1
                return True

            async def _should_contact():
                return ProactiveDecision(True, "test", "low")

            async def _generate_message(reason: str):
                return "hello"

            engine._platform_sender = _sender
            engine.should_contact = _should_contact  # type: ignore[method-assign]
            engine.generate_message = _generate_message  # type: ignore[method-assign]

            original_random = proactive_engine_module.random.random
            proactive_engine_module.random.random = lambda: 0.0
            try:
                await scheduler._tick()
            finally:
                proactive_engine_module.random.random = original_random

            passed = send_counter["count"] == 1
            detail = f"send_count={send_counter['count']}"
            log = json.dumps(send_counter, ensure_ascii=False, indent=2)
            return passed, detail, log

    async def case_life_journal_records(self) -> tuple[bool, str, str]:
        from ai_companion.proactive.life_config import LifeConfig
        from ai_companion.proactive.life_engine import LifeEngine
        from ai_companion.proactive.life_state import LifeState

        class _DailyEventModel:
            async def chat(self, messages: list[dict], system_prompt: str = "", **kwargs) -> str:
                text = messages[-1].get("content", "") if messages else ""
                if "输出一个 JSON 数组" in text:
                    return json.dumps(
                        [
                            {
                                "description": "在公园散步并听了喜欢的音乐",
                                "mood_before": "平静",
                                "mood_after": "轻松",
                                "importance": 3.0,
                                "shareable": True,
                                "topic_prompt": "今天去公园散步，意外地很治愈。",
                                "related_to_user": False,
                            }
                        ],
                        ensure_ascii=False,
                    )
                return "[]"

        with tempfile.TemporaryDirectory(prefix="sys-test-life-journal-") as td:
            root = Path(td)
            state = LifeState("life_journal_bot", root)
            state.current_date = "2024-01-01"
            state.last_daily_tick = datetime.now() - timedelta(seconds=3)

            cfg = LifeConfig(
                daily_interval_seconds=1,
                major_interval_seconds=999999,
                time_ratio=86400,
                time_ratio_warning_threshold=999999,
            )
            model = _DailyEventModel()
            engine = LifeEngine(
                bot_id="life_journal_bot",
                config=cfg,
                state=state,
                model=model,
                memory=None,
                persona_dir=None,
            )

            event = await engine.tick_daily()
            state_data = state.to_dict()
            journal = state_data.get("life_journal", [])
            day_records = [item for item in journal if item.get("record_type") == "day_passed"]
            event_records = [item for item in journal if item.get("record_type") == "daily_event"]

            unique_day_count = len({item.get("date") for item in day_records})
            passed = (
                event is not None
                and len(state_data.get("life_events", [])) >= 1
                and len(day_records) >= 2
                and unique_day_count == len(day_records)
                and len(event_records) >= 1
            )
            detail = (
                f"day_records={len(day_records)} unique_day_count={unique_day_count} "
                f"event_records={len(event_records)}"
            )
            log = json.dumps(
                {
                    "event_generated": event.to_dict() if event else None,
                    "current_date": state_data.get("current_date"),
                    "life_events_count": len(state_data.get("life_events", [])),
                    "journal_count": len(journal),
                    "day_records": day_records[-5:],
                    "event_records": event_records[-5:],
                },
                ensure_ascii=False,
                indent=2,
            )
            return passed, detail, log

    async def case_life_fallback_and_fixed_major_probability(self) -> tuple[bool, str, str]:
        from ai_companion.proactive.life_config import LifeConfig
        from ai_companion.proactive.life_engine import LifeEngine
        from ai_companion.proactive.life_state import LifeState

        class _NoEventModel:
            async def chat(self, messages: list[dict], system_prompt: str = "", **kwargs) -> str:
                text = messages[-1].get("content", "") if messages else ""
                if "输出一个 JSON 数组" in text:
                    return "[]"
                if '"is_major": true或false' in text:
                    return '{"is_major": false, "reason": "stable"}'
                return "[]"

        with tempfile.TemporaryDirectory(prefix="sys-test-life-fallback-") as td:
            root = Path(td)
            state = LifeState("life_fallback_bot", root)
            state.current_date = "2024-01-05"
            state.last_daily_tick = datetime.now() - timedelta(seconds=2)
            state.bot_age_days = 10
            state.last_daily_event_date = "2024-01-03"

            cfg = LifeConfig(
                daily_interval_seconds=1,
                major_interval_seconds=1,
                time_ratio=86400,
                time_ratio_warning_threshold=999999,
                daily_event_min_gap_days=2,
                major_event_fixed_probability=1.0,
            )
            engine = LifeEngine(
                bot_id="life_fallback_bot",
                config=cfg,
                state=state,
                model=_NoEventModel(),
                memory=None,
                persona_dir=None,
            )

            daily_event = await engine.tick_daily()
            major_event = await engine.tick_major()
            state_data = state.to_dict()

            journal = state_data.get("life_journal", [])
            day_records = [item for item in journal if item.get("record_type") == "day_passed"]
            daily_records = [item for item in journal if item.get("record_type") == "daily_event"]
            major_records = [item for item in journal if item.get("record_type") == "major_event"]
            daily_description = daily_event.description if daily_event else ""
            abstract_tokens = ["状态更稳定", "有一些变化", "发生了一件具体的小事"]
            has_specific_detail = (
                bool(daily_event and daily_event.scenario_key and daily_event.source == "fallback")
                and bool(daily_description.strip())
                and not any(token in daily_description for token in abstract_tokens)
            )

            passed = (
                daily_event is not None
                and major_event is not None
                and has_specific_detail
                and len(state_data.get("life_events", [])) >= 1
                and len(state_data.get("major_life_events", [])) >= 1
                and len(day_records) >= 1
                and len(daily_records) >= 1
                and len(major_records) >= 1
            )
            detail = (
                f"daily_event={'yes' if daily_event else 'no'} "
                f"specific_detail={'yes' if has_specific_detail else 'no'} "
                f"major_event={'yes' if major_event else 'no'} "
                f"daily_records={len(daily_records)} major_records={len(major_records)}"
            )
            log = json.dumps(
                {
                    "daily_event": daily_event.to_dict() if daily_event else None,
                    "major_event": major_event.to_dict() if major_event else None,
                    "life_events_count": len(state_data.get("life_events", [])),
                    "major_life_events_count": len(state_data.get("major_life_events", [])),
                    "day_records_tail": day_records[-3:],
                    "daily_records_tail": daily_records[-3:],
                    "major_records_tail": major_records[-3:],
                },
                ensure_ascii=False,
                indent=2,
            )
            return passed, detail, log

    def case_life_scenario_cooldown(self) -> tuple[bool, str, str]:
        from ai_companion.proactive.life_config import LifeConfig
        from ai_companion.proactive.life_engine import LifeEngine
        from ai_companion.proactive.life_state import LifeState

        with tempfile.TemporaryDirectory(prefix="sys-test-life-cooldown-") as td:
            root = Path(td)
            state = LifeState("life_cooldown_bot", root)
            state.current_date = "2024-02-01"
            cfg = LifeConfig(
                daily_interval_seconds=1,
                major_interval_seconds=999999,
                time_ratio=1,
                scenario_cooldown_days=30,
            )
            engine = LifeEngine("life_cooldown_bot", cfg, state, model=FakeModel())

            first = engine._build_forced_daily_event()
            if not first:
                return False, "first fallback unavailable", "{}"
            state.add_event(first)
            state.current_date = "2024-02-02"

            blocked = engine._forbidden_daily_scenario_keys()
            second = engine._build_forced_daily_event(exclude_scenario_keys=blocked)

            for item in engine._daily_scenario_catalog():
                state.record_scenario(item["key"], major=False)
            none_left = engine._build_forced_daily_event(exclude_scenario_keys=engine._forbidden_daily_scenario_keys())

            passed = (
                first.scenario_key
                and second is not None
                and second.scenario_key != first.scenario_key
                and none_left is None
            )
            detail = (
                f"first={first.scenario_key} "
                f"second={second.scenario_key if second else '<none>'} "
                f"none_left={none_left is None}"
            )
            log = json.dumps(
                {
                    "first": first.to_dict(),
                    "second": second.to_dict() if second else None,
                    "blocked": sorted(blocked),
                    "scenario_history": state.get_scenario_history(),
                    "none_left": none_left.to_dict() if none_left else None,
                },
                ensure_ascii=False,
                indent=2,
            )
            return passed, detail, log

    async def case_persona_updater_patch(self) -> tuple[bool, str, str]:
        from ai_companion.proactive.life_config import LifeConfig
        from ai_companion.proactive.life_engine import LifeEngine, PersonaUpdater
        from ai_companion.proactive.life_state import LifeState, MajorLifeEvent

        class _PatchModel:
            async def chat(self, messages: list[dict], system_prompt: str = "", **kwargs) -> str:
                return json.dumps(
                    {
                        "profile_updates": {"relationship_to_user": "更信任的朋友"},
                        "backstory_append": ["经历了一次重要选择，开始更认真地看待长期规划。"],
                        "backstory_updates": {},
                        "values_updates": {"growth": "重视长期主义"},
                        "speaking_style_updates": {},
                    },
                    ensure_ascii=False,
                )

        with tempfile.TemporaryDirectory(prefix="sys-test-persona-patch-") as td:
            root = Path(td)
            persona_dir = root / "persona"
            persona_dir.mkdir(parents=True, exist_ok=True)
            original = {
                "profile.json": {"name": "测试", "relationship_to_user": "朋友", "settings": {"tone": "calm"}},
                "backstory.json": {"summary": "原始背景", "key_moments": ["原始关键经历"]},
                "values.json": {"baseline": "诚实"},
                "speaking_style.json": {"tone": "平静"},
            }
            for name, payload in original.items():
                (persona_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            state = LifeState("persona_patch_bot", root)
            cfg = LifeConfig()
            engine = LifeEngine("persona_patch_bot", cfg, state, model=_PatchModel(), persona_dir=persona_dir)
            event = MajorLifeEvent(
                description="做出了一个长期规划上的关键决定",
                mood_before="犹豫",
                mood_after="坚定",
                importance=9,
                scenario_key="life_planning_turn",
            )

            ok = await PersonaUpdater(engine).update_all(event)
            profile = json.loads((persona_dir / "profile.json").read_text(encoding="utf-8"))
            backstory = json.loads((persona_dir / "backstory.json").read_text(encoding="utf-8"))
            values = json.loads((persona_dir / "values.json").read_text(encoding="utf-8"))
            speaking = json.loads((persona_dir / "speaking_style.json").read_text(encoding="utf-8"))

            passed = (
                ok
                and profile.get("relationship_to_user") == "更信任的朋友"
                and profile.get("settings") == {"tone": "calm"}
                and "原始关键经历" in backstory.get("key_moments", [])
                and "经历了一次重要选择，开始更认真地看待长期规划。" in backstory.get("key_moments", [])
                and values.get("baseline") == "诚实"
                and values.get("growth") == "重视长期主义"
                and speaking == original["speaking_style.json"]
            )
            detail = f"ok={ok} key_moments={len(backstory.get('key_moments', []))}"
            log = json.dumps(
                {
                    "profile": profile,
                    "backstory": backstory,
                    "values": values,
                    "speaking_style": speaking,
                },
                ensure_ascii=False,
                indent=2,
            )
            return passed, detail, log

    def case_life_context_persona_prompt(self) -> tuple[bool, str, str]:
        from ai_companion.persona.engine import PersonaEngine
        from ai_companion.persona.loader import PersonaLoader
        from ai_companion.proactive.life_config import LifeConfig
        from ai_companion.proactive.life_engine import LifeEngine
        from ai_companion.proactive.life_state import LifeEvent, LifeState, MajorLifeEvent

        with tempfile.TemporaryDirectory(prefix="sys-test-life-prompt-") as td:
            root = Path(td)
            persona_dir = root / "persona"
            persona_dir.mkdir(parents=True, exist_ok=True)
            files = {
                "profile.json": {
                    "name": "轨迹实验君",
                    "age": 24,
                    "birth_date": "2002-11-03",
                    "occupation": "产品设计师",
                    "personality_tags": ["理性", "敏感"],
                    "relationship_to_user": "朋友",
                },
                "backstory.json": {"key_moments": []},
                "values.json": {"non_negotiable": []},
                "speaking_style.json": {"tone": "自然"},
            }
            for name, payload in files.items():
                (persona_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            state = LifeState("life_prompt_bot", root)
            state.birth_date = "2002-11-03"
            state.current_date = "2030-05-08"
            state.day_of_week = "周三"
            state.year = 2030
            state.current_month = 5
            state.bot_age_days = 985
            state.initial_age = 24
            state.bot_mood = "平静"
            state.bot_current_activity = "在整理这一阶段的生活变化"
            state.add_event(
                LifeEvent(
                    timestamp="2030-05-07T09:00:00",
                    description="早高峰地铁晚点，临时改走路去公司",
                    importance=3,
                    scenario_key="commute_delay",
                )
            )
            state.add_major_event(
                MajorLifeEvent(
                    timestamp="2030-05-06T20:00:00",
                    description="决定把产品设计方向转向长期作品集项目",
                    importance=9,
                    scenario_key="career_direction_shift",
                )
            )

            engine = LifeEngine("life_prompt_bot", LifeConfig(), state, model=FakeModel(), persona_dir=persona_dir)
            engine.set_bot_info("轨迹实验君", 24, "产品设计师", "理性, 敏感")
            status = engine.get_status()
            prompt = PersonaEngine(PersonaLoader(persona_dir).load()).build_system_prompt(life_context=status)

            passed = (
                status.get("bot_real_age") == 27
                and "你是轨迹实验君，27岁，产品设计师。" in prompt
                and "你是轨迹实验君，24岁，产品设计师。" not in prompt
                and "当前日期：2030-05-08（周三）" in prompt
                and "出生日期：2002-11-03" in prompt
                and "profile.age 只是初始年龄" in prompt
                and "决定把产品设计方向转向长期作品集项目" in prompt
                and "早高峰地铁晚点，临时改走路去公司" in prompt
            )
            detail = f"bot_real_age={status.get('bot_real_age')} prompt_len={len(prompt)}"
            log = json.dumps(
                {
                    "status": status,
                    "prompt": prompt,
                },
                ensure_ascii=False,
                indent=2,
            )
            return passed, detail, log

    async def case_bot_instance_runtime_persona_refresh(self) -> tuple[bool, str, str]:
        from ai_companion.bot.instance import BotInstance

        def _write_persona(persona_dir: Path, profile: dict, backstory: dict | None = None):
            payloads = {
                "profile.json": profile,
                "backstory.json": backstory or {"key_moments": []},
                "values.json": {"non_negotiable": ["不伤害他人"]},
                "speaking_style.json": {"tone": "自然"},
                "proactive.json": {"enabled": True, "mode": "silent"},
                "life.json": {
                    "daily_interval_seconds": 999999,
                    "major_interval_seconds": 999999,
                    "time_ratio": 1,
                    "birth_date": profile.get("birth_date"),
                },
            }
            for name, payload in payloads.items():
                (persona_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        with tempfile.TemporaryDirectory(prefix="sys-test-runtime-refresh-") as td:
            root = Path(td)
            bot_id = "runtime_refresh_bot"
            persona_dir = root / bot_id / "persona"
            persona_dir.mkdir(parents=True, exist_ok=True)

            _write_persona(
                persona_dir,
                {
                    "id": bot_id,
                    "name": "旧名字",
                    "age": 24,
                    "birth_date": "2002-11-03",
                    "occupation": "旧职业",
                    "personality_tags": ["高冷"],
                    "relationship_to_user": "朋友",
                },
            )

            fake_model = FakeModel()
            bot = BotInstance(
                config={"id": bot_id, "name": "旧名字", "data_dir": str(root)},
                model=fake_model,
                memory_config=None,
                data_dir=root,
                refusal_enabled=False,
            )

            try:
                await bot.init(start_schedulers=False)
                bot.life_state.current_date = "2030-05-08"
                bot.life_state.day_of_week = "周三"
                bot.life_state.year = 2030
                bot.life_state.current_month = 5

                _write_persona(
                    persona_dir,
                    {
                        "id": bot_id,
                        "name": "新名字",
                        "age": 24,
                        "birth_date": "2002-11-03",
                        "occupation": "新职业",
                        "personality_tags": ["温柔"],
                        "relationship_to_user": "朋友",
                    },
                    {"key_moments": ["刚刚经历了一次重要设定更新"]},
                )

                reply = await bot.handle_message("runtime refresh ping")
                prompts = [
                    call.get("system_prompt", "")
                    for call in fake_model.chat_calls
                    if call.get("messages")
                    and call["messages"][-1].get("content") == "runtime refresh ping"
                ]
                prompt = prompts[-1] if prompts else ""

                passed = (
                    reply == "offline-reply"
                    and "你是新名字，27岁，新职业。" in prompt
                    and "刚刚经历了一次重要设定更新" in prompt
                    and "旧名字" not in prompt
                    and bot.name == "新名字"
                    and getattr(bot.life_engine, "occupation", "") == "新职业"
                    and getattr(bot.proactive_engine, "personality_type", "") == "温柔"
                )
                detail = (
                    f"prompt_new={'新名字' in prompt} "
                    f"life_occupation={getattr(bot.life_engine, 'occupation', '')} "
                    f"proactive_personality={getattr(bot.proactive_engine, 'personality_type', '')}"
                )
                log = json.dumps(
                    {
                        "reply": reply,
                        "prompt": prompt,
                        "bot_name": bot.name,
                        "life_engine": {
                            "bot_name": getattr(bot.life_engine, "bot_name", None),
                            "occupation": getattr(bot.life_engine, "occupation", None),
                            "personality_type": getattr(bot.life_engine, "_personality_type", None),
                        },
                        "proactive_engine": {
                            "bot_name": getattr(bot.proactive_engine, "bot_name", None),
                            "occupation": getattr(bot.proactive_engine, "occupation", None),
                            "personality_type": getattr(bot.proactive_engine, "personality_type", None),
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                return passed, detail, log
            finally:
                await bot.close()

    async def case_life_daily_lenient_json(self) -> tuple[bool, str, str]:
        from ai_companion.proactive.life_config import LifeConfig
        from ai_companion.proactive.life_engine import LifeEngine
        from ai_companion.proactive.life_state import LifeState

        class _BrokenJsonModel:
            async def chat(self, messages: list[dict], system_prompt: str = "", **kwargs) -> str:
                return """
[
  {
    "scenario_key": "commute_delay",
    "description": "早高峰地铁临时限流，通勤多花了20分钟"
    "mood_before": "平静",
    "mood_after": "有点疲惫",
    "importance": 3,
    "shareable": true,
    "topic_prompt": "今天通勤太刺激了。",
    "mood_tags": ["通勤", "早高峰"],
    "related_to_user": false
  }
]
"""

        with tempfile.TemporaryDirectory(prefix="sys-test-life-lenient-json-") as td:
            root = Path(td)
            state = LifeState("life_lenient_json_bot", root)
            state.current_date = "2024-01-01"
            cfg = LifeConfig()
            engine = LifeEngine("life_lenient_json_bot", cfg, state, model=_BrokenJsonModel())
            event = await engine.generate_daily_event()

            passed = (
                event is not None
                and event.scenario_key == "commute_delay"
                and event.description == "早高峰地铁临时限流，通勤多花了20分钟"
                and event.shareable is True
                and "通勤" in event.mood_tags
            )
            detail = f"event={'yes' if event else 'no'} scenario={event.scenario_key if event else '<none>'}"
            log = json.dumps(event.to_dict() if event else {}, ensure_ascii=False, indent=2)
            return passed, detail, log

    async def case_proactive_missing_sender_not_sent(self) -> tuple[bool, str, str]:
        from ai_companion.proactive.config import ProactiveConfig
        from ai_companion.proactive.engine import ProactiveEngine
        from ai_companion.proactive.state import ProactiveState

        with tempfile.TemporaryDirectory(prefix="sys-test-proactive-no-sender-") as td:
            root = Path(td)
            persona_dir = root / "persona"
            persona_dir.mkdir(parents=True, exist_ok=True)
            (persona_dir / "proactive.json").write_text(
                json.dumps({"enabled": True, "mode": "active"}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            state = ProactiveState("no_sender_bot", root)
            engine = ProactiveEngine(
                bot_id="no_sender_bot",
                config=ProactiveConfig(persona_dir),
                state=state,
                model=FakeModel(),
                memory=None,
            )

            sent = await engine._send_proactive_message("hello")
            passed = (
                sent is False
                and state.today_proactive_count == 0
                and state.total_proactive_sent == 0
                and state.unreplied_count == 0
            )
            detail = (
                f"sent={sent} today={state.today_proactive_count} "
                f"total={state.total_proactive_sent} unreplied={state.unreplied_count}"
            )
            log = json.dumps(state.to_dict(), ensure_ascii=False, indent=2)
            return passed, detail, log

    def case_life_daily_events_hard_cap(self) -> tuple[bool, str, str]:
        from ai_companion.proactive.life_config import LifeConfig
        from ai_companion.proactive.life_state import LifeEvent, LifeState

        with tempfile.TemporaryDirectory(prefix="sys-test-life-event-cap-") as td:
            root = Path(td)
            state = LifeState("life_event_cap_bot", root)
            for index in range(150):
                state.add_event(
                    LifeEvent(
                        description=f"daily event {index:03d}",
                        mood_before="平静",
                        mood_after="平静",
                        importance=2,
                        scenario_key=f"scenario_{index:03d}",
                    )
                )

            after_add = state.to_dict().get("life_events", [])
            state.prune_events(max_events=1000, max_context_bits=999999)
            after_prune = state.to_dict().get("life_events", [])

            cfg = LifeConfig(max_events=1000)
            state.prune_events(max_events=cfg.max_events, max_context_bits=999999)
            after_config_prune = state.to_dict().get("life_events", [])

            reloaded = LifeState("life_event_cap_bot", root)
            after_reload = reloaded.to_dict().get("life_events", [])

            passed = (
                len(after_add) == 100
                and after_add[0].get("description") == "daily event 050"
                and after_add[-1].get("description") == "daily event 149"
                and len(after_prune) == 100
                and len(after_config_prune) == 100
                and len(after_reload) == 100
            )
            detail = (
                f"after_add={len(after_add)} after_prune={len(after_prune)} "
                f"after_config_prune={len(after_config_prune)} after_reload={len(after_reload)}"
            )
            log = json.dumps(
                {
                    "first_after_add": after_add[0] if after_add else None,
                    "last_after_add": after_add[-1] if after_add else None,
                    "counts": {
                        "after_add": len(after_add),
                        "after_prune": len(after_prune),
                        "after_config_prune": len(after_config_prune),
                        "after_reload": len(after_reload),
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            return passed, detail, log

    def case_major_fallback_events_concrete(self) -> tuple[bool, str, str]:
        from ai_companion.proactive.life_config import LifeConfig
        from ai_companion.proactive.life_engine import LifeEngine
        from ai_companion.proactive.life_state import LifeState

        with tempfile.TemporaryDirectory(prefix="sys-test-major-concrete-") as td:
            root = Path(td)
            state = LifeState("major_concrete_bot", root)
            state.current_date = "2030-05-08"
            state.bot_mood = "平静"
            cfg = LifeConfig(major_event_fixed_probability=1.0, major_scenario_cooldown_days=0)
            engine = LifeEngine("major_concrete_bot", cfg, state, model=FakeModel())
            engine.set_bot_info("测试", 27, "产品设计师", "理性")

            descriptions = []
            failures = []
            abstract_phrases = ["更明确的选择", "人生规划出现", "长期犹豫", "换一种方式成长"]
            for scenario in engine._major_scenario_catalog():
                description = engine._render_major_scenario_description(scenario)
                descriptions.append({"key": scenario["key"], "description": description})
                if not engine._is_meaningful_major_description(description):
                    failures.append({"key": scenario["key"], "reason": "not_meaningful", "description": description})
                if any(phrase in description for phrase in abstract_phrases):
                    failures.append({"key": scenario["key"], "reason": "abstract_phrase", "description": description})

            event = engine._build_probability_major_event()
            old_keys = {
                "career_direction_choice",
                "life_planning_turn",
                "long_hesitation_settled",
                "important_feedback",
            }
            passed = (
                not failures
                and event is not None
                and event.scenario_key not in old_keys
                and engine._is_meaningful_major_description(event.description)
            )
            detail = (
                f"catalog={len(descriptions)} failures={len(failures)} "
                f"sample={event.scenario_key if event else '<none>'}"
            )
            log = json.dumps(
                {
                    "descriptions": descriptions,
                    "failures": failures,
                    "sample_event": event.to_dict() if event else None,
                },
                ensure_ascii=False,
                indent=2,
            )
            return passed, detail, log

    async def case_unexpected_major_events_low_probability(self) -> tuple[bool, str, str]:
        from ai_companion.proactive.life_config import LifeConfig
        from ai_companion.proactive.life_engine import LifeEngine
        from ai_companion.proactive.life_state import LifeState

        class _NoMajorModel(FakeModel):
            async def chat(self, messages: list[dict], system_prompt: str = "", **kwargs) -> str:
                self.chat_calls.append({"messages": messages, "system_prompt": system_prompt})
                return '{"is_major": false, "reason": "stable"}'

        with tempfile.TemporaryDirectory(prefix="sys-test-unexpected-major-") as td:
            root = Path(td)
            state = LifeState("unexpected_major_bot", root)
            state.current_date = "2030-05-08"
            state.bot_mood = "平静"
            cfg = LifeConfig(
                major_event_fixed_probability=0.0,
                major_scenario_cooldown_days=0,
                unexpected_event_probability=1.0,
                unexpected_event_cooldown_days=365,
            )
            engine = LifeEngine("unexpected_major_bot", cfg, state, model=_NoMajorModel())
            engine.set_bot_info("测试", 27, "项目经理", "理性")

            catalog_checks = []
            for scenario in engine._unexpected_major_scenario_catalog():
                description = engine._render_major_scenario_description(scenario)
                catalog_checks.append(
                    {
                        "key": scenario["key"],
                        "description": description,
                        "meaningful": engine._is_meaningful_major_description(description),
                    }
                )

            first_event = await engine.tick_major()
            state.current_date = "2030-05-09"
            second_event = await engine.tick_major()

            passed = (
                first_event is not None
                and first_event.source == "unexpected_probability"
                and first_event.scenario_key.startswith("unexpected_")
                and first_event.scenario_category == "unexpected"
                and engine._is_meaningful_major_description(first_event.description)
                and state.last_unexpected_event_date == "2030-05-08"
                and second_event is None
                and all(item["meaningful"] for item in catalog_checks)
            )
            detail = (
                f"first={first_event.scenario_key if first_event else '<none>'} "
                f"second={'yes' if second_event else 'no'} "
                f"last_unexpected={state.last_unexpected_event_date}"
            )
            log = json.dumps(
                {
                    "catalog_checks": catalog_checks,
                    "first_event": first_event.to_dict() if first_event else None,
                    "second_event": second_event.to_dict() if second_event else None,
                    "state": state.to_dict(),
                },
                ensure_ascii=False,
                indent=2,
            )
            return passed, detail, log

    def case_model_entrypoints_use_factory(self) -> tuple[bool, str, str]:
        main_text = (self.root / "ai_companion" / "main.py").read_text(encoding="utf-8")
        gateway_text = (self.root / "ai_companion" / "gateway" / "cmd.py").read_text(encoding="utf-8")

        main_uses_factory = "ModelFactory" in main_text
        gateway_uses_factory = "ModelFactory" in gateway_text
        main_direct_minimax = "MiniMaxAdapter(" in main_text
        gateway_direct_minimax = "MiniMaxAdapter(" in gateway_text

        passed = (
            main_uses_factory
            and gateway_uses_factory
            and not main_direct_minimax
            and not gateway_direct_minimax
        )
        detail = (
            f"main_factory={main_uses_factory} gateway_factory={gateway_uses_factory} "
            f"main_direct_minimax={main_direct_minimax} gateway_direct_minimax={gateway_direct_minimax}"
        )
        log = json.dumps(
            {
                "main_uses_factory": main_uses_factory,
                "gateway_uses_factory": gateway_uses_factory,
                "main_direct_minimax": main_direct_minimax,
                "gateway_direct_minimax": gateway_direct_minimax,
            },
            indent=2,
        )
        return passed, detail, log

    def case_gateway_lifecycle_admin_api(self) -> tuple[bool, str, str]:
        env = dict(os.environ)
        env["START_UI"] = "false"
        log_chunks: list[str] = []

        # Cleanup before start
        pre_stop_cmd = [str(self.python_bin), "-m", "ai_companion", "gateway", "stop"]
        rc, out, err, to = self._run_cmd(pre_stop_cmd, env=env, timeout=40)
        log_chunks.append(self._fmt_cmd_output(pre_stop_cmd, rc, out, err, to))

        start_cmd = [str(self.python_bin), "-m", "ai_companion", "gateway", "start"]
        s_rc, s_out, s_err, s_to = self._run_cmd(start_cmd, env=env, timeout=60)
        log_chunks.append(self._fmt_cmd_output(start_cmd, s_rc, s_out, s_err, s_to))

        api_ok = False
        api_payload = None
        api_error = ""
        try:
            deadline = time.time() + 20
            while time.time() < deadline:
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8642/api/v1/admin/bots", timeout=3) as resp:
                        body = resp.read().decode("utf-8", errors="replace")
                        api_payload = json.loads(body)
                        if isinstance(api_payload, dict) and "bots" in api_payload:
                            api_ok = True
                            break
                except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                    api_error = str(exc)
                time.sleep(1)
        finally:
            stop_cmd = [str(self.python_bin), "-m", "ai_companion", "gateway", "stop"]
            st_rc, st_out, st_err, st_to = self._run_cmd(stop_cmd, env=env, timeout=40)
            log_chunks.append(self._fmt_cmd_output(stop_cmd, st_rc, st_out, st_err, st_to))

            status_cmd = [str(self.python_bin), "-m", "ai_companion", "gateway", "status"]
            ss_rc, ss_out, ss_err, ss_to = self._run_cmd(status_cmd, env=env, timeout=20)
            log_chunks.append(self._fmt_cmd_output(status_cmd, ss_rc, ss_out, ss_err, ss_to))

        start_ok = (s_rc == 0) and ("已启动" in (s_out + s_err))
        stop_ok = ("已停止" in "".join(log_chunks))
        status_stopped = ("未运行" in "".join(log_chunks))
        passed = start_ok and api_ok and stop_ok and status_stopped
        detail = f"start_ok={start_ok} api_ok={api_ok} stop_ok={stop_ok} status_stopped={status_stopped}"

        log_chunks.append(
            json.dumps(
                {
                    "api_ok": api_ok,
                    "api_error": api_error,
                    "api_payload_preview": api_payload,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return passed, detail, "\n\n".join(log_chunks)

    def case_ui_provider_contract(self) -> tuple[bool, str, str]:
        from ai_companion.model.factory import ModelFactory

        settings_path = self.root / "ai-companion-ui" / "src" / "pages" / "Settings" / "Settings.tsx"
        text = settings_path.read_text(encoding="utf-8")
        block_match = re.search(r"const providerOptions = \[(.*?)\];", text, flags=re.S)
        if not block_match:
            return False, "providerOptions block not found", text

        values = re.findall(r"value:\s*'([^']+)'", block_match.group(1))
        ui_set = set(values)
        backend_set = set(ModelFactory.list_providers())
        passed = ui_set == backend_set
        detail = f"ui={sorted(ui_set)} backend={sorted(backend_set)}"
        log = json.dumps(
            {
                "ui_providers": sorted(ui_set),
                "backend_providers": sorted(backend_set),
                "missing_in_ui": sorted(backend_set - ui_set),
                "missing_in_backend": sorted(ui_set - backend_set),
            },
            ensure_ascii=False,
            indent=2,
        )
        return passed, detail, log

    def case_ui_clear_all_implemented(self) -> tuple[bool, str, str]:
        api_path = self.root / "ai-companion-ui" / "src" / "api" / "index.ts"
        text = api_path.read_text(encoding="utf-8")
        has_noop = "clearAll: (_botId: string): Promise<void> =>" in text and "Promise.resolve()" in text
        passed = not has_noop
        detail = "clearAll calls backend" if passed else "clearAll is still no-op"
        return passed, detail, text

    def case_frontend_build(self) -> tuple[bool, str, str]:
        cmd = ["npm", "run", "build"]
        rc, out, err, to = self._run_cmd(cmd, cwd=self.root / "ai-companion-ui", timeout=300)
        passed = rc == 0
        detail = "build success" if passed else "build failed"
        return passed, detail, self._fmt_cmd_output(cmd, rc, out, err, to)

    def case_no_hardcoded_feishu_credentials(self) -> tuple[bool, str, str]:
        # Focus on source code only (not docs or vendored tooling strings),
        # and only match literal credential-like assignments.
        cmd = [
            "rg",
            "-n",
            "--hidden",
            "--glob",
            "!.git/**",
            "--glob",
            "!.artifacts/**",
            "--glob",
            "!**/node_modules/**",
            "--glob",
            "!**/_vendor/**",
            "--glob",
            "!**/*.log",
            (
                r"(app_secret\s*[:=]\s*['\"][A-Za-z0-9]{16,}['\"]"
                r"|APP_SECRET\s*=\s*['\"][A-Za-z0-9]{16,}['\"]"
                r"|app_id\s*[:=]\s*['\"]cli_[A-Za-z0-9]{8,}['\"]"
                r"|APP_ID\s*=\s*['\"]cli_[A-Za-z0-9]{8,}['\"])"
            ),
            str(self.root / "ai_companion"),
            str(self.root / "ai-companion-ui"),
            str(self.root / "scripts"),
            str(self.root / "tests"),
            str(self.root / "config"),
            str(self.root / "data"),
        ]
        rc, out, err, to = self._run_cmd(cmd, timeout=60)

        # rg returns 1 when no match
        has_match = rc == 0 and bool(out.strip())
        passed = not has_match
        detail = "no hardcoded feishu secret patterns" if passed else "hardcoded secret-like patterns found"
        return passed, detail, self._fmt_cmd_output(cmd, rc, out, err, to)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    suite = SystemTestSuite(root=root)
    return suite.run()


if __name__ == "__main__":
    raise SystemExit(main())
