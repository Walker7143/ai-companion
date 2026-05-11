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
import random
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request
from aiohttp import web
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
        run_env = dict(os.environ)
        run_env.setdefault("AI_COMPANION_LOG_DIR", str(self.artifacts_dir / "logs"))
        run_env.setdefault("AI_COMPANION_GATEWAY_PID_FILE", str(self.artifacts_dir / "gateway.pid"))
        if env:
            run_env.update(env)
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd or self.root),
                env=run_env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
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
        self._run_case("T03b", "Skill CLI mounted", self.case_skill_cli_mounted)
        self._run_case("T03c", "Skill registry install and command execution", self.case_skill_registry_and_command)
        self._run_case("T03d", "Bot natural-language skill management", self.case_bot_natural_language_skill_management)
        self._run_case("T04", "Config loader", self.case_config_loader)
        self._run_case("T05", "ModelFactory provider registry", self.case_model_factory_registry)
        self._run_case("T05b", "MiMo adapter OpenAI-compatible request", self.case_mimo_adapter_request_contract)
        self._run_case("T05c", "Tele adapter TeleClaw header contract", self.case_tele_adapter_request_contract)
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
        self._run_case("T18b", "Life invalid milestones do not break checkpointing", self.case_life_invalid_milestones_do_not_break_checkpointing)
        self._run_case("T19", "Life scenario cooldown blocks repeats", self.case_life_scenario_cooldown)
        self._run_case("T20", "Persona updater applies patch", self.case_persona_updater_patch)
        self._run_case("T21", "Life timeline context enters persona prompt", self.case_life_context_persona_prompt)
        self._run_case("T22", "BotInstance refreshes runtime persona settings", self.case_bot_instance_runtime_persona_refresh)
        self._run_case("T23", "Life daily event lenient JSON parsing", self.case_life_daily_lenient_json)
        self._run_case("T24", "Proactive missing sender is not counted as sent", self.case_proactive_missing_sender_not_sent)
        self._run_case("T25", "Life daily events hard cap at 100", self.case_life_daily_events_hard_cap)
        self._run_case("T26", "Major fallback events are concrete", self.case_major_fallback_events_concrete)
        self._run_case("T27", "Unexpected major events use separate low-probability channel", self.case_unexpected_major_events_low_probability)
        self._run_case("T28", "Daily scenario pool uses random candidate sampling", self.case_daily_scenario_pool_random_candidates)
        self._run_case("T29", "Major and proactive prompts include bot timeline", self.case_major_and_proactive_prompts_include_bot_timeline)
        self._run_case("T30", "Setup preserves existing config and defaults to real-time life clock", self.case_setup_preserves_config_realtime_defaults)
        self._run_case("T31", "Gateway admin safety defaults and Feishu fallback", self.case_gateway_admin_safety_defaults)
        self._run_case("T32", "Working memory compression preserves recent messages", self.case_working_memory_compression_boundary)
        self._run_case("T33", "LLM summarizer compression uses outer adapter", self.case_memory_summarizer_closure)
        self._run_case("T34", "Persona runtime profile overlays template files", self.case_persona_runtime_profile_overlay)
        self._run_case("T35", "Dependency and UI contract cleanup", self.case_dependency_and_ui_contract_cleanup)
        self._run_case("T36", "Web config center reads and persists full config", self.case_web_config_center_roundtrip)
        self._run_case("T37", "User profile memory guides natural replies", self.case_user_profile_memory_guidance)
        self._run_case("T38", "Memory governor skips casual episodic writes", self.case_memory_governor_skips_casual_episodes)
        self._run_case("T39", "Memory stores important episodes with metadata", self.case_memory_stores_important_episode_metadata)
        self._run_case("T40", "User understanding manual override wins", self.case_user_understanding_manual_override)
        self._run_case("T41", "Intent retriever trims task emotional memory", self.case_memory_retriever_intent_filtering)
        self._run_case("T42", "Relationship state is separate from semantic facts", self.case_relationship_state_separate)
        self._run_case("T42b", "Relationship stage is stable and multi-dimensional", self.case_relationship_stage_stability)
        self._run_case("T43", "Admin memory API supports new memory schema", self.case_admin_memory_api_schema_compatibility)
        self._run_case("T44", "User understanding v3 captures deep relationship insight", self.case_user_understanding_v3_deep_projection)
        self._run_case("T45", "Response style polisher removes AI tone", self.case_response_style_polisher)
        self._run_case("T46", "Built-in bots include style and understanding seeds", self.case_builtin_bot_style_and_understanding_seeds)
        self._run_case("T47", "Manual identity enters memory prompt", self.case_user_understanding_manual_identity_prompt)
        self._run_case("T48", "Runtime understanding seeds from bundled defaults", self.case_user_understanding_runtime_seed)
        self._run_case("T49", "Manual custom fields enter memory prompt", self.case_user_understanding_manual_custom_fields_prompt)
        self._run_case("T50", "Memory prompt limit handles large user understanding", self.case_memory_prompt_limit_large_understanding)
        self._run_case("T51", "Persona importer plans, applies, and resumes drafts", self.case_persona_importer_plan_apply_resume)
        self._run_case("T52", "Deferred proactive continuity", self.case_deferred_reply_proactive_continuity)

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

    def case_skill_cli_mounted(self) -> tuple[bool, str, str]:
        cmd = [str(self.python_bin), "-m", "ai_companion", "skill", "list", "--json"]
        with tempfile.TemporaryDirectory(prefix="sys-test-skill-home-") as td:
            rc, out, err, to = self._run_cmd(
                cmd,
                timeout=40,
                env={"AI_COMPANION_HOME": td},
            )
        passed = (rc == 0) and out.strip().startswith("[")
        detail = "skill CLI mounted" if passed else "skill CLI unavailable"
        return passed, detail, self._fmt_cmd_output(cmd, rc, out, err, to)

    def case_skill_registry_and_command(self) -> tuple[bool, str, str]:
        from ai_companion.skill.command import (
            contains_sensitive_token,
            execute_skill_command,
            parse_skill_management_command,
            redact_sensitive_tokens,
        )
        from ai_companion.skill.installer import SkillInstaller
        from ai_companion.skill.registry import SkillRegistry
        from ai_companion.skill.dispatcher import SkillDispatcher
        from ai_companion.skill.base import SkillContext

        async def run_command(dispatcher: SkillDispatcher) -> str:
            return await execute_skill_command(
                dispatcher,
                "/skill echo {\"message\":\"hi\"}",
                SkillContext(bot_id="test", user_id="user", conversation_history=[], personality_tags=[]),
            )

        with tempfile.TemporaryDirectory(prefix="sys-test-skill-") as td:
            root = Path(td)
            registry = SkillRegistry(root / "installed")
            source = root / "skill-echo"
            source.mkdir()
            (source / "skill.json").write_text(
                json.dumps(
                    {
                        "name": "echo",
                        "version": "1.0.0",
                        "description": "Echo test",
                        "entry": "echo_skill.py",
                        "enabled": True,
                        "requirements": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (source / "echo_skill.py").write_text(
                "\n".join(
                    [
                        "from ai_companion.skill.base import Skill, SkillContext, SkillResult",
                        "class EchoSkill(Skill):",
                        "    name = 'echo'",
                        "    description = 'Echo test'",
                        "    capabilities = ['echo']",
                        "    async def execute(self, params: dict, context: SkillContext) -> SkillResult:",
                        "        return SkillResult(success=True, content=params.get('message') or params.get('input') or 'empty')",
                    ]
                ),
                encoding="utf-8",
            )

            installed = registry.register_skill(source)
            skill = registry.load_skill("echo")
            dispatcher = SkillDispatcher()
            if skill:
                dispatcher.register(skill)
            command_output = asyncio.run(run_command(dispatcher)) if skill else ""

            bad = root / "skill-bad"
            bad.mkdir()
            (bad / "skill.json").write_text(
                json.dumps({"name": "bad", "version": "1.0.0", "entry": "../escape.py"}),
                encoding="utf-8",
            )
            rejected = registry.register_skill(bad) is None

            instruction_source = root / "skill-mmx-cli"
            instruction_source.mkdir()
            (instruction_source / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: mmx-cli",
                        "description: Use mmx via MiniMax.",
                        "---",
                        "# MiniMax CLI",
                    ]
                ),
                encoding="utf-8",
            )
            instruction_installed = registry.register_skill(instruction_source)
            instruction_skill = registry.load_skill("mmx-cli")
            nested_source = root / "repo-with-nested-skill"
            nested_skill = nested_source / "skill"
            nested_skill.mkdir(parents=True)
            (nested_skill / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: nested-md",
                        "description: Nested SKILL.md import.",
                        "---",
                        "# Nested",
                    ]
                ),
                encoding="utf-8",
            )
            nested_registry = SkillRegistry(root / "nested-installed")
            nested_installed = SkillInstaller(nested_registry).install_from_path(nested_source)

            github_parsed = parse_skill_management_command("/skill GitHub - MiniMax-AI/cli: Generate text")
            github_ok = github_parsed == ("install", {"source": "https://github.com/MiniMax-AI/cli.git", "force": False})
            windows_path = r"D:\data\个人\ai-girl-friend\.artifacts\system-test\skill-natural\skill-mmx-cli"
            windows_natural_parsed = parse_skill_management_command(f"帮我安装 skill {windows_path}")
            windows_explicit_parsed = parse_skill_management_command(f"/skill install {windows_path} --force")
            windows_path_ok = windows_natural_parsed == ("install", {"source": windows_path, "force": False})
            windows_explicit_ok = windows_explicit_parsed == ("install", {"force": True, "source": windows_path})
            secret_text = "帮我安装 skill ./demo 我的密钥是 sk-cp-" + ("A" * 32)
            secret_ok = contains_sensitive_token(secret_text) and "sk-cp-" not in redact_sensitive_tokens(secret_text)

            passed = (
                bool(installed)
                and bool(skill)
                and command_output == "hi"
                and rejected
                and bool(instruction_installed)
                and bool(instruction_skill)
                and instruction_skill.get_capabilities() == ["instruction"]
                and bool(nested_installed)
                and github_ok
                and windows_path_ok
                and windows_explicit_ok
                and secret_ok
            )
            detail = (
                f"installed={bool(installed)} loaded={bool(skill)} rejected_bad_entry={rejected} "
                f"instruction={bool(instruction_skill)} nested={bool(nested_installed)} "
                f"github_parse={github_ok} win_path={windows_path_ok and windows_explicit_ok} "
                f"secret_redact={secret_ok}"
            )
            log = json.dumps(
                {
                    "installed": installed,
                    "command_output": command_output,
                    "installed_dir": str(registry.skills_dir),
                    "bad_rejected": rejected,
                    "instruction_installed": instruction_installed,
                    "instruction_skill_name": getattr(instruction_skill, "name", None),
                    "nested_installed": nested_installed,
                    "github_parsed": github_parsed,
                    "windows_natural_parsed": windows_natural_parsed,
                    "windows_explicit_parsed": windows_explicit_parsed,
                    "windows_path_ok": windows_path_ok,
                    "windows_explicit_ok": windows_explicit_ok,
                    "secret_ok": secret_ok,
                },
                ensure_ascii=False,
                indent=2,
            )
            return passed, detail, log

    async def case_bot_natural_language_skill_management(self) -> tuple[bool, str, str]:
        from ai_companion.bot.instance import BotInstance

        skill_root = self.artifacts_dir / "skill-natural"
        skill_home = self.artifacts_dir / "skill-natural-home"
        source = skill_root / "skill-natural"
        source.mkdir(parents=True, exist_ok=True)
        (source / "skill.json").write_text(
            json.dumps(
                {
                    "name": "natural",
                    "version": "1.0.0",
                    "description": "Natural install test",
                    "entry": "natural_skill.py",
                    "enabled": True,
                    "requirements": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (source / "natural_skill.py").write_text(
            "\n".join(
                [
                    "from ai_companion.skill.base import Skill, SkillContext, SkillResult",
                    "class NaturalSkill(Skill):",
                    "    name = 'natural'",
                    "    description = 'Natural install test'",
                    "    capabilities = ['natural']",
                    "    async def execute(self, params: dict, context: SkillContext) -> SkillResult:",
                    "        return SkillResult(success=True, content='natural-ok')",
                ]
            ),
            encoding="utf-8",
        )

        leaky_source = skill_root / "skill-leaky"
        leaky_source.mkdir(parents=True, exist_ok=True)
        (leaky_source / "skill.json").write_text(
            json.dumps(
                {
                    "name": "leaky",
                    "version": "1.0.0",
                    "description": "Leaky install test",
                    "entry": "leaky_skill.py",
                    "enabled": True,
                    "requirements": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (leaky_source / "leaky_skill.py").write_text(
            "\n".join(
                [
                    "from ai_companion.skill.base import Skill, SkillContext, SkillResult",
                    "class LeakySkill(Skill):",
                    "    name = 'leaky'",
                    "    description = 'Leaky install test'",
                    "    capabilities = ['leaky']",
                    "    async def execute(self, params: dict, context: SkillContext) -> SkillResult:",
                    "        return SkillResult(success=True, content='leaky-ok')",
                ]
            ),
            encoding="utf-8",
        )

        configured_source = skill_root / "skill-configured"
        configured_source.mkdir(parents=True, exist_ok=True)
        (configured_source / "skill.json").write_text(
            json.dumps(
                {
                    "name": "configured",
                    "version": "1.0.0",
                    "description": "Configured install test",
                    "entry": "configured_skill.py",
                    "enabled": True,
                    "requirements": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (configured_source / "configured_skill.py").write_text(
            "\n".join(
                [
                    "from ai_companion.skill.base import Skill, SkillContext, SkillResult",
                    "class ConfiguredSkill(Skill):",
                    "    name = 'configured'",
                    "    description = 'Configured install test'",
                    "    capabilities = ['configured']",
                    "    async def execute(self, params: dict, context: SkillContext) -> SkillResult:",
                    "        return SkillResult(success=True, content='has-key' if self.config.get('api_key') else 'missing-key')",
                ]
            ),
            encoding="utf-8",
        )

        minimax_source = skill_root / "skill-mmx-cli"
        minimax_source.mkdir(parents=True, exist_ok=True)
        (minimax_source / "SKILL.md").write_text(
            "\n".join(
                [
                    "---",
                    "name: mmx-cli",
                    "description: Use mmx via MiniMax.",
                    "---",
                    "# MiniMax CLI",
                ]
            ),
            encoding="utf-8",
        )

        old_home = os.environ.get("AI_COMPANION_HOME")
        old_mmx_home = os.environ.get("MMX_CONFIG_HOME")
        os.environ["AI_COMPANION_HOME"] = str(skill_home)
        os.environ["MMX_CONFIG_HOME"] = str(skill_home / "mmx")
        bot = BotInstance(
            {"id": "aiyue", "name": "爱月", "description": "", "data_dir": str(self.root / "data" / "bots")},
            model=FakeModel(),
            memory_config=None,
            refusal_enabled=True,
        )
        try:
            await bot.init(start_schedulers=False)
            before = await bot.handle_message("/skill natural")
            install_reply = await bot.handle_message(f"帮我安装 skill {source}")
            run_reply = await bot.handle_message("/skill natural")
            list_reply = await bot.handle_message("查看技能列表")
            leaky_reply = await bot.handle_message(f"帮我安装 skill {leaky_source} 我的密钥是 sk-cp-{'A' * 32}")
            leaky_run = await bot.handle_message("/skill leaky")
            configured_reply = await bot.handle_message(f"帮我安装 skill {configured_source} 我的密钥是 sk-cp-{'B' * 32}")
            configured_run = await bot.handle_message("/skill configured")
            minimax_reply = await bot.handle_message(f"/skill install {minimax_source} --force 我的密钥是 sk-cp-{'C' * 32}")
            minimax_run = await bot.handle_message("/skill mmx-cli")
            history_text = "\n".join(item.get("content", "") for item in bot.conversation_history)
            configured_secrets = skill_home / "data" / "bots" / "_skills" / "skill-configured" / ".skill-secrets.json"
            minimax_secrets = skill_home / "data" / "bots" / "_skills" / "skill-mmx-cli" / ".skill-secrets.json"
            minimax_cli_config = skill_home / "mmx" / "config.json"
            passed = (
                "Skill Error" in before
                and "技能已安装：natural" in install_reply
                and run_reply == "natural-ok"
                and "natural" in list_reply
                and "技能已安装：leaky" in leaky_reply
                and leaky_run == "leaky-ok"
                and "已保存该技能需要的密钥配置" in configured_reply
                and configured_run == "has-key"
                and configured_secrets.exists()
                and "技能已安装：mmx-cli" in minimax_reply
                and "指令型技能已安装：mmx-cli" in minimax_run
                and minimax_secrets.exists()
                and minimax_cli_config.exists()
                and "sk-cp-" not in history_text
            )
            detail = (
                f"installed={'技能已安装：natural' in install_reply} run={run_reply} "
                f"secret_install={'技能已安装：leaky' in leaky_reply} configured={configured_run}"
            )
            log = json.dumps(
                {
                    "before": before,
                    "install_reply": install_reply,
                    "run_reply": run_reply,
                    "list_reply": list_reply,
                    "leaky_reply": leaky_reply,
                    "leaky_run": leaky_run,
                    "configured_reply": configured_reply,
                    "configured_run": configured_run,
                    "configured_secrets_exists": configured_secrets.exists(),
                    "minimax_reply": minimax_reply,
                    "minimax_run": minimax_run,
                    "minimax_secrets_exists": minimax_secrets.exists(),
                    "minimax_cli_config_exists": minimax_cli_config.exists(),
                    "history_contains_secret": "sk-cp-" in history_text,
                    "home": str(skill_home),
                },
                ensure_ascii=False,
                indent=2,
            )
            return passed, detail, log
        finally:
            await bot.close()
            if old_home is None:
                os.environ.pop("AI_COMPANION_HOME", None)
            else:
                os.environ["AI_COMPANION_HOME"] = old_home
            if old_mmx_home is None:
                os.environ.pop("MMX_CONFIG_HOME", None)
            else:
                os.environ["MMX_CONFIG_HOME"] = old_mmx_home

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
        expected = {"minimax", "openai", "claude", "mimo", "tele", "ollama", "custom"}
        passed = providers == expected
        detail = f"providers={sorted(providers)}"
        log = json.dumps({"providers": sorted(providers), "expected": sorted(expected)}, indent=2)
        return passed, detail, log

    async def case_mimo_adapter_request_contract(self) -> tuple[bool, str, str]:
        from ai_companion.model.factory import ModelFactory

        seen: dict = {}

        async def handle_chat(request):
            seen["path"] = request.path
            seen["headers"] = dict(request.headers)
            seen["body"] = await request.json()
            return web.json_response({
                "choices": [
                    {"message": {"content": "mimo-ok", "reasoning_content": "hidden"}}
                ]
            })

        app = web.Application()
        app.router.add_post("/v1/chat/completions", handle_chat)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        sockets = site._server.sockets if site._server else []
        port = sockets[0].getsockname()[1]
        adapter = ModelFactory.create_from_runtime_config(
            {
                "provider": "mimo",
                "api_key": "test-key",
                "base_url": f"http://127.0.0.1:{port}/v1",
                "model": "mimo-v2.5-pro",
                "timeout": 5,
            },
            provider="mimo",
        )
        try:
            response = await adapter.chat(
                [{"role": "user", "content": "hello"}],
                system_prompt="sys",
                max_tokens=123,
                temperature=0.5,
            )
        finally:
            await adapter.close()
            await runner.cleanup()

        body = seen.get("body", {})
        headers = seen.get("headers", {})
        passed = (
            response == "mimo-ok"
            and seen.get("path") == "/v1/chat/completions"
            and headers.get("api-key") == "test-key"
            and body.get("model") == "mimo-v2.5-pro"
            and body.get("max_completion_tokens") == 123
            and "max_tokens" not in body
            and body.get("messages", [])[0].get("role") == "system"
            and body.get("messages", [])[1].get("role") == "user"
        )
        detail = f"response={response} path={seen.get('path')} max_completion_tokens={body.get('max_completion_tokens')}"
        log = json.dumps(
            {
                "seen": seen,
                "response": response,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        return passed, detail, log

    async def case_tele_adapter_request_contract(self) -> tuple[bool, str, str]:
        from ai_companion.model.factory import ModelFactory

        seen: dict = {}
        state_file = self.artifacts_dir / "tele-state.json"
        state_file.write_text(
            json.dumps(
                {
                    "token": "login-token",
                    "deviceId": "device-id",
                    "installId": "install-id",
                }
            ),
            encoding="utf-8",
        )

        async def handle_chat(request):
            seen["path"] = request.path
            seen["headers"] = dict(request.headers)
            seen["body"] = await request.json()
            return web.json_response({
                "choices": [
                    {"message": {"content": "tele-ok", "reasoning_content": "hidden"}}
                ]
            })

        app = web.Application()
        app.router.add_post("/v1/chat/completions", handle_chat)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        sockets = site._server.sockets if site._server else []
        port = sockets[0].getsockname()[1]
        adapter = ModelFactory.create_from_runtime_config(
            {
                "provider": "tele",
                "base_url": f"http://127.0.0.1:{port}/v1",
                "model": "ignored-model",
                "auth_state_file": str(state_file),
                "timeout": 5,
            },
            provider="tele",
        )
        try:
            response = await adapter.chat(
                [{"role": "user", "content": "hello"}],
                system_prompt="sys",
                max_tokens=123,
                temperature=0.5,
            )
        finally:
            await adapter.close()
            await runner.cleanup()

        body = seen.get("body", {})
        headers = seen.get("headers", {})
        passed = (
            response == "tele-ok"
            and seen.get("path") == "/v1/chat/completions"
            and "Authorization" not in headers
            and headers.get("X-Token") == "login-token"
            and str(headers.get("X-SuperAgent-Timestamp", "")).isdigit()
            and bool(headers.get("X-SuperAgent-Nonce"))
            and headers.get("X-SuperAgent-Device-Id") == "device-id"
            and headers.get("X-SuperAgent-Install-Id") == "install-id"
            and body.get("model") == "glm-5-turbo"
            and body.get("max_tokens") == 123
            and body.get("messages", [])[0].get("role") == "system"
            and body.get("messages", [])[1].get("role") == "user"
        )
        safe_headers = {
            key: ("<redacted>" if key in {"Authorization", "X-Token"} else value)
            for key, value in headers.items()
            if key in {
                "Authorization",
                "X-Token",
                "X-SuperAgent-Timestamp",
                "X-SuperAgent-Nonce",
                "X-SuperAgent-Device-Id",
                "X-SuperAgent-Install-Id",
            }
        }
        detail = f"response={response} path={seen.get('path')} model={body.get('model')}"
        log = json.dumps(
            {
                "path": seen.get("path"),
                "headers": safe_headers,
                "body": body,
                "response": response,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
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
                skill_reply = await bot.handle_message("/skill hello")
                await asyncio.sleep(0.6)
                memory_status = await bot.memory.get_memory_status() if bot.memory else {}
                life_loader_ok = getattr(bot.life_engine, "_persona_loader", None) is not None
                proactive_life_link_ok = getattr(bot.proactive_engine, "life_engine", None) is bot.life_engine
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
                    and proactive_life_link_ok
                    and prompt_has_life_context
                )
                detail = (
                    f"reply_len={len(reply)} working_turns={memory_status.get('working_turns', 0)} "
                    f"life_loader_ok={life_loader_ok} proactive_life_link={proactive_life_link_ok} "
                    f"prompt_life_context={prompt_has_life_context}"
                )
                log = json.dumps(
                    {
                        "bot_id": bot.id,
                    "reply": reply,
                    "skill_reply": skill_reply,
                        "memory_status": memory_status,
                        "proactive_running": proactive_running,
                        "life_running": life_running,
                        "life_loader_ok": life_loader_ok,
                        "proactive_life_link_ok": proactive_life_link_ok,
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

    async def case_life_invalid_milestones_do_not_break_checkpointing(self) -> tuple[bool, str, str]:
        from ai_companion.proactive.life_config import LifeConfig
        from ai_companion.proactive.life_engine import LifeEngine
        from ai_companion.proactive.life_state import LifeState

        class _DailyOnlyModel:
            async def chat(self, messages: list[dict], system_prompt: str = "", **kwargs) -> str:
                text = messages[-1].get("content", "") if messages else ""
                if "输出一个 JSON 数组" in text:
                    return "[]"
                if "输出一个 JSON 对象" in text:
                    return '{"is_major": false, "reason": "stable"}'
                return "[]"

        with tempfile.TemporaryDirectory(prefix="sys-test-life-invalid-milestones-") as td:
            root = Path(td)
            state = LifeState("life_invalid_milestone_bot", root)
            state.current_date = "2024-01-01"
            state.initial_age = 20
            state.bot_age_days = 364
            state.last_checked_age = 19
            state.last_daily_tick = datetime.now() - timedelta(days=1, seconds=1)
            previous_tick = state.last_daily_tick

            cfg = LifeConfig(
                daily_interval_seconds=86400,
                major_interval_seconds=604800,
                time_ratio=1,
                sync_with_local_time_when_realtime=False,
                milestones=[
                    {"event": "缺少 age 的坏配置"},
                    {"age": "21", "event": "合法里程碑"},
                ],
            )
            engine = LifeEngine(
                bot_id="life_invalid_milestone_bot",
                config=cfg,
                state=state,
                model=_DailyOnlyModel(),
                memory=None,
                persona_dir=None,
            )

            event = await engine.tick_daily()
            state_data = state.to_dict()

            passed = (
                event is not None
                and state_data.get("current_date") == "2024-01-02"
                and state_data.get("bot_age_days") == 365
                and state.last_daily_tick is not None
                and state.last_daily_tick > previous_tick
                and state_data.get("last_checked_age") == 21
                and state_data.get("triggered_milestones") == [21]
                and len(state_data.get("major_life_events", [])) >= 1
            )
            detail = (
                f"current_date={state_data.get('current_date')} "
                f"last_checked_age={state_data.get('last_checked_age')} "
                f"major_events={len(state_data.get('major_life_events', []))}"
            )
            log = json.dumps(
                {
                    "event": event.to_dict() if event else None,
                    "state": state_data,
                    "previous_tick": previous_tick.isoformat() if previous_tick else None,
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
                sync_with_local_time_when_realtime=False,
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
            cfg = LifeConfig(sync_with_local_time_when_realtime=False)
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

            engine = LifeEngine(
                "life_prompt_bot",
                LifeConfig(sync_with_local_time_when_realtime=False),
                state,
                model=FakeModel(),
                persona_dir=persona_dir,
            )
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
                    "sync_with_local_time_when_realtime": False,
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
            cfg = LifeConfig(sync_with_local_time_when_realtime=False)
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

            cfg = LifeConfig(max_events=1000, sync_with_local_time_when_realtime=False)
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
            cfg = LifeConfig(
                major_event_fixed_probability=1.0,
                major_scenario_cooldown_days=0,
                sync_with_local_time_when_realtime=False,
            )
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
                sync_with_local_time_when_realtime=False,
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

    def case_daily_scenario_pool_random_candidates(self) -> tuple[bool, str, str]:
        from ai_companion.proactive.life_config import LifeConfig
        from ai_companion.proactive.life_engine import LifeEngine
        from ai_companion.proactive.life_state import LifeState

        with tempfile.TemporaryDirectory(prefix="sys-test-daily-candidates-") as td:
            root = Path(td)
            state = LifeState("daily_candidates_bot", root)
            state.current_date = "2030-05-08"
            cfg = LifeConfig(llm_daily_candidate_limit=12, sync_with_local_time_when_realtime=False)
            engine = LifeEngine("daily_candidates_bot", cfg, state, model=FakeModel())
            engine.set_bot_info("候选测试", 27, "产品经理", "内向, 敏感, 自律")

            catalog = engine._daily_scenario_catalog()
            sequential_keys = [item["key"] for item in catalog[:12]]
            forbidden = {item["key"] for item in catalog[:20]}

            random.seed(20260429)
            candidates = engine._daily_scenario_candidates(forbidden, limit=12)
            candidate_keys = [item["key"] for item in candidates]

            random.seed(20260429)
            unblocked_candidates = engine._daily_scenario_candidates(set(), limit=12)
            unblocked_keys = [item["key"] for item in unblocked_candidates]

            guidance = engine._scenario_guidance(candidates)
            solitude_item = next(item for item in catalog if item.get("category") == "solitude")
            social_item = next(item for item in catalog if item.get("category") == "social")
            solitude_weight = engine._scenario_personality_multiplier(solitude_item)
            social_weight = engine._scenario_personality_multiplier(social_item)

            passed = (
                len(catalog) >= 200
                and len(candidates) == 12
                and not (set(candidate_keys) & forbidden)
                and len(set(candidate_keys)) == len(candidate_keys)
                and unblocked_keys != sequential_keys
                and len(guidance.split(", ")) == len(candidates)
                and solitude_weight > social_weight
            )
            detail = (
                f"catalog={len(catalog)} candidates={len(candidates)} "
                f"random_not_front={unblocked_keys != sequential_keys} "
                f"solitude_weight={solitude_weight:.2f} social_weight={social_weight:.2f}"
            )
            log = json.dumps(
                {
                    "catalog_count": len(catalog),
                    "sequential_keys": sequential_keys,
                    "forbidden": sorted(forbidden),
                    "candidate_keys": candidate_keys,
                    "unblocked_keys": unblocked_keys,
                    "guidance": guidance,
                    "weights": {
                        "solitude": solitude_weight,
                        "social": social_weight,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            return passed, detail, log

    async def case_major_and_proactive_prompts_include_bot_timeline(self) -> tuple[bool, str, str]:
        from ai_companion.proactive.config import ProactiveConfig
        from ai_companion.proactive.engine import ProactiveEngine
        from ai_companion.proactive.life_config import LifeConfig
        from ai_companion.proactive.life_engine import LifeEngine
        from ai_companion.proactive.life_state import LifeState
        from ai_companion.proactive.state import ProactiveState

        class _NoMajorModel(FakeModel):
            async def chat(self, messages: list[dict], system_prompt: str = "", **kwargs) -> str:
                self.chat_calls.append({"messages": messages, "system_prompt": system_prompt})
                return '{"is_major": false, "reason": "stable"}'

        with tempfile.TemporaryDirectory(prefix="sys-test-bot-timeline-prompts-") as td:
            root = Path(td)
            persona_dir = root / "persona"
            persona_dir.mkdir(parents=True, exist_ok=True)
            (persona_dir / "proactive.json").write_text(
                json.dumps(
                    {
                        "enabled": True,
                        "mode": "active",
                        "scheduler": {
                            "idle_threshold_hours": 1,
                            "max_daily": 5,
                            "min_interval_hours": 0,
                            "max_idle_days": 7,
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            life_state = LifeState("timeline_prompt_bot", root)
            life_state.birth_date = "2002-11-03"
            life_state.current_date = "2030-05-08"
            life_state.day_of_week = "周三"
            life_state.year = 2030
            life_state.current_month = 5
            life_state.current_season = "春"
            life_state.initial_age = 24
            life_state.bot_age_days = 985
            life_state.bot_mood = "平静"
            life_state.bot_current_activity = "在准备一次项目评审"

            major_model = _NoMajorModel()
            life_engine = LifeEngine(
                "timeline_prompt_bot",
                LifeConfig(major_event_fixed_probability=0.0, sync_with_local_time_when_realtime=False),
                life_state,
                model=major_model,
            )
            life_engine.set_bot_info("时间测试", 24, "产品设计师", "理性, 敏感")
            await life_engine.generate_major_event()
            major_prompt = major_model.chat_calls[-1]["messages"][-1]["content"]

            proactive_model = FakeModel()
            proactive_state = ProactiveState("timeline_prompt_bot", root)
            proactive_state.last_message_time = datetime.now() - timedelta(hours=3)
            proactive_engine = ProactiveEngine(
                bot_id="timeline_prompt_bot",
                config=ProactiveConfig(persona_dir),
                state=proactive_state,
                model=proactive_model,
                memory=None,
                personality_type="温柔",
            )
            proactive_engine.bot_name = "时间测试"
            proactive_engine.age = life_engine.get_status()["bot_real_age"]
            proactive_engine.occupation = "产品设计师"
            proactive_engine.set_life_engine(life_engine)

            decision = await proactive_engine.should_contact()
            message = await proactive_engine.generate_message("测试时间线")
            proactive_prompts = [call["messages"][-1]["content"] for call in proactive_model.chat_calls]
            should_prompt = next((p for p in proactive_prompts if "should_contact" in p), "")
            message_prompt = next((p for p in proactive_prompts if '"opening"' in p and '"ending"' in p), "")

            expected_major = [
                "【当前时间背景】",
                "季节：春（5月）",
                "日期：2030-05-08，周三",
                "人生阶段：职场初期",
            ]
            expected_proactive = [
                "【Bot 时间线】",
                "当前日期：2030-05-08（周三）",
                "当前季节：春（5月）",
                "出生日期：2002-11-03",
                "当前年龄：27岁",
                "人生阶段：职场初期",
                "当前状态：在准备一次项目评审",
            ]
            passed = (
                all(item in major_prompt for item in expected_major)
                and all(item in should_prompt for item in expected_proactive)
                and all(item in message_prompt for item in expected_proactive)
                and decision.should_contact is True
                and message == "hi，there"
            )
            detail = (
                f"major_time={all(item in major_prompt for item in expected_major)} "
                f"should_time={all(item in should_prompt for item in expected_proactive)} "
                f"message_time={all(item in message_prompt for item in expected_proactive)}"
            )
            log = json.dumps(
                {
                    "major_prompt": major_prompt,
                    "should_prompt": should_prompt,
                    "message_prompt": message_prompt,
                    "decision": {
                        "should_contact": decision.should_contact,
                        "reason": decision.reason,
                        "urgency": decision.urgency,
                    },
                    "message": message,
                },
                ensure_ascii=False,
                indent=2,
            )
            return passed, detail, log

    def case_setup_preserves_config_realtime_defaults(self) -> tuple[bool, str, str]:
        from ai_companion.proactive.life_config import LifeConfig
        from ai_companion.setup import (
            LIFE_TIME_PRESETS,
            REALTIME_DAILY_INTERVAL_SECONDS,
            REALTIME_MAJOR_INTERVAL_SECONDS,
            _deep_merge,
            _extract_existing_feishu_binding,
            _merge_bot_entries,
        )
        setup_text = (self.root / "ai_companion" / "setup.py").read_text(encoding="utf-8")

        model_existing = {
            "model": {"provider": "minimax", "temperature": 0.7},
            "minimax": {"api_key": "keep-minimax", "model": "old-model"},
            "memory": {"embedding": "local", "max_working_turns": 9},
        }
        model_update = {
            "model": {"provider": "openai"},
            "openai": {"api_key": "new-openai", "model": "gpt-4o"},
        }
        merged_model = _deep_merge(model_existing, model_update)

        life_existing = {
            "daily_interval_seconds": 3600,
            "major_interval_seconds": 21600,
            "time_ratio": 24,
            "event_policy": {"scenario_cooldown_days": 14},
            "daily_life_profile": {"hobbies": ["咖啡"]},
        }
        life_update = {
            "daily_interval_seconds": REALTIME_DAILY_INTERVAL_SECONDS,
            "major_interval_seconds": REALTIME_MAJOR_INTERVAL_SECONDS,
            "time_ratio": LIFE_TIME_PRESETS["1"]["time_ratio"],
            "max_events": 100,
        }
        merged_life = _deep_merge(life_existing, life_update)
        existing_bots = [
            {
                "id": "lin_wanqing",
                "name": "旧林晚晴",
                "description": "keep me",
                "enabled": False,
                "custom": {"tone": "quiet"},
            }
        ]
        preserved_bots = _merge_bot_entries(
            existing_bots,
            [{"id": "lin_wanqing", "name": "新林晚晴"}],
            overwritten_bot_ids=set(),
        )
        overwritten_bots = _merge_bot_entries(
            existing_bots,
            [{"id": "lin_wanqing", "name": "新林晚晴"}],
            overwritten_bot_ids={"lin_wanqing"},
        )
        default_life = LifeConfig()
        existing_feishu = {
            "extra": {"app_id": "global-app", "app_secret": "global-secret"},
            "routing": {"mode": "dedicated", "bot_id": "lin_wanqing"},
            "bot_bindings": {
                "ethan_reed": {"extra": {"app_id": "ethan-app", "app_secret": "ethan-secret"}}
            },
        }
        lin_wanqing_feishu = _extract_existing_feishu_binding(existing_feishu, "lin_wanqing")
        ethan_reed_feishu = _extract_existing_feishu_binding(existing_feishu, "ethan_reed")

        passed = (
            merged_model["model"]["provider"] == "openai"
            and merged_model["model"]["temperature"] == 0.7
            and merged_model["minimax"]["api_key"] == "keep-minimax"
            and merged_model["memory"]["embedding"] == "local"
            and merged_life["daily_interval_seconds"] == 86400
            and merged_life["major_interval_seconds"] == 604800
            and merged_life["time_ratio"] == 1
            and merged_life["event_policy"]["scenario_cooldown_days"] == 14
            and merged_life["daily_life_profile"]["hobbies"] == ["咖啡"]
            and preserved_bots["lin_wanqing"]["name"] == "旧林晚晴"
            and preserved_bots["lin_wanqing"]["description"] == "keep me"
            and preserved_bots["lin_wanqing"]["enabled"] is False
            and preserved_bots["lin_wanqing"]["custom"]["tone"] == "quiet"
            and overwritten_bots["lin_wanqing"]["name"] == "新林晚晴"
            and overwritten_bots["lin_wanqing"]["description"] == "keep me"
            and default_life.daily_interval_seconds == 86400
            and default_life.major_interval_seconds == 604800
            and default_life.daily_interval == 86400
            and default_life.sync_with_local_time_when_realtime is True
            and "绑定飞书前必须先创建 Bot" in setup_text
            and "绑定飞书 App 时必须同时绑定 Bot" in setup_text
            and "是否为每个 Bot 单独配置主动唤醒活跃程度" in setup_text
            and "是否为每个 Bot 单独配置人生轨迹参数" in setup_text
            and "是否为多个 Bot 分别配置飞书 App" in setup_text
            and lin_wanqing_feishu["extra"]["app_id"] == "global-app"
            and ethan_reed_feishu["extra"]["app_id"] == "ethan-app"
        )
        detail = (
            f"provider={merged_model['model']['provider']} "
            f"daily={default_life.daily_interval_seconds} major={default_life.major_interval_seconds}"
        )
        log = json.dumps(
            {
                "merged_model": merged_model,
                "merged_life": merged_life,
                "preserved_bots": preserved_bots,
                "overwritten_bots": overwritten_bots,
                "default_life": {
                    "daily_interval_seconds": default_life.daily_interval_seconds,
                    "major_interval_seconds": default_life.major_interval_seconds,
                    "daily_interval": default_life.daily_interval,
                    "major_interval": default_life.major_interval,
                },
                "setup_has_required_feishu_binding": "绑定飞书 App 时必须同时绑定 Bot" in setup_text,
                "setup_has_per_bot_prompts": {
                    "proactive": "是否为每个 Bot 单独配置主动唤醒活跃程度" in setup_text,
                    "life": "是否为每个 Bot 单独配置人生轨迹参数" in setup_text,
                    "feishu": "是否为多个 Bot 分别配置飞书 App" in setup_text,
                },
                "feishu_binding_lookup": {
                    "lin_wanqing": lin_wanqing_feishu,
                    "ethan_reed": ethan_reed_feishu,
                },
                "life_time_presets": LIFE_TIME_PRESETS,
            },
            ensure_ascii=False,
            indent=2,
        )
        return passed, detail, log

    def case_gateway_admin_safety_defaults(self) -> tuple[bool, str, str]:
        from ai_companion.gateway.admin_services import admin_host, mask_secret, public_model_config

        gateway_text = (self.root / "ai_companion" / "gateway" / "cmd.py").read_text(encoding="utf-8")
        public_cfg = public_model_config({"provider": "openai", "api_key": "sk-1234567890abcdef"})
        passed = (
            "bot_manager._bots" not in gateway_text
            and "bot_manager.first_bot" in gateway_text
            and admin_host({}) == "127.0.0.1"
            and 'Access-Control-Allow-Origin"] = "*"' not in gateway_text
            and public_cfg["api_key"] == mask_secret("sk-1234567890abcdef")
            and public_cfg["api_key"] != "sk-1234567890abcdef"
        )
        detail = f"masked={public_cfg['api_key']} fallback={'bot_manager.first_bot' in gateway_text}"
        log = json.dumps(
            {
                "public_cfg": public_cfg,
                "admin_host": admin_host({}),
                "has_private_bots_access": "bot_manager._bots" in gateway_text,
                "has_wildcard_cors_assignment": 'Access-Control-Allow-Origin"] = "*"' in gateway_text,
            },
            ensure_ascii=False,
            indent=2,
        )
        return passed, detail, log

    async def case_working_memory_compression_boundary(self) -> tuple[bool, str, str]:
        from ai_companion.memory.stores.working import WorkingMemoryStore

        with tempfile.TemporaryDirectory() as tmp:
            store = WorkingMemoryStore(str(Path(tmp) / "working.db"))
            await store.init()
            store.start_session("s1")
            for i in range(10):
                await store.append(f"user-{i}", f"bot-{i}", session_id="s1")
            summary = await store.compress("s1", summarizer=None)

            import sqlite3

            conn = sqlite3.connect(str(Path(tmp) / "working.db"))
            rows = conn.execute("SELECT id, compressed FROM messages ORDER BY id ASC").fetchall()
            summary_row = conn.execute("SELECT message_count FROM summaries").fetchone()
            conn.close()

        compressed_ids = [row[0] for row in rows if row[1] == 1]
        active_ids = [row[0] for row in rows if row[1] == 0]
        passed = (
            summary is not None
            and compressed_ids == list(range(1, 9))
            and active_ids == list(range(9, 21))
            and summary_row
            and summary_row[0] == 8
        )
        detail = f"compressed={compressed_ids} active_first={active_ids[:1]} active_count={len(active_ids)}"
        log = json.dumps(
            {
                "summary": summary,
                "compressed_ids": compressed_ids,
                "active_ids": active_ids,
                "summary_row": summary_row,
            },
            ensure_ascii=False,
            indent=2,
        )
        return passed, detail, log

    async def case_memory_summarizer_closure(self) -> tuple[bool, str, str]:
        from ai_companion.memory.engine import MemoryEngine

        class Summarizer:
            def __init__(self):
                self.calls = 0

            async def chat(self, messages: list[dict], system_prompt: str = "") -> dict:
                self.calls += 1
                return {"content": "LLM summary"}

        with tempfile.TemporaryDirectory() as tmp:
            engine = MemoryEngine("bot", Path(tmp), config={"embedding": "none"})
            await engine.init()
            engine.start_session("s1")
            summarizer = Summarizer()
            engine.set_summarizer(summarizer)
            for i in range(10):
                await engine.working.append(f"user-{i}", f"bot-{i}", session_id="s1")
            await engine._do_compress()
            summaries = engine.working.get_summaries("s1")
            await engine.close()

        passed = summarizer.calls == 1 and summaries == ["LLM summary"]
        detail = f"calls={summarizer.calls} summaries={summaries}"
        return passed, detail, json.dumps({"calls": summarizer.calls, "summaries": summaries}, ensure_ascii=False, indent=2)

    async def case_persona_runtime_profile_overlay(self) -> tuple[bool, str, str]:
        from ai_companion.memory.stores.semantic import SemanticStore
        from ai_companion.persona.engine import PersonaEngine
        from ai_companion.persona.loader import PersonaLoader

        with tempfile.TemporaryDirectory() as tmp:
            persona_dir = Path(tmp) / "persona"
            persona_dir.mkdir()
            profile_path = persona_dir / "profile.json"
            backstory_path = persona_dir / "backstory.json"
            profile_path.write_text(
                json.dumps({"name": "林晚晴", "age": 27, "occupation": "古籍修复师", "relationship_to_user": "朋友"}, ensure_ascii=False),
                encoding="utf-8",
            )
            backstory_path.write_text(json.dumps({"key_moments": ["初识"]}, ensure_ascii=False), encoding="utf-8")
            (persona_dir / "values.json").write_text(json.dumps({"non_negotiable": []}, ensure_ascii=False), encoding="utf-8")
            (persona_dir / "speaking_style.json").write_text(json.dumps({"tone": "自然"}, ensure_ascii=False), encoding="utf-8")

            store = SemanticStore(str(Path(tmp) / "semantic.db"), persona_backstory_path=str(backstory_path))
            await store._update_relationship("恋人")
            await store._update_attitude_profile(6)
            await store._append_key_moment("一起看烟花")

            profile_after = json.loads(profile_path.read_text(encoding="utf-8"))
            backstory_after = json.loads(backstory_path.read_text(encoding="utf-8"))
            persona = PersonaLoader(persona_dir).load()
            prompt = PersonaEngine(persona).build_system_prompt()

        passed = (
            profile_after["relationship_to_user"] == "朋友"
            and backstory_after["key_moments"] == ["初识"]
            and persona.profile["relationship_to_user"] == "恋人"
            and persona.profile["attitude_score"] == 6
            and "一起看烟花" in prompt
            and "你和用户的关系：恋人" in prompt
        )
        detail = f"template_rel={profile_after['relationship_to_user']} runtime_rel={persona.profile.get('relationship_to_user')}"
        log = json.dumps(
            {
                "profile_after": profile_after,
                "backstory_after": backstory_after,
                "persona_profile": persona.profile,
                "prompt": prompt,
            },
            ensure_ascii=False,
            indent=2,
        )
        return passed, detail, log

    async def case_user_profile_memory_guidance(self) -> tuple[bool, str, str]:
        from ai_companion.memory.engine import MemoryEngine

        class MultiFactModel:
            async def chat(self, messages: list[dict], system_prompt: str = "") -> str:
                text = messages[-1].get("content", "") if messages else ""
                if "用户画像信息" in text:
                    return '\n'.join([
                        '{"key": "城市", "value": "上海"}',
                        '{"key": "希望被怎样回应", "value": "先共情，少讲大道理"}',
                    ])
                if "NO_CHANGE" in text:
                    return "NO_CHANGE"
                if "NO_MOMENT" in text:
                    return "NO_MOMENT"
                if "只输出数字" in text:
                    return "0"
                return "NO_FACT"

        with tempfile.TemporaryDirectory(prefix="sys-test-user-profile-") as td:
            root = Path(td)
            engine = MemoryEngine(
                bot_id="profile_bot",
                memory_dir=root,
                config={"embedding": "none"},
            )
            await engine.init()
            engine.start_session("new")
            engine.set_summarizer(MultiFactModel())
            understanding_path = root / "profile_bot" / "memory" / "user_understanding.json"
            seeded = json.loads(understanding_path.read_text(encoding="utf-8"))
            seeded["summary"] = "用户最近压力偏大，但不喜欢被催着立刻振作。"
            seeded["communication_style"] = ["先接住情绪，再给建议。"]
            understanding_path.write_text(json.dumps(seeded, ensure_ascii=False, indent=2), encoding="utf-8")
            await engine.semantic.set_fact("城市", "杭州", session_id="old")
            await engine.semantic.extract_and_store(
                "我现在住上海，最近有点烦，跟我说话你先共情，少讲大道理。",
                "我听见了，先不急着讲道理。",
                session_id="new",
            )

            facts = await engine.semantic.get_all_facts()
            context = await engine.load_context("今天有点烦")
            understanding = engine.user_understanding.load()
            await engine.close()

        suffix = context.get("system_suffix", "")
        passed = (
            facts.get("城市") == "上海"
            and facts.get("希望被怎样回应") == "先共情，少讲大道理"
            and understanding.get("auto_facts", {}).get("城市") == "上海"
            and "用户最近压力偏大" in suffix
            and "先接住情绪" in suffix
            and "【你对用户的理解】" in suffix
            and "相处背景" in suffix
            and "不要生硬" in suffix
            and "【语义记忆补充】" not in suffix
        )
        detail = f"city={facts.get('城市')} auto={len(understanding.get('auto_facts', {}))} guidance={'相处背景' in suffix}"
        log = json.dumps(
            {
                "facts": facts,
                "user_understanding": understanding,
                "system_suffix": suffix,
            },
            ensure_ascii=False,
            indent=2,
        )
        return passed, detail, log

    async def case_memory_governor_skips_casual_episodes(self) -> tuple[bool, str, str]:
        from ai_companion.memory.engine import MemoryEngine
        import sqlite3

        with tempfile.TemporaryDirectory(prefix="sys-test-memory-casual-") as td:
            root = Path(td)
            engine = MemoryEngine("casual_bot", root, config={"embedding": "none"})
            await engine.init()
            engine.start_session("sid")
            await engine.on_message("你好呀", "你好，今天怎么样？")
            db_path = root / "casual_bot" / "memory" / "episodic.db"
            conn = sqlite3.connect(str(db_path))
            count = conn.execute("SELECT COUNT(*) FROM episodic_memory").fetchone()[0]
            conn.close()
            await engine.close()

        passed = count == 0
        return passed, f"episodic_count={count}", json.dumps({"episodic_count": count}, ensure_ascii=False, indent=2)

    async def case_memory_stores_important_episode_metadata(self) -> tuple[bool, str, str]:
        from ai_companion.memory.engine import MemoryEngine
        import sqlite3

        with tempfile.TemporaryDirectory(prefix="sys-test-memory-episode-") as td:
            root = Path(td)
            engine = MemoryEngine("episode_bot", root, config={"embedding": "none"})
            await engine.init()
            engine.start_session("sid")
            await engine.on_message("我明天有一个很重要的面试，真的有点焦虑。", "我陪你一起准备。")
            db_path = root / "episode_bot" / "memory" / "episodic.db"
            conn = sqlite3.connect(str(db_path))
            row = conn.execute(
                "SELECT summary, importance, confidence, user_id, archived FROM episodic_memory LIMIT 1"
            ).fetchone()
            conn.close()
            await engine.close()

        passed = bool(row and row[1] >= 0.68 and row[2] >= 0.6 and row[3] == "default_user" and row[4] == 0)
        log = json.dumps({"row": row}, ensure_ascii=False, indent=2)
        return passed, f"row={bool(row)}", log

    async def case_user_understanding_manual_override(self) -> tuple[bool, str, str]:
        from ai_companion.memory.engine import MemoryEngine

        with tempfile.TemporaryDirectory(prefix="sys-test-understanding-manual-") as td:
            root = Path(td)
            engine = MemoryEngine("manual_bot", root, config={"embedding": "none"})
            await engine.init()
            data = engine.user_understanding.load()
            data["manual"]["facts"]["城市"] = "杭州"
            engine.user_understanding._write(data)
            await engine.semantic.set_fact(
                "城市",
                "上海",
                bot_id="manual_bot",
                user_id="default_user",
                category="identity",
                confidence=0.95,
                source="user_explicit",
            )
            await engine.maintenance.run_light(bot_id="manual_bot", user_id="default_user")
            understanding = engine.user_understanding.load()
            context = await engine.load_context("我在哪个城市？")
            await engine.close()

        suffix = context.get("system_suffix", "")
        passed = (
            understanding["manual"]["facts"].get("城市") == "杭州"
            and understanding["auto"]["facts"].get("城市") is None
            and "杭州" in suffix
            and "上海" not in suffix
        )
        log = json.dumps({"understanding": understanding, "system_suffix": suffix}, ensure_ascii=False, indent=2)
        return passed, f"manual_city={understanding['manual']['facts'].get('城市')}", log

    async def case_memory_retriever_intent_filtering(self) -> tuple[bool, str, str]:
        from ai_companion.memory.engine import MemoryEngine

        with tempfile.TemporaryDirectory(prefix="sys-test-memory-intent-") as td:
            root = Path(td)
            engine = MemoryEngine("intent_bot", root, config={"embedding": "none"})
            await engine.init()
            await engine.semantic.set_fact(
                "希望被怎样回应",
                "先共情，少讲大道理",
                bot_id="intent_bot",
                user_id="default_user",
                category="communication_style",
                confidence=0.95,
            )
            await engine.episodic.store_episode(
                summary="用户之前因为失眠很难过，Bot 陪用户聊到很晚。",
                content="用户：我失眠很难过\n助手：我陪你。",
                bot_id="intent_bot",
                user_id="default_user",
                session_id="old",
                importance=0.9,
                confidence=0.9,
            )
            emotional = await engine.load_context("我今天有点难过")
            task = await engine.load_context("帮我写代码实现一个排序函数")
            await engine.close()

        passed = (
            emotional.get("memory_intent") == "emotional_support"
            and "可能相关的共同经历" in emotional.get("system_suffix", "")
            and task.get("memory_intent") == "task_request"
            and "可能相关的共同经历" not in task.get("system_suffix", "")
        )
        log = json.dumps(
            {
                "emotional_intent": emotional.get("memory_intent"),
                "task_intent": task.get("memory_intent"),
                "emotional_suffix": emotional.get("system_suffix"),
                "task_suffix": task.get("system_suffix"),
            },
            ensure_ascii=False,
            indent=2,
        )
        return passed, f"emotional={emotional.get('memory_intent')} task={task.get('memory_intent')}", log

    async def case_relationship_state_separate(self) -> tuple[bool, str, str]:
        from ai_companion.memory.engine import MemoryEngine

        with tempfile.TemporaryDirectory(prefix="sys-test-relationship-") as td:
            root = Path(td)
            engine = MemoryEngine("rel_bot", root, config={"embedding": "none"})
            await engine.init()
            await engine.relationship.apply_event(
                bot_id="rel_bot",
                user_id="default_user",
                label="好朋友",
                attitude_delta=3,
                key_moment="用户认真安慰了 Bot",
            )
            await engine.semantic.set_fact(
                "喜欢的音乐",
                "爵士",
                bot_id="rel_bot",
                user_id="default_user",
                category="preferences",
                confidence=0.9,
            )
            await engine.forget_fact("喜欢的音乐")
            facts = await engine.semantic.get_all_facts(bot_id="rel_bot", user_id="default_user")
            relationship = await engine.relationship.get_state(bot_id="rel_bot", user_id="default_user")
            await engine.close()

        passed = (
            "喜欢的音乐" not in facts
            and relationship.get("relationship_label") == "好朋友"
            and relationship.get("attitude_score") == 62
            and relationship.get("relationship_score") > 35
            and relationship.get("score_scale") == 100
        )
        log = json.dumps({"facts": facts, "relationship": relationship}, ensure_ascii=False, indent=2)
        return passed, f"relationship={relationship.get('relationship_label')}", log

    async def case_relationship_stage_stability(self) -> tuple[bool, str, str]:
        from ai_companion.memory.engine import MemoryEngine

        with tempfile.TemporaryDirectory(prefix="sys-test-relationship-stable-") as td:
            root = Path(td)
            engine = MemoryEngine("stable_bot", root, config={"embedding": "none"})
            await engine.init()
            first = await engine.relationship.apply_event(
                bot_id="stable_bot",
                user_id="default_user",
                label="暧昧中",
                intimacy_delta=20,
                affection_delta=28,
                trust_delta=12,
                attitude_delta=4,
                key_moment="用户认真表白，关系进入暧昧期",
            )
            second = await engine.relationship.apply_event(
                bot_id="stable_bot",
                user_id="default_user",
                label="朋友",
                intimacy_delta=0,
                affection_delta=0,
                trust_delta=0,
                attitude_delta=0,
            )
            third = await engine.relationship.apply_event(
                bot_id="stable_bot",
                user_id="default_user",
                label="朋友",
                tension_delta=1,
                attitude_delta=-1,
            )
            final = await engine.relationship.get_state(bot_id="stable_bot", user_id="default_user")
            await engine.close()

        passed = (
            first.get("relationship_label") == "暧昧中"
            and second.get("relationship_label") == "暧昧中"
            and third.get("relationship_label") == "暧昧中"
            and final.get("relationship_score") >= 45
            and final.get("score_scale") == 100
        )
        log = json.dumps({"first": first, "second": second, "third": third, "final": final}, ensure_ascii=False, indent=2)
        return passed, f"final={final.get('relationship_label')} score={final.get('relationship_score')}", log

    def case_admin_memory_api_schema_compatibility(self) -> tuple[bool, str, str]:
        gateway_text = (self.root / "ai_companion" / "gateway" / "cmd.py").read_text(encoding="utf-8")
        types_text = (self.root / "ai-companion-ui" / "src" / "types" / "index.ts").read_text(encoding="utf-8")
        memory_ui = (self.root / "ai-companion-ui" / "src" / "pages" / "Memory" / "Memory.tsx").read_text(encoding="utf-8")
        checks = {
            "gateway_counts_v2_understanding": "_understanding_auto_count" in gateway_text,
            "gateway_reads_relationship": "relationship_state" in gateway_text,
            "gateway_returns_relationship_state": '"relationship_state": relationship_state' in gateway_text,
            "gateway_returns_fact_metadata": '"category": r[3]' in gateway_text and '"confidence": r[4]' in gateway_text,
            "ui_fact_metadata_types": "category?: string" in types_text and "confidence?: number" in types_text,
            "ui_displays_metadata": "fact.category" in memory_ui and "fact.confidence" in memory_ui,
            "ui_displays_relationship_dimensions": "RelationshipMetric" in memory_ui and "综合关系温度" in memory_ui,
        }
        passed = all(checks.values())
        return passed, f"checks={sum(checks.values())}/{len(checks)}", json.dumps(checks, ensure_ascii=False, indent=2)

    async def case_user_understanding_v3_deep_projection(self) -> tuple[bool, str, str]:
        from ai_companion.memory.engine import MemoryEngine

        with tempfile.TemporaryDirectory(prefix="sys-test-understanding-v3-") as td:
            root = Path(td)
            engine = MemoryEngine("deep_bot", root, config={"embedding": "none"})
            await engine.init()
            await engine.semantic.set_fact(
                "近期压力源",
                "最近准备作品集压力很大，晚上容易焦虑",
                bot_id="deep_bot",
                user_id="default_user",
                category="life_context",
                confidence=0.92,
            )
            await engine.semantic.set_fact(
                "希望被怎样回应",
                "情绪低落时先陪一会儿，不要立刻讲道理",
                bot_id="deep_bot",
                user_id="default_user",
                category="communication_style",
                confidence=0.96,
            )
            await engine.relationship.apply_event(
                bot_id="deep_bot",
                user_id="default_user",
                label="好朋友",
                trust_delta=1,
                intimacy_delta=1,
                key_moment="用户开始主动分享自己的脆弱时刻",
            )
            await engine.maintenance.run_light(bot_id="deep_bot", user_id="default_user")
            understanding = engine.user_understanding.load()
            context = await engine.load_context("我今天又有点焦虑")
            await engine.close()

        auto = understanding.get("auto", {})
        relationship_memory = understanding.get("relationship_memory", {})
        suffix = context.get("system_suffix", "")
        passed = (
            understanding.get("version") == 3
            and auto.get("profile_summary")
            and any("作品集" in item for item in auto.get("stressors", []))
            and any("先陪" in item for item in auto.get("comfort_strategies", []))
            and any("脆弱" in item for item in relationship_memory.get("things_that_brought_them_closer", []))
            and "观察到的情绪模式" in suffix
            and "有效的安慰/陪伴方式" in suffix
            and "让关系变近的时刻" in suffix
        )
        log = json.dumps(
            {
                "understanding": understanding,
                "system_suffix": suffix,
            },
            ensure_ascii=False,
            indent=2,
        )
        return passed, f"version={understanding.get('version')} deep={'有效的安慰/陪伴方式' in suffix}", log

    def case_response_style_polisher(self) -> tuple[bool, str, str]:
        from ai_companion.bot.response_style import ResponseStylePolisher

        polisher = ResponseStylePolisher()
        understanding = {
            "manual": {
                "interaction_style": {
                    "preferred_reply_length": "短一点",
                    "disliked_phrases": ["我理解你的感受"],
                    "avoid_patterns": ["先总结再列点"],
                }
            }
        }
        raw = "我理解你的感受。以下是一些建议：\n1. 先休息一下\n2. 然后制定计划\n3. 如果你需要，我可以继续帮你。"
        polished = polisher.polish(
            raw,
            intent="emotional_support",
            relationship_state={"tension_score": 0},
            user_understanding=understanding,
        )
        passed = (
            "我理解你的感受" not in polished
            and "以下是一些建议" not in polished
            and "如果你需要" not in polished
            and "1." not in polished
            and len(polished) < len(raw)
        )
        return passed, f"polished_len={len(polished)}", json.dumps({"raw": raw, "polished": polished}, ensure_ascii=False, indent=2)

    def case_builtin_bot_style_and_understanding_seeds(self) -> tuple[bool, str, str]:
        bot_ids = ["lin_wanqing", "shen_nian", "sofia_rivera", "gu_yichen", "zhou_yan", "ethan_reed"]
        base = self.root / "ai_companion" / "data" / "bots"
        checks = {}
        for bot_id in bot_ids:
            style_path = base / bot_id / "persona" / "conversation_style_rules.json"
            understanding_path = base / bot_id / "memory" / "user_understanding.json"
            style = json.loads(style_path.read_text(encoding="utf-8")) if style_path.exists() else {}
            understanding = json.loads(understanding_path.read_text(encoding="utf-8")) if understanding_path.exists() else {}
            checks[bot_id] = {
                "style_exists": style_path.exists(),
                "has_avoid_phrases": bool(style.get("avoid_phrases")),
                "understanding_exists": understanding_path.exists(),
                "understanding_v3": understanding.get("version") == 3,
                "has_manual_interaction_style": bool(
                    understanding.get("manual", {}).get("interaction_style", {}).get("disliked_phrases")
                ),
            }
        template_style = base / "_template" / "persona" / "conversation_style_rules.json"
        template_understanding = base / "_template" / "memory" / "user_understanding.json"
        checks["_template"] = {
            "style_exists": template_style.exists(),
            "understanding_exists": template_understanding.exists(),
        }
        passed = all(all(item.values()) for item in checks.values())
        return passed, f"bots={len(bot_ids)} template={checks['_template']['style_exists']}", json.dumps(checks, ensure_ascii=False, indent=2)

    async def case_user_understanding_manual_identity_prompt(self) -> tuple[bool, str, str]:
        from ai_companion.memory.engine import MemoryEngine

        with tempfile.TemporaryDirectory(prefix="sys-test-understanding-identity-") as td:
            root = Path(td)
            engine = MemoryEngine("identity_bot", root, config={"embedding": "none"})
            await engine.init()
            data = engine.user_understanding.load()
            data["manual"]["identity"]["称呼"] = "小王"
            data["manual"]["identity"]["城市"] = "杭州"
            engine.user_understanding._write(data)
            context = await engine.load_context("你知道我怎么称呼吗？")
            await engine.close()

        suffix = context.get("system_suffix", "")
        passed = (
            "用户手动设定的身份信息" in suffix
            and "称呼: 小王" in suffix
            and "城市: 杭州" in suffix
        )
        return passed, f"identity_in_suffix={passed}", json.dumps({"system_suffix": suffix}, ensure_ascii=False, indent=2)

    async def case_user_understanding_runtime_seed(self) -> tuple[bool, str, str]:
        from ai_companion.memory.engine import MemoryEngine

        with tempfile.TemporaryDirectory(prefix="sys-test-understanding-seed-") as td:
            root = Path(td)

            seeded_engine = MemoryEngine("shen_nian", root, config={"embedding": "none"})
            await seeded_engine.init()
            seeded = seeded_engine.user_understanding.load()
            seeded_context = await seeded_engine.load_context("随便聊聊")
            await seeded_engine.close()

            existing_engine = MemoryEngine("shen_nian", root / "existing", config={"embedding": "none"})
            await existing_engine.init()
            existing = existing_engine.user_understanding.load()
            existing["manual"]["summary"] = "用户自己写的理解，不应被内置种子覆盖。"
            existing_engine.user_understanding._write(existing)
            await existing_engine.close()

            existing_engine = MemoryEngine("shen_nian", root / "existing", config={"embedding": "none"})
            await existing_engine.init()
            existing_after = existing_engine.user_understanding.load()
            await existing_engine.close()

        seeded_manual = seeded.get("manual", {})
        relationship_memory = seeded.get("relationship_memory", {})
        seeded_suffix = seeded_context.get("system_suffix", "")
        passed = (
            "轻快、有创作感" in seeded_manual.get("summary", "")
            and any("脑暴" in item for item in seeded_manual.get("communication_style", []))
            and any(
                "关键时刻认真" in item
                for item in relationship_memory.get("what_user_seems_to_need_from_bot", [])
            )
            and "轻快、有创作感" in seeded_suffix
            and existing_after.get("manual", {}).get("summary") == "用户自己写的理解，不应被内置种子覆盖。"
        )
        log = json.dumps(
            {
                "seeded_manual": seeded_manual,
                "seeded_relationship_memory": relationship_memory,
                "seeded_suffix": seeded_suffix,
                "existing_after": existing_after.get("manual", {}),
            },
            ensure_ascii=False,
            indent=2,
        )
        return passed, f"seeded_summary={bool(seeded_manual.get('summary'))}", log

    async def case_user_understanding_manual_custom_fields_prompt(self) -> tuple[bool, str, str]:
        from ai_companion.memory.engine import MemoryEngine

        with tempfile.TemporaryDirectory(prefix="sys-test-understanding-custom-") as td:
            root = Path(td)
            engine = MemoryEngine("custom_bot", root, config={"embedding": "none"})
            await engine.init()
            data = engine.user_understanding.load()
            data["manual"]["life_context"] = ["最近在准备长期项目，容易被上下文切换打断。"]
            data["manual"]["自定义观察"] = {
                "工作方式": "喜欢先给结论，再给必要依据",
                "雷区": ["不要重复确认已经说清楚的背景"],
            }
            data["长期提醒"] = "用户希望 Bot 主动沿用 user_understanding 里的背景。"
            engine.user_understanding._write(data)

            loaded = engine.user_understanding.load()
            context = await engine.load_context("继续")
            proactive_text = engine.user_understanding.format_for_prompt()
            await engine.close()

        suffix = context.get("system_suffix", "")
        passed = (
            loaded.get("manual", {}).get("自定义观察", {}).get("工作方式") == "喜欢先给结论，再给必要依据"
            and loaded.get("长期提醒") == "用户希望 Bot 主动沿用 user_understanding 里的背景。"
            and "用户手动设定的生活背景" in suffix
            and "自定义观察" in suffix
            and "喜欢先给结论" in suffix
            and "长期提醒" in suffix
            and "用户手动设定的生活背景" in proactive_text
            and "自定义观察" in proactive_text
        )
        log = json.dumps(
            {"loaded": loaded, "system_suffix": suffix},
            ensure_ascii=False,
            indent=2,
        )
        return passed, f"custom_in_suffix={passed}", log

    async def case_memory_prompt_limit_large_understanding(self) -> tuple[bool, str, str]:
        from ai_companion.memory.engine import MemoryEngine

        tail_marker = "TAIL_MARKER_用户理解末尾仍应进入提示"
        with tempfile.TemporaryDirectory(prefix="sys-test-understanding-large-") as td:
            root = Path(td)
            engine = MemoryEngine("large_bot", root, config={"embedding": "none"})
            await engine.init()
            data = engine.user_understanding.load()
            data["manual"]["summary"] = "用户手动写入了很长的背景。"
            data["manual"]["notes"] = [f"背景片段{i}: " + ("重要上下文" * 18) for i in range(75)]
            data["manual"]["notes"].append(tail_marker)
            engine.user_understanding._write(data)
            context = await engine.load_context("继续")
            await engine.close()

        suffix = context.get("system_suffix", "")
        passed = (
            len(suffix) > 4400
            and len(suffix) <= 12000
            and tail_marker in suffix
        )
        return passed, f"suffix_len={len(suffix)} tail={tail_marker in suffix}", json.dumps({"system_suffix_len": len(suffix), "tail_present": tail_marker in suffix}, ensure_ascii=False, indent=2)

    async def case_persona_importer_plan_apply_resume(self) -> tuple[bool, str, str]:
        from ai_companion.persona_importer.apply import apply_draft
        from ai_companion.persona_importer.chunker import chunk_sections, select_character_chunks
        from ai_companion.persona_importer.paths import _decode_file_url_path, resolve_book_path
        from ai_companion.persona_importer.pipeline import PersonaImportPipeline
        from ai_companion.persona_importer.reader import load_book
        from ai_companion.persona_importer.schema import ImportOptions, parse_character_spec
        from ai_companion.model.factory import ModelFactory

        class ImporterFakeModel:
            def __init__(self):
                self.calls = 0

            async def chat(self, messages: list[dict], system_prompt: str = "", **kwargs) -> str:
                self.calls += 1
                if "角色档案编辑器" in system_prompt:
                    return json.dumps({
                        "name": "林黛玉",
                        "bot_id": "lin_daiyu",
                        "profile_facts": [],
                        "timeline": [{"stage": "当前", "event": "初入贾府", "evidence_refs": ["s0000_c0000"], "confidence": 0.9}],
                        "traits": [{"trait": "敏感", "description": "心思细腻", "evidence_refs": ["s0000_c0000"], "confidence": 0.8}],
                        "relationships": [],
                        "speaking_style": [],
                        "values_and_boundaries": [],
                        "evidence_index": [{"ref": "s0000_c0000", "chapter": "第一章 初见", "summary": "林黛玉进府", "confidence": 0.9}],
                        "uncertainties": [],
                    }, ensure_ascii=False)
                if "persona 配置作者" in system_prompt:
                    return json.dumps({
                        "profile.json": {
                            "id": "lin_daiyu",
                            "name": "林黛玉",
                            "age": 18,
                            "occupation": "书中角色",
                            "gender": "female",
                            "personality_tags": ["敏感"],
                            "relationship_to_user": "基于书中角色改写的初识对象",
                            "appearance": "",
                            "interests": [],
                            "settings": {"tone_default": "含蓄", "emoji_usage": "从不", "response_length": "中等"},
                        },
                        "backstory.json": {"summary": "初入贾府", "key_moments": ["初入贾府"]},
                        "values.json": {"non_negotiable": ["不接受轻慢"], "soft_boundaries": []},
                        "speaking_style.json": {"tone": "含蓄", "emotion_indicators": {"sad": "话少"}},
                        "conversation_style_rules.json": {
                            "reply_principles": ["先回应当下"],
                            "avoid_phrases": ["作为AI"],
                            "avoid_patterns": [],
                            "natural_patterns": ["短句"],
                            "intent_style": {"casual_chat": "自然"},
                        },
                    }, ensure_ascii=False)
                raise AssertionError("resume should skip chunk extraction calls")

            async def embeddings(self, texts: list[str]) -> list[list[float]]:
                return [[0.0] for _ in texts]

            async def close(self):
                return None

        class AlwaysFailModel:
            def __init__(self):
                self.calls = 0

            async def chat(self, messages: list[dict], system_prompt: str = "", **kwargs) -> str:
                self.calls += 1
                raise RuntimeError("forced failure")

            async def embeddings(self, texts: list[str]) -> list[list[float]]:
                return [[0.0] for _ in texts]

            async def close(self):
                return None

        class JsonRepairModel:
            def __init__(self):
                self.calls = 0

            async def chat(self, messages: list[dict], system_prompt: str = "", **kwargs) -> str:
                self.calls += 1
                if "JSON 语法修复器" in system_prompt:
                    return json.dumps({
                        "chunk_id": "s0000_c0000",
                        "section_title": "第一章 初见",
                        "characters": [{
                            "bot_id": "lin_daiyu",
                            "name": "林黛玉",
                            "facts": [{"claim": "进府", "evidence_summary": "林黛玉进府", "quote": "", "confidence": 0.9}],
                            "events": [],
                            "traits": [],
                            "relationships": [],
                            "speaking_style": [],
                            "values_boundaries": [],
                            "uncertainties": [],
                        }],
                    }, ensure_ascii=False)
                return '{"chunk_id":"s0000_c0000","section_title":"第一章 初见" "characters":[]}'

            async def embeddings(self, texts: list[str]) -> list[list[float]]:
                return [[0.0] for _ in texts]

            async def close(self):
                return None

        class BadShapeThenGoodModel:
            def __init__(self):
                self.calls = 0

            async def chat(self, messages: list[dict], system_prompt: str = "", **kwargs) -> str:
                self.calls += 1
                if self.calls == 1:
                    return json.dumps([{"not": "an object"}], ensure_ascii=False)
                return json.dumps({
                    "chunk_id": "s0000_c0000",
                    "section_title": "第一章 初见",
                    "characters": [],
                }, ensure_ascii=False)

            async def embeddings(self, texts: list[str]) -> list[list[float]]:
                return [[0.0] for _ in texts]

            async def close(self):
                return None

        with tempfile.TemporaryDirectory(prefix="sys-test-persona-importer-") as td:
            root = Path(td)
            book = root / "book.txt"
            book.write_text(
                "\n".join([
                    "第一章 初见",
                    "林黛玉进府，众人都看她言谈举止不俗。",
                    "",
                    "第二章 另事",
                    "薛宝钗待人稳妥，话不多。",
                ]),
                encoding="utf-8",
            )
            gbk_book = root / "gbk_book.txt"
            gbk_book.write_bytes("第一章 编码\n杨思思站在门口。".encode("gbk"))
            resolved_relative = resolve_book_path("book.txt", cwd=root)
            resolved_file_url = resolve_book_path(book.as_uri())
            target = parse_character_spec("lin_daiyu:林黛玉=黛玉,林妹妹")
            document = load_book(resolved_relative)
            gbk_document = load_book(gbk_book)
            chunks = chunk_sections(document.sections, chunk_chars=1000, overlap_chars=100)
            selected = select_character_chunks(chunks, [target], include_neighbors=False)

            out = root / "draft"
            out.mkdir()
            existing = {
                "chunk_id": "s0000_c0000",
                "section_title": "第一章 初见",
                "char_range": [0, 30],
                "characters": [{
                    "bot_id": "lin_daiyu",
                    "name": "林黛玉",
                    "facts": [],
                    "events": [{"event": "初入贾府", "stage": "当前", "evidence_summary": "林黛玉进府", "confidence": 0.9}],
                    "traits": [],
                    "relationships": [],
                    "speaking_style": [],
                    "values_boundaries": [],
                    "uncertainties": [],
                }],
            }
            (out / "extractions.jsonl").write_text(json.dumps(existing, ensure_ascii=False) + "\n", encoding="utf-8")

            model = ImporterFakeModel()
            manifest = await PersonaImportPipeline(
                model=model,
                options=ImportOptions(
                    book_path=book,
                    characters=[target],
                    output_dir=out,
                    chunk_chars=1000,
                    overlap_chars=100,
                    retry_attempts=1,
                    resume=True,
                    include_neighbor_chunks=False,
                ),
            ).run()

            data_dir = root / "data" / "bots"
            config_dir = root / "config"
            result = apply_draft(out, data_dir=data_dir, config_dir=config_dir, yes=True)
            profile = json.loads((data_dir / target.bot_id / "persona" / "profile.json").read_text(encoding="utf-8"))
            bots_yaml = (config_dir / "bots.yaml").read_text(encoding="utf-8")
            run_log = (out / "run.log").read_text(encoding="utf-8")

            fail_out = root / "fail_draft"
            fail_model = AlwaysFailModel()
            failure_raised = False
            try:
                await PersonaImportPipeline(
                    model=fail_model,
                    options=ImportOptions(
                        book_path=book,
                        characters=[target],
                        output_dir=fail_out,
                        chunk_chars=1000,
                        overlap_chars=100,
                        retry_attempts=2,
                        retry_base_delay_seconds=0,
                        failure_policy="exit",
                        include_neighbor_chunks=False,
                    ),
                ).run()
            except RuntimeError:
                failure_raised = True
            fail_log = (fail_out / "run.log").read_text(encoding="utf-8")

            repair_out = root / "repair_draft"
            repair_model = JsonRepairModel()
            repair_data = await PersonaImportPipeline(
                model=repair_model,
                options=ImportOptions(
                    book_path=book,
                    characters=[target],
                    output_dir=repair_out,
                    chunk_chars=1000,
                    overlap_chars=100,
                    retry_attempts=1,
                    json_repair_attempts=1,
                    include_neighbor_chunks=False,
                ),
            )._extract_chunk(selected[0][0], selected[0][1])
            repair_log = (repair_out / "run.log").read_text(encoding="utf-8")
            invalid_json_files = list((repair_out / "debug" / "invalid_json").glob("*.txt"))

            bad_shape_out = root / "bad_shape_draft"
            bad_shape_model = BadShapeThenGoodModel()
            bad_shape_data = await PersonaImportPipeline(
                model=bad_shape_model,
                options=ImportOptions(
                    book_path=book,
                    characters=[target],
                    output_dir=bad_shape_out,
                    chunk_chars=1000,
                    overlap_chars=100,
                    retry_attempts=2,
                    retry_base_delay_seconds=0,
                    include_neighbor_chunks=False,
                ),
            )._extract_chunk(selected[0][0], selected[0][1])
            bad_shape_log = (bad_shape_out / "run.log").read_text(encoding="utf-8")

        checks = {
            "target_bot_id": target.bot_id == "lin_daiyu",
            "target_aliases": target.aliases == ["黛玉", "林妹妹"],
            "resolved_relative": resolved_relative == book.resolve(),
            "resolved_file_url": resolved_file_url == book.resolve(),
            "gbk_encoding": gbk_document.encoding in {"gb18030", "gbk"},
            "gbk_text": "杨思思" in gbk_document.sections[0].text,
            "chunk_count": len(chunks) >= 2,
            "selected_count": len(selected) == 1,
            "resume_model_calls": model.calls == 2,
            "run_log_skip": "chunk_skip_completed" in run_log,
            "run_log_success": "llm_call_success" in run_log,
            "manifest_resume": manifest["chunks"]["resume"] is True,
            "applied_bot": result.applied_bot_ids == ["lin_daiyu"],
            "profile_name": profile["name"] == "林黛玉",
            "bots_yaml_name": "林黛玉" in bots_yaml,
            "failure_raised": failure_raised,
            "fail_calls": fail_model.calls == 2,
            "fail_log_give_up": "llm_call_give_up" in fail_log,
            "repair_calls": repair_model.calls == 2,
            "repair_bot": repair_data["characters"][0]["bot_id"] == "lin_daiyu",
            "repair_log_success": "llm_json_repair_success" in repair_log,
            "invalid_json_count": len(invalid_json_files) == 1,
            "bad_shape_calls": bad_shape_model.calls == 2,
            "bad_shape_chunk": bad_shape_data["chunk_id"] == "s0000_c0000",
            "bad_shape_log_error": "llm_call_error" in bad_shape_log,
            "bad_shape_log_type": "顶层类型=list" in bad_shape_log,
        }
        passed = all(checks.values())
        timeout_adapter = ModelFactory.create_from_runtime_config(
            {"provider": "minimax", "api_key": "fake", "timeout": 180},
            provider="minimax",
        )
        try:
            timeout_total = timeout_adapter.timeout.total
        finally:
            await timeout_adapter.close()
        checks["timeout_total"] = timeout_total == 180
        from ai_companion.gateway.cmd import build_memory_config_for_provider

        class _Cfg:
            models = {
                "memory": {"embedding": "none"},
                "mimo": {"max_context_tokens": 1048576},
            }

            def get_provider_config(self, provider: str) -> dict:
                return self.models.get(provider, {})

        mimo_memory_cfg = build_memory_config_for_provider(_Cfg(), "mimo")
        mimo_model_context = mimo_memory_cfg["context"]["compressor"]["model_context"]
        checks["mimo_model_context"] = mimo_model_context == 1048576
        windows_file_url_path = _decode_file_url_path("/D:/data/%E4%B8%AA%E4%BA%BA/book.txt", platform="win32")
        checks["windows_file_url_path"] = windows_file_url_path == "D:/data/个人/book.txt"
        passed = all(checks.values())
        failed_checks = [name for name, ok in checks.items() if not ok]
        detail = (
            f"chunks={len(chunks)} selected={len(selected)} calls={model.calls} "
            f"resume={manifest['chunks'].get('resume')} failure_raised={failure_raised} "
            f"repair_calls={repair_model.calls} bad_shape_calls={bad_shape_model.calls} "
            f"timeout_total={timeout_total} mimo_context={mimo_model_context}"
        )
        if failed_checks:
            detail += f" failed_checks={','.join(failed_checks)}"
        log = json.dumps(
            {
                "target": target.to_dict(),
                "resolved_relative": str(resolved_relative),
                "resolved_file_url": str(resolved_file_url),
                "document": document.to_dict(),
                "gbk_document": gbk_document.to_dict(),
                "selected": [{"chunk": chunk.to_dict(), "targets": [t.bot_id for t in targets]} for chunk, targets in selected],
                "manifest": manifest,
                "model_calls": model.calls,
                "profile": profile,
                "bots_yaml": bots_yaml,
                "run_log": run_log,
                "fail_model_calls": fail_model.calls,
                "failure_raised": failure_raised,
                "fail_log": fail_log,
                "repair_model_calls": repair_model.calls,
                "repair_log": repair_log,
                "invalid_json_files": [str(path) for path in invalid_json_files],
                "bad_shape_model_calls": bad_shape_model.calls,
                "bad_shape_log": bad_shape_log,
                "timeout_total": timeout_total,
                "mimo_model_context": mimo_model_context,
                "windows_file_url_path": windows_file_url_path,
                "checks": checks,
            },
            ensure_ascii=False,
            indent=2,
        )
        return passed, detail, log

    def case_dependency_and_ui_contract_cleanup(self) -> tuple[bool, str, str]:
        pyproject = (self.root / "pyproject.toml").read_text(encoding="utf-8")
        setup_py = (self.root / "setup.py").read_text(encoding="utf-8")
        requirements = (self.root / "requirements.txt").read_text(encoding="utf-8").strip()
        api_text = (self.root / "ai-companion-ui" / "src" / "api" / "index.ts").read_text(encoding="utf-8")
        ui_server_text = (self.root / "ai_companion" / "ui_server.py").read_text(encoding="utf-8")

        passed = (
            "[project]" in pyproject
            and "lark-oapi" in pyproject
            and "chromadb" in pyproject
            and "install_requires" not in setup_py
            and requirements == "."
            and "bot_id=" in api_text
            and "Promise.resolve(true)" not in api_text
            and "Promise.resolve('')" not in api_text
            and "def ensure_ui_server" in ui_server_text
            and "--strictPort" in ui_server_text
            and 'os.environ.get("START_UI")' in ui_server_text
        )
        detail = f"pyproject={'[project]' in pyproject} requirements={requirements}"
        log = json.dumps(
            {
                "has_pyproject": "[project]" in pyproject,
                "requirements": requirements,
                "ui_uses_bot_filter": "bot_id=" in api_text,
                "ui_has_fake_success": "Promise.resolve(true)" in api_text or "Promise.resolve('')" in api_text,
            },
            ensure_ascii=False,
            indent=2,
        )
        return passed, detail, log

    def case_web_config_center_roundtrip(self) -> tuple[bool, str, str]:
        from types import SimpleNamespace

        import yaml

        from ai_companion.config.loader import Config
        from ai_companion.gateway.admin_services import ConfigAdminService, _validate_feishu_one_to_one_binding

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "config"
            persona_dir = root / "data" / "bots" / "webbot" / "persona"
            other_persona_dir = root / "data" / "bots" / "otherbot" / "persona"
            config_dir.mkdir(parents=True)
            persona_dir.mkdir(parents=True)
            other_persona_dir.mkdir(parents=True)

            (config_dir / "models.yaml").write_text(
                yaml.safe_dump(
                    {
                        "model": {"provider": "openai", "temperature": 0.7, "max_tokens": 2000},
                        "openai": {"api_key": "keep-openai-key", "base_url": "https://api.openai.com/v1", "model": "old-model"},
                        "memory": {"embedding": "none", "soft_limit_chars": 3000},
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            (config_dir / "config.yaml").write_text(
                yaml.safe_dump(
                    {
                        "platforms": {
                        "feishu": {
                            "enabled": True,
                            "extra": {"app_id": "old-app", "app_secret": "keep-secret", "connection_mode": "websocket"},
                            "routing": {"mode": "dedicated", "bot_id": "webbot"},
                            },
                            "weixin": {
                                "enabled": True,
                                "token": "keep-wx-token",
                                "extra": {
                                    "account_id": "wx-account",
                                    "base_url": "https://ilinkai.weixin.qq.com",
                                    "cdn_base_url": "https://novac2c.cdn.weixin.qq.com/c2c",
                                    "dm_policy": "allowlist",
                                    "allow_from": ["wx-user"],
                                    "group_policy": "disabled",
                                    "group_allow_from": [],
                                    "split_multiline_messages": False,
                                },
                                "routing": {"mode": "dedicated", "bot_id": "webbot"},
                                "home_channel": {"platform": "weixin", "chat_id": "wx-user", "name": "微信私聊"},
                            },
                        }
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            def write_persona_files(target: Path, name: str):
                (target / "profile.json").write_text(
                    json.dumps({"name": name, "age": 20, "occupation": "学生", "relationship_to_user": "朋友", "personality_tags": ["温柔"]}, ensure_ascii=False),
                    encoding="utf-8",
                )
                (target / "backstory.json").write_text(json.dumps({"key_moments": ["初识"]}, ensure_ascii=False), encoding="utf-8")
                (target / "values.json").write_text(json.dumps({"non_negotiable": ["真诚"]}, ensure_ascii=False), encoding="utf-8")
                (target / "speaking_style.json").write_text(json.dumps({"tone": "自然"}, ensure_ascii=False), encoding="utf-8")
                (target / "proactive.json").write_text(json.dumps({"enabled": True, "scheduler": {"idle_threshold_hours": 24}}, ensure_ascii=False), encoding="utf-8")
                (target / "life.json").write_text(json.dumps({"time_ratio": 1, "daily_interval_seconds": 86400}, ensure_ascii=False), encoding="utf-8")

            write_persona_files(persona_dir, "旧名")
            write_persona_files(other_persona_dir, "另一个 Bot")

            config = Config(config_dir=config_dir)
            refresh = {"count": 0}

            def refresh_runtime():
                refresh["count"] += 1

            bot = SimpleNamespace(
                id="webbot",
                name="旧名",
                persona_loader=SimpleNamespace(dir=persona_dir),
                _refresh_runtime_settings=refresh_runtime,
                get_proactive_status=lambda: {"conversation_tasks": {"pending": 0}},
            )
            other_bot = SimpleNamespace(
                id="otherbot",
                name="另一个 Bot",
                persona_loader=SimpleNamespace(dir=other_persona_dir),
                _refresh_runtime_settings=lambda: None,
            )
            manager = SimpleNamespace(get_bot=lambda bot_id: {"webbot": bot, "otherbot": other_bot}.get(bot_id))
            service = ConfigAdminService(config, manager)
            before = service.get_bot_config("webbot")
            proactive_fields = next(
                section["fields"]
                for section in before["schema"]["sections"]
                if section["id"] == "proactive"
            )
            other_before = service.get_bot_config("otherbot")
            result = service.update_bot_config(
                "webbot",
                {
                    "model": {
                        "provider": "openai",
                        "api_key": before["model"]["api_key"],
                        "base_url": "https://api.openai.com/v1",
                        "model": "gpt-4o",
                        "temperature": 0.9,
                        "max_tokens": 4096,
                    },
                    "memory": {
                        "hard_limit_chars": 90000,
                        "soft_limit_chars": 5000,
                        "max_working_turns": 12,
                        "max_summaries": 4,
                        "semantic_char_limit": 3200,
                        "embedding": "local",
                        "embedding_model": "all-MiniLM-L6-v2",
                    },
                    "proactive": {
                        "enabled": True,
                        "mode": "active",
                        "check_interval_seconds": 300,
                        "idle_threshold_hours": 8,
                        "min_interval_hours": 2,
                        "max_daily": 3,
                        "continuity_enabled": True,
                        "deferred_reply_enabled": True,
                        "deferred_reply_delay_minutes": 10,
                        "deferred_reply_min_delay_minutes": 3,
                        "deferred_reply_max_delay_minutes": 45,
                        "deferred_reply_expires_hours": 12,
                        "deferred_reply_bypass_idle_threshold": False,
                        "topic_continuation_enabled": True,
                        "topic_continuation_idle_after_minutes": 30,
                        "topic_continuation_expires_hours": 8,
                        "topic_continuation_min_score": 0.66,
                        "emotion_followup_enabled": False,
                        "emotion_followup_delay_minutes": 25,
                        "emotion_followup_expires_hours": 18,
                        "life_event_motive_enabled": False,
                        "idle_ping_enabled": True,
                        "emotion_keywords": ["累"],
                        "preferred_contact_times": ["09:00-22:00"],
                        "platform_type": "feishu",
                    },
                    "life": {
                        "time_ratio": 24,
                        "daily_interval_seconds": 86400,
                        "major_interval_seconds": 604800,
                        "event_policy": {"unexpected_event_probability": 0.02},
                    },
                    "platforms": [{"name": "feishu", "enabled": True, "config": {}}],
                    "feishu": {
                        "enabled": True,
                        "extra": {"app_id": "new-app", "app_secret": before["platforms"][1]["config"]["extra"]["app_secret"], "group_policy": "allowlist"},
                        "routing": {"mode": "dedicated", "bot_id": "webbot"},
                    },
                    "weixin": {
                        "enabled": True,
                        "token": before["platforms"][2]["config"]["token"],
                        "extra": {
                            "account_id": "wx-account",
                            "base_url": "https://ilinkai.weixin.qq.com",
                            "cdn_base_url": "https://novac2c.cdn.weixin.qq.com/c2c",
                            "dm_policy": "allowlist",
                            "allow_from": ["wx-user"],
                            "group_policy": "allowlist",
                            "group_allow_from": ["wx-group"],
                            "split_multiline_messages": True,
                        },
                        "routing": {"mode": "dedicated", "bot_id": "webbot"},
                        "home_channel": {"platform": "weixin", "chat_id": "wx-user", "name": "微信私聊"},
                    },
                    "session_reset": {"mode": "idle", "at_hour": 3, "idle_minutes": 45, "notify": False},
                    "persona": {
                        "profile": {"name": "新名", "personality_tags": ["温柔", "可靠"]},
                        "backstory": {"key_moments": ["初识", "一起看展"]},
                        "values": {"non_negotiable": ["真诚", "尊重"]},
                        "speaking_style": {
                            "tone": "温柔",
                            "catchphrases": ["嗯"],
                            "embodied_expression": {
                                "enabled": True,
                                "frequency": "high",
                                "action_style": "动作轻一点，偏照顾感",
                                "action_examples": ["把杯子往你手边推近一点"],
                                "avoid_actions": ["夸张拥抱"],
                            },
                        },
                    },
                },
            )
            other_result = service.update_bot_config(
                "otherbot",
                {
                    "platforms": [{"name": "feishu", "enabled": True, "config": {}}],
                    "feishu": {
                        "enabled": True,
                        "extra": {"app_id": "other-app", "app_secret": "other-secret", "group_policy": "allowlist"},
                        "routing": {"mode": "dedicated", "bot_id": "otherbot"},
                    },
                },
            )
            other_after = service.get_bot_config("otherbot")
            web_after = service.get_bot_config("webbot")
            invalid_error = ""
            try:
                service.update_bot_config(
                    "otherbot",
                    {
                        "weixin": {
                            "enabled": True,
                            "token": "other-token",
                            "extra": {"account_id": "other-account"},
                            "routing": {"mode": "dedicated", "bot_id": "otherbot"},
                        },
                    },
                )
            except ValueError as e:
                weixin_conflict_error = str(e)
            else:
                weixin_conflict_error = ""
            try:
                service.update_bot_config(
                    "otherbot",
                    {
                        "feishu": {
                            "enabled": True,
                            "extra": {"app_id": "new-app", "app_secret": "other-secret"},
                            "routing": {"mode": "dedicated", "bot_id": "otherbot"},
                        },
                    },
                )
            except ValueError as e:
                invalid_error = str(e)
            missing_app_error = ""
            try:
                _validate_feishu_one_to_one_binding(
                    {"enabled": True, "routing": {"mode": "dedicated", "bot_id": "webbot"}}
                )
            except ValueError as e:
                missing_app_error = str(e)
            models = yaml.safe_load((config_dir / "models.yaml").read_text(encoding="utf-8"))
            main_cfg = yaml.safe_load((config_dir / "config.yaml").read_text(encoding="utf-8"))
            proactive = json.loads((persona_dir / "proactive.json").read_text(encoding="utf-8"))
            life = json.loads((persona_dir / "life.json").read_text(encoding="utf-8"))
            profile = json.loads((persona_dir / "profile.json").read_text(encoding="utf-8"))
            style = json.loads((persona_dir / "speaking_style.json").read_text(encoding="utf-8"))

        passed = (
            before["schema"]["sections"]
            and "continuity_enabled" in proactive_fields
            and "deferred_reply_delay_minutes" in proactive_fields
            and "topic_continuation_min_score" in proactive_fields
            and before["model"]["api_key"] != "keep-openai-key"
            and before["proactive"]["continuity_enabled"] is True
            and result["ok"] is True
            and models["openai"]["api_key"] == "keep-openai-key"
            and models["openai"]["model"] == "gpt-4o"
            and models["memory"]["embedding"] == "local"
            and proactive["scheduler"]["idle_threshold_hours"] == 8
            and proactive["platform"]["type"] == "feishu"
            and proactive["conversation_continuity"]["enabled"] is True
            and proactive["conversation_continuity"]["deferred_reply"]["default_delay_minutes"] == 10
            and proactive["conversation_continuity"]["deferred_reply"]["min_delay_minutes"] == 3
            and proactive["conversation_continuity"]["deferred_reply"]["max_delay_minutes"] == 45
            and proactive["conversation_continuity"]["deferred_reply"]["expires_hours"] == 12
            and proactive["conversation_continuity"]["deferred_reply"]["bypass_idle_threshold"] is False
            and proactive["conversation_continuity"]["topic_continuation"]["idle_after_minutes"] == 30
            and proactive["conversation_continuity"]["topic_continuation"]["expires_hours"] == 8
            and proactive["conversation_continuity"]["topic_continuation"]["min_score"] == 0.66
            and proactive["conversation_continuity"]["emotion_followup"]["enabled"] is False
            and proactive["conversation_continuity"]["emotion_followup"]["delay_minutes"] == 25
            and proactive["conversation_continuity"]["emotion_followup"]["expires_hours"] == 18
            and proactive["conversation_continuity"]["life_event"]["enabled"] is False
            and proactive["conversation_continuity"]["idle_ping"]["enabled"] is True
            and life["time_ratio"] == 24
            and life["event_policy"]["unexpected_event_probability"] == 0.02
            and main_cfg["platforms"]["feishu"]["extra"]["app_secret"] == "keep-secret"
            and main_cfg["platforms"]["feishu"]["extra"]["app_id"] == "new-app"
            and main_cfg["platforms"]["weixin"]["token"] == "keep-wx-token"
            and main_cfg["platforms"]["weixin"]["extra"]["group_policy"] == "allowlist"
            and main_cfg["platforms"]["weixin"]["extra"]["split_multiline_messages"] is True
            and before["platforms"][2]["config"]["token"] != "keep-wx-token"
            and web_after["proactive"]["continuity_enabled"] is True
            and web_after["proactive"]["deferred_reply_delay_minutes"] == 10
            and web_after["proactive"]["topic_continuation_min_score"] == 0.66
            and web_after["proactive"]["idle_ping_enabled"] is True
            and web_after["diagnostics"]["proactive_status"]["conversation_tasks"]["pending"] == 0
            and web_after["platforms"][2]["enabled"] is True
            and web_after["platforms"][2]["config"]["extra"]["group_allow_from"] == ["wx-group"]
            and other_before["platforms"][2]["enabled"] is False
            and other_before["platforms"][1]["enabled"] is False
            and other_before["platforms"][1]["config"]["extra"].get("app_id") is None
            and other_result["ok"] is True
            and main_cfg["platforms"]["feishu"]["bot_bindings"]["otherbot"]["extra"]["app_id"] == "other-app"
            and other_after["platforms"][1]["config"]["extra"]["app_id"] == "other-app"
            and web_after["platforms"][1]["config"]["extra"]["app_id"] == "new-app"
            and "一个微信账号只能绑定一个 Bot" in weixin_conflict_error
            and "同时绑定了多个 Bot" in invalid_error
            and "必须填写 App ID" in missing_app_error
            and main_cfg["session_reset"]["mode"] == "idle"
            and profile["name"] == "新名"
            and style["口头禅"] == ["嗯"]
            and style["embodied_expression"]["enabled"] is True
            and style["embodied_expression"]["frequency"] == "high"
            and style["embodied_expression"]["action_style"] == "动作轻一点，偏照顾感"
            and style["embodied_expression"]["action_examples"] == ["把杯子往你手边推近一点"]
            and style["embodied_expression"]["avoid_actions"] == ["夸张拥抱"]
            and web_after["persona_summary"]["speaking_style"]["embodied_expression"]["frequency"] == "high"
            and web_after["persona_summary"]["speaking_style"]["embodied_expression"]["action_examples"] == ["把杯子往你手边推近一点"]
            and refresh["count"] >= 2
        )
        detail = f"model={models['openai']['model']} memory={models['memory']['embedding']} refresh={refresh['count']}"
        log = json.dumps(
            {
                "before": before,
                "other_before": other_before,
                "other_after": other_after,
                "web_after": web_after,
                "result_changed_files": result.get("changed_files"),
                "models": models,
                "main_cfg": main_cfg,
                "invalid_error": invalid_error,
                "missing_app_error": missing_app_error,
                "weixin_conflict_error": weixin_conflict_error,
                "proactive": proactive,
                "life": life,
                "profile": profile,
                "style": style,
                "refresh": refresh,
            },
            ensure_ascii=False,
            indent=2,
        )
        return passed, detail, log

    async def case_deferred_reply_proactive_continuity(self) -> tuple[bool, str, str]:
        from ai_companion.bot.instance import BotInstance

        class PromiseThenFollowupModel:
            provider = "test"
            model = "promise-followup"

            def __init__(self):
                self.calls: list[str] = []

            async def chat(self, messages, system_prompt=None, **kwargs):
                text = messages[-1].get("content", "") if messages else ""
                self.calls.append(text)
                if "主动联系原因" in text or "继续刚才承诺" in text:
                    return '{"opening":"刚才你问的那个问题","topic":"我想了一下，可以先小范围试试","ending":"你觉得呢？"}'
                if "延迟回复承诺" in text or "对话分析助手" in text:
                    return '{"deferred_reply": {"detected": true, "summary": "承诺稍后回复关于项目的看法", "delay_minutes": 1}, "unresolved_topic": {"detected": false, "summary": "", "confidence": 0.0}, "emotion_followup": {"detected": false, "emotion": "", "summary": ""}}'
                return "我想一下，一会儿回复你。"

            async def embeddings(self, texts: list[str]) -> list[list[float]]:
                return [[0.0, 0.0, 0.0] for _ in texts]

            async def close(self):
                return None

        with tempfile.TemporaryDirectory(prefix="sys-deferred-proactive-") as td:
            root = Path(td)
            data_root = root / "data" / "bots"
            bot_id = "deferred_bot"
            persona = data_root / bot_id / "persona"
            persona.mkdir(parents=True)
            for name, payload in {
                "profile.json": {
                    "name": "延迟测试",
                    "age": 22,
                    "occupation": "学生",
                    "relationship_to_user": "朋友",
                    "personality_tags": ["温柔"],
                },
                "backstory.json": {},
                "values.json": {},
                "speaking_style.json": {"tone": "自然"},
                "proactive.json": {
                    "enabled": True,
                    "mode": "active",
                    "scheduler": {"min_interval_hours": 0.1, "max_daily": 5},
                    "platform": {"type": "weixin"},
                    "preferred_contact_times": ["00:00-23:59"],
                    "conversation_continuity": {"deferred_reply": {"default_delay_minutes": 1}},
                },
                "life.json": {
                    "daily_interval_seconds": 86400,
                    "major_interval_seconds": 604800,
                    "time_ratio": 1,
                    "sync_with_local_time_when_realtime": False,
                },
            }.items():
                (persona / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            sent = []
            model = PromiseThenFollowupModel()
            bot = BotInstance(
                {"id": bot_id, "name": "延迟测试", "data_dir": str(data_root)},
                model=model,
                data_dir=data_root,
                memory_config={"embedding": "none"},
                refusal_enabled=False,
            )
            async def capture_send(msg, target=None):
                sent.append({"msg": msg, "target": target})
                return True

            try:
                await bot.init(start_schedulers=False)
                bot.proactive_engine._platform_sender = capture_send
                response = await bot.handle_message(
                    "那你怎么看这个项目？",
                    memory_turn_context={
                        "platform": "weixin",
                        "session_id": "gw_a",
                        "user_id": "default_user",
                        "chat_id": "wx-1",
                    },
                )
                await bot._drain_background_tasks(timeout=5.0)
                pending_before = bot.conversation_task_store.count_pending(bot_id)
                now = datetime.now()
                task_rows = bot.conversation_task_store.list_due(bot_id, now + timedelta(minutes=10))
                due_at = (task_rows[0].due_at + timedelta(seconds=1)) if task_rows else now + timedelta(minutes=5)
                due = bot.conversation_task_store.list_due(bot_id, due_at)
                ok_tick = await bot.proactive_orchestrator.tick(now=due_at)
                pending_after = bot.conversation_task_store.count_pending(bot_id)
            finally:
                await bot.close()

        passed = (
            "一会儿回复你" in response
            and len(due) == 1
            and pending_before == 1
            and ok_tick is True
            and pending_after == 0
            and sent
            and sent[0]["target"]["chat_id"] == "wx-1"
            and "刚才你问的那个问题" in sent[0]["msg"]
        )
        detail = (
            f"response={response} due={len(due)} pending_before={pending_before} "
            f"pending_after={pending_after} sent={sent}"
        )
        log = json.dumps(
            {
                "response": response,
                "due": [item.to_dict() for item in due],
                "pending_before": pending_before,
                "pending_after": pending_after,
                "ok_tick": ok_tick,
                "sent": sent,
                "model_calls": model.calls,
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
        npm = shutil.which("npm")
        if not npm:
            return False, "npm not found", "Node.js/npm is required for frontend production build."
        cmd = [npm, "run", "build"]
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
