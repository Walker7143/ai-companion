from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from .runtime_profile import load_runtime_profile, runtime_profile_path_from_persona_dir


DEFAULT_TIMELINE_LIMIT = 50
DEFAULT_TURN_REFLECTION_CADENCE = 8
DEFAULT_AUDIT_RETENTION = 500


def evolution_state_path_from_persona_dir(persona_dir: str | Path | None) -> Optional[Path]:
    if not persona_dir:
        return None
    return Path(persona_dir) / "evolution_state.json"


def evolution_audit_path_from_persona_dir(persona_dir: str | Path | None) -> Optional[Path]:
    if not persona_dir:
        return None
    return Path(persona_dir) / "evolution_audit.jsonl"


def evolution_config_path_from_persona_dir(persona_dir: str | Path | None) -> Optional[Path]:
    if not persona_dir:
        return None
    return Path(persona_dir) / "evolution.json"


def load_evolution_state(persona_dir: str | Path | None) -> dict[str, Any]:
    path = evolution_state_path_from_persona_dir(persona_dir)
    if not path or not path.exists():
        return _default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_state()
    return _normalize_state(data)


def load_evolution_config(persona_dir: str | Path | None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = copy.deepcopy(DEFAULT_EVOLUTION_CONFIG)
    path = evolution_config_path_from_persona_dir(persona_dir)
    if path and path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            raw = {}
        cfg = _deep_merge(cfg, raw if isinstance(raw, dict) else {})
    if isinstance(overrides, dict):
        cfg = _deep_merge(cfg, overrides)
    return _normalize_config(cfg)


DEFAULT_EVOLUTION_CONFIG: dict[str, Any] = {
    "enabled": True,
    "auto_promotion_enabled": True,
    "display_enabled": True,
    "summary_polling_seconds": 10,
    "timeline_limit": DEFAULT_TIMELINE_LIMIT,
    "audit_retention": DEFAULT_AUDIT_RETENTION,
    "reflection": {
        "turn_cadence": DEFAULT_TURN_REFLECTION_CADENCE,
        "bot_day_cadence": 1,
        "allow_empty_reflection": False,
    },
    "auto_fields": {
        "values": True,
        "speaking_style": True,
        "profile_tags": True,
    },
    "thresholds": {
        "backstory_support_signals": 2,
        "backstory_major_event_signals": 1,
        "profile_tags_support_signals": 3,
        "profile_tags_windows": 2,
        "speaking_style_support_signals": 3,
        "soft_values_support_signals": 2,
        "non_negotiable_support_signals": 4,
        "non_negotiable_windows": 3,
    },
    "field_protection": {
        "forbidden_paths": [
            "profile.name",
            "profile.birth_date",
            "profile.identity",
            "profile.base_identity",
        ],
        "occupation_requires_major": True,
    },
}


@dataclass
class EvolutionDiff:
    field_path: str
    before: Any
    after: Any


def _default_state() -> dict[str, Any]:
    return {
        "signals": [],
        "hypotheses": [],
        "pending_promotions": [],
        "applied_changes": [],
        "suppressed_changes": [],
        "runtime_reflection": {
            "shared_growth_summary": "",
            "life_growth_summary": "",
            "active_style_drift": [],
            "active_value_drift": [],
            "active_personality_drift": [],
            "latest_relationship_drift": "",
        },
        "diagnostics": [],
        "effective_turn_count": 0,
        "last_reflection_turn": 0,
        "last_reflection_at": "",
        "last_reflection_bot_date": "",
        "last_promotion_at": "",
        "last_seen_relationship_label": "",
        "meta": {
            "version": 1,
        },
    }


def _normalize_state(data: dict[str, Any]) -> dict[str, Any]:
    merged = _deep_merge(_default_state(), data if isinstance(data, dict) else {})
    for key in (
        "signals",
        "hypotheses",
        "pending_promotions",
        "applied_changes",
        "suppressed_changes",
        "diagnostics",
    ):
        if not isinstance(merged.get(key), list):
            merged[key] = []
    if not isinstance(merged.get("runtime_reflection"), dict):
        merged["runtime_reflection"] = copy.deepcopy(_default_state()["runtime_reflection"])
    return merged


def _normalize_config(data: dict[str, Any]) -> dict[str, Any]:
    cfg = copy.deepcopy(DEFAULT_EVOLUTION_CONFIG)
    cfg = _deep_merge(cfg, data if isinstance(data, dict) else {})
    reflection = cfg.get("reflection")
    if not isinstance(reflection, dict):
        reflection = {}
        cfg["reflection"] = reflection
    reflection["turn_cadence"] = max(1, int(reflection.get("turn_cadence", DEFAULT_TURN_REFLECTION_CADENCE)))
    reflection["bot_day_cadence"] = max(1, int(reflection.get("bot_day_cadence", 1)))
    cfg["timeline_limit"] = max(1, int(cfg.get("timeline_limit", DEFAULT_TIMELINE_LIMIT)))
    cfg["audit_retention"] = max(50, int(cfg.get("audit_retention", DEFAULT_AUDIT_RETENTION)))
    thresholds = cfg.get("thresholds")
    if not isinstance(thresholds, dict):
        thresholds = {}
        cfg["thresholds"] = thresholds
    auto_fields = cfg.get("auto_fields")
    if not isinstance(auto_fields, dict):
        auto_fields = {}
        cfg["auto_fields"] = auto_fields
    field_protection = cfg.get("field_protection")
    if not isinstance(field_protection, dict):
        field_protection = {}
        cfg["field_protection"] = field_protection
    return cfg


def _deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in (updates or {}).items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _utcnow_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _compact_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _unique_list(items: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for item in items:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, (dict, list)) else str(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


class PersonaEvolutionEngine:
    def __init__(
        self,
        *,
        bot_id: str,
        persona_dir: str | Path | None,
        config: dict[str, Any] | None = None,
    ):
        self.bot_id = bot_id
        self.persona_dir = Path(persona_dir) if persona_dir else None
        self.runtime_profile_path = runtime_profile_path_from_persona_dir(self.persona_dir)
        self.state_path = evolution_state_path_from_persona_dir(self.persona_dir)
        self.audit_path = evolution_audit_path_from_persona_dir(self.persona_dir)
        self.config_path = evolution_config_path_from_persona_dir(self.persona_dir)
        self.config_overrides = config if isinstance(config, dict) else {}
        self._summarizer: Any = None

    def set_summarizer(self, summarizer: Any) -> None:
        self._summarizer = summarizer

    def get_config(self) -> dict[str, Any]:
        return load_evolution_config(self.persona_dir, self.config_overrides)

    def get_state(self) -> dict[str, Any]:
        return load_evolution_state(self.persona_dir)

    def _save_state(self, state: dict[str, Any]) -> None:
        path = self.state_path
        if not path:
            return
        _write_json_atomic(path, _normalize_state(state))

    def _append_audit(self, event: dict[str, Any]) -> None:
        path = self.audit_path
        if not path:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = copy.deepcopy(event)
        payload.setdefault("id", uuid.uuid4().hex)
        payload.setdefault("created_at", _utcnow_iso())
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._trim_audit_if_needed()

    def _trim_audit_if_needed(self) -> None:
        path = self.audit_path
        if not path or not path.exists():
            return
        retention = self.get_config().get("audit_retention", DEFAULT_AUDIT_RETENTION)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return
        if len(lines) <= retention:
            return
        path.write_text("\n".join(lines[-retention:]) + "\n", encoding="utf-8")

    def _load_json_file(self, filename: str) -> dict[str, Any]:
        if not self.persona_dir:
            return {}
        path = self.persona_dir / filename
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_persona_file(self, filename: str, data: dict[str, Any]) -> None:
        if not self.persona_dir:
            return
        _write_json_atomic(self.persona_dir / filename, data)

    async def capture_turn(
        self,
        *,
        user_input: str,
        bot_output: str,
        relationship_state: dict[str, Any] | None = None,
        turn_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cfg = self.get_config()
        if not cfg.get("enabled", True):
            return {"captured": 0, "signals": [], "reflected": False}

        state = self.get_state()
        user_text = _compact_text(user_input)
        bot_text = _compact_text(bot_output)
        relationship_state = dict(relationship_state or {})
        signals: list[dict[str, Any]] = []
        effective = self._is_effective_turn(user_text)
        if effective:
            state["effective_turn_count"] = int(state.get("effective_turn_count", 0)) + 1

        window_index = int(state.get("effective_turn_count", 0)) // max(1, cfg["reflection"]["turn_cadence"])
        created_at = _utcnow_iso()
        relationship_label = str(relationship_state.get("relationship_label") or "").strip()

        feedback_signal = self._infer_feedback_signal(
            user_text=user_text,
            bot_text=bot_text,
            relationship_state=relationship_state,
            created_at=created_at,
            window_index=window_index,
        )
        if feedback_signal:
            signals.append(feedback_signal)

        shared_signal = self._infer_shared_experience_signal(
            user_text=user_text,
            created_at=created_at,
            window_index=window_index,
        )
        if shared_signal:
            signals.append(shared_signal)

        style_signal = self._infer_style_signal(
            user_text=user_text,
            bot_text=bot_text,
            created_at=created_at,
            window_index=window_index,
        )
        if style_signal:
            signals.append(style_signal)

        if relationship_label:
            previous_label = str(state.get("last_seen_relationship_label") or "").strip()
            if previous_label and previous_label != relationship_label:
                signals.append(
                    self._build_signal(
                        source_kind="relationship",
                        dimension="relationship",
                        subtype="boundary_shift",
                        direction="shift",
                        confidence=0.88,
                        stability=0.72,
                        novelty=0.66,
                        importance=0.86,
                        summary=f"关系阶段从「{previous_label}」变化为「{relationship_label}」。",
                        evidence_refs=[user_text[:120]] if user_text else [],
                        candidate_patch={},
                        created_at=created_at,
                        window_index=window_index,
                        reason="relationship_label_changed",
                    )
                )
            state["last_seen_relationship_label"] = relationship_label

        for signal in signals:
            state["signals"].append(signal)
            self._append_audit(
                {
                    "id": signal["id"],
                    "created_at": signal["created_at"],
                    "event_type": "signal_captured",
                    "dimension": signal["dimension"],
                    "status": signal["status"],
                    "summary": signal["summary"],
                    "evidence_count": len(signal.get("evidence_refs") or []),
                    "payload": signal,
                    "human_readable_reason": self._signal_reason(signal),
                }
            )

        reflected = False
        reflect_reason = ""
        if any(signal.get("importance", 0) >= 0.85 for signal in signals):
            reflect_reason = "high_importance_signal"
        elif effective and (
            int(state.get("effective_turn_count", 0)) - int(state.get("last_reflection_turn", 0))
            >= cfg["reflection"]["turn_cadence"]
        ):
            reflect_reason = "periodic_turn_cadence"

        self._save_state(state)
        if reflect_reason:
            await self.reflect(reason=reflect_reason)
            reflected = True

        return {
            "captured": len(signals),
            "signals": signals,
            "reflected": reflected,
        }

    async def capture_relationship_state(
        self,
        relationship_state: dict[str, Any] | None,
        *,
        turn_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = self.get_state()
        relationship_state = dict(relationship_state or {})
        label = str(relationship_state.get("relationship_label") or "").strip()
        previous = str(state.get("last_seen_relationship_label") or "").strip()
        state["last_seen_relationship_label"] = label
        self._save_state(state)
        if not label or not previous or previous == label:
            return {"captured": 0}
        signal = self._build_signal(
            source_kind="relationship",
            dimension="relationship",
            subtype="boundary_shift",
            direction="shift",
            confidence=0.92,
            stability=0.9,
            novelty=0.74,
            importance=0.9,
            summary=f"关系标签从「{previous}」调整为「{label}」。",
            evidence_refs=[f"relationship_label:{previous}->{label}"],
            candidate_patch={},
            created_at=_utcnow_iso(),
            window_index=int(state.get("effective_turn_count", 0)) // max(1, self.get_config()["reflection"]["turn_cadence"]),
            reason="relationship_state_store",
        )
        state["signals"].append(signal)
        self._save_state(state)
        self._append_audit(
            {
                "id": signal["id"],
                "created_at": signal["created_at"],
                "event_type": "signal_captured",
                "dimension": signal["dimension"],
                "status": signal["status"],
                "summary": signal["summary"],
                "evidence_count": 1,
                "payload": signal,
                "human_readable_reason": "关系状态存储层确认了新的关系阶段。",
            }
        )
        await self.reflect(reason="relationship_label_changed")
        return {"captured": 1}

    async def capture_life_event(
        self,
        event: Any,
        *,
        event_type: str,
        runtime_update: dict[str, Any] | None = None,
        runtime_profile_before: dict[str, Any] | None = None,
        runtime_profile_after: dict[str, Any] | None = None,
        relationship_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cfg = self.get_config()
        if not cfg.get("enabled", True):
            return {"captured": 0}

        state = self.get_state()
        created_at = _utcnow_iso()
        summary = _compact_text(getattr(event, "description", "") or "")
        mood_tags = list(getattr(event, "mood_tags", []) or [])
        update = runtime_update if isinstance(runtime_update, dict) else {}
        patch: dict[str, Any] = {"backstory": {}}
        if update.get("shared_experience"):
            patch["backstory"]["shared_experiences"] = [str(update["shared_experience"]).strip()]
        if update.get("life_experience"):
            patch["backstory"]["life_experiences"] = [str(update["life_experience"]).strip()]
        if update.get("shared_growth_summary"):
            patch["backstory"]["shared_growth_summary"] = str(update["shared_growth_summary"]).strip()
        if update.get("life_growth_summary"):
            patch["backstory"]["life_growth_summary"] = str(update["life_growth_summary"]).strip()
        dimension = "backstory"
        subtype = "life_experience" if event_type in {"major", "milestone", "birthday"} else "shared_experience"
        direction = "intensify" if event_type in {"major", "milestone", "birthday"} else "nudge"
        signal = self._build_signal(
            source_kind="life_event",
            dimension=dimension,
            subtype=subtype,
            direction=direction,
            confidence=0.94 if event_type in {"major", "milestone", "birthday"} else 0.8,
            stability=0.92 if event_type in {"major", "milestone", "birthday"} else 0.66,
            novelty=0.82,
            importance=0.95 if event_type in {"major", "milestone", "birthday"} else 0.72,
            summary=summary or f"记录了一次新的 {event_type} 事件。",
            evidence_refs=[summary, *[str(tag) for tag in mood_tags[:3]]],
            candidate_patch=patch,
            created_at=created_at,
            window_index=int(state.get("effective_turn_count", 0)) // max(1, self.get_config()["reflection"]["turn_cadence"]),
            reason=f"life_event:{event_type}",
            extras={
                "life_event_type": event_type,
                "runtime_before": runtime_profile_before or {},
                "runtime_after": runtime_profile_after or {},
                "relationship_state": relationship_state or {},
            },
        )
        state["signals"].append(signal)
        self._save_state(state)
        self._append_audit(
            {
                "id": signal["id"],
                "created_at": created_at,
                "event_type": "signal_captured",
                "dimension": signal["dimension"],
                "status": signal["status"],
                "summary": signal["summary"],
                "evidence_count": len(signal.get("evidence_refs") or []),
                "payload": signal,
                "human_readable_reason": f"{event_type} 事件会立即进入演化链路，先影响运行态，再进入反思判断。",
            }
        )
        await self.reflect(reason=f"life_event_{event_type}")
        return {"captured": 1}

    async def reflect(self, *, reason: str = "manual") -> dict[str, Any]:
        cfg = self.get_config()
        state = self.get_state()
        signals = list(state.get("signals") or [])
        active_signals = [signal for signal in signals if signal.get("status") in {"captured", "merged"}]
        if not active_signals and not cfg["reflection"].get("allow_empty_reflection", False):
            return {"ok": True, "reflected": False, "message": "no_active_signals"}

        hypotheses, pending_promotions, suppressed_changes, diagnostics = self._build_reflection_outputs(
            active_signals=active_signals,
            existing_pending=state.get("pending_promotions") or [],
            cfg=cfg,
        )
        runtime_reflection = self._build_runtime_reflection(active_signals)
        reflection_id = uuid.uuid4().hex
        created_at = _utcnow_iso()

        for signal in active_signals:
            signal["status"] = "merged"

        state["signals"] = signals
        state["hypotheses"] = hypotheses
        state["pending_promotions"] = pending_promotions
        state["suppressed_changes"] = suppressed_changes
        state["runtime_reflection"] = runtime_reflection
        state["diagnostics"] = diagnostics
        state["last_reflection_at"] = created_at
        state["last_reflection_turn"] = int(state.get("effective_turn_count", 0))
        self._save_state(state)

        event = {
            "id": reflection_id,
            "created_at": created_at,
            "event_type": "reflection_generated",
            "dimension": "mixed",
            "status": "runtime",
            "summary": self._reflection_summary(runtime_reflection, pending_promotions, suppressed_changes),
            "evidence_count": len(active_signals),
            "payload": {
                "reason": reason,
                "hypotheses": hypotheses,
                "pending_promotions": pending_promotions,
                "suppressed_changes": suppressed_changes,
                "runtime_reflection": runtime_reflection,
                "diagnostics": diagnostics,
            },
            "human_readable_reason": self._humanize_diagnostics(diagnostics),
        }
        self._append_audit(event)

        if cfg.get("auto_promotion_enabled", True) and pending_promotions:
            await self.promote(reason="auto_reflection")

        return {
            "ok": True,
            "reflected": True,
            "hypotheses": hypotheses,
            "pending_promotions": pending_promotions,
            "suppressed_changes": suppressed_changes,
        }

    async def promote(self, *, reason: str = "manual") -> dict[str, Any]:
        cfg = self.get_config()
        if not cfg.get("auto_promotion_enabled", True) and reason != "manual":
            return {"ok": True, "applied": []}
        state = self.get_state()
        applied: list[dict[str, Any]] = []
        pending = list(state.get("pending_promotions") or [])
        keep: list[dict[str, Any]] = []
        for candidate in pending:
            if not candidate.get("auto_apply", True) and reason != "manual":
                keep.append(candidate)
                continue
            result = await self.apply_core_patch(str(candidate.get("id") or ""), approval_reason=reason)
            if result.get("applied"):
                applied.append(result)
            else:
                keep.append(candidate)
        state = self.get_state()
        state["pending_promotions"] = keep
        if applied:
            state["last_promotion_at"] = _utcnow_iso()
        self._save_state(state)
        return {"ok": True, "applied": applied}

    async def apply_core_patch(self, candidate_id: str, *, approval_reason: str = "manual") -> dict[str, Any]:
        state = self.get_state()
        candidates = list(state.get("pending_promotions") or [])
        candidate = next((item for item in candidates if str(item.get("id") or "") == str(candidate_id)), None)
        if not candidate:
            return {"ok": False, "applied": False, "error": "candidate_not_found"}

        patch = candidate.get("candidate_patch") if isinstance(candidate.get("candidate_patch"), dict) else {}
        before_files = {
            "profile": self._load_json_file("profile.json"),
            "backstory": self._load_json_file("backstory.json"),
            "speaking_style": self._load_json_file("speaking_style.json"),
            "values": self._load_json_file("values.json"),
        }
        after_files = copy.deepcopy(before_files)
        diffs: list[EvolutionDiff] = []
        protected_hit = self._protected_reason_for_patch(candidate, patch)
        if protected_hit:
            candidate["status"] = "suppressed"
            candidate["suppression_reason"] = protected_hit
            state["suppressed_changes"].append(
                {
                    "id": uuid.uuid4().hex,
                    "candidate_id": candidate_id,
                    "summary": candidate.get("summary", ""),
                    "reason": protected_hit,
                    "created_at": _utcnow_iso(),
                }
            )
            state["pending_promotions"] = [item for item in candidates if str(item.get("id")) != str(candidate_id)]
            self._save_state(state)
            self._append_audit(
                {
                    "id": uuid.uuid4().hex,
                    "created_at": _utcnow_iso(),
                    "event_type": "promotion_suppressed",
                    "dimension": candidate.get("dimension", "mixed"),
                    "status": "suppressed",
                    "summary": candidate.get("summary", ""),
                    "evidence_count": int(candidate.get("support_count", 0)),
                    "payload": {"candidate": candidate},
                    "human_readable_reason": protected_hit,
                }
            )
            return {"ok": False, "applied": False, "error": protected_hit}

        for file_key, filename in (
            ("profile", "profile.json"),
            ("backstory", "backstory.json"),
            ("speaking_style", "speaking_style.json"),
            ("values", "values.json"),
        ):
            update = patch.get(file_key)
            if not isinstance(update, dict):
                continue
            self._apply_nested_update(
                target=after_files[file_key],
                update=update,
                prefix=file_key,
                diffs=diffs,
            )
            if after_files[file_key] != before_files[file_key]:
                self._write_persona_file(filename, after_files[file_key])

        state = self.get_state()
        state["pending_promotions"] = [item for item in candidates if str(item.get("id")) != str(candidate_id)]
        state["applied_changes"].append(
            {
                "id": uuid.uuid4().hex,
                "candidate_id": candidate_id,
                "summary": candidate.get("summary", ""),
                "created_at": _utcnow_iso(),
                "diffs": [diff.__dict__ for diff in diffs],
            }
        )
        state["last_promotion_at"] = _utcnow_iso()
        for signal in state.get("signals") or []:
            if signal.get("status") == "merged" and signal.get("summary") == candidate.get("summary"):
                signal["status"] = "promoted"
        self._save_state(state)

        event_id = uuid.uuid4().hex
        self._append_audit(
            {
                "id": event_id,
                "created_at": _utcnow_iso(),
                "event_type": "core_patch_applied",
                "dimension": candidate.get("dimension", "mixed"),
                "status": "promoted",
                "summary": candidate.get("summary", ""),
                "evidence_count": int(candidate.get("support_count", 0)),
                "payload": {
                    "candidate": candidate,
                    "diffs": [diff.__dict__ for diff in diffs],
                    "approval_reason": approval_reason,
                },
                "human_readable_reason": candidate.get("promotion_reason") or "证据达到阈值后，这次变化已写入核心 persona。",
            }
        )
        return {
            "ok": True,
            "applied": True,
            "event_id": event_id,
            "diffs": [diff.__dict__ for diff in diffs],
        }

    async def reject_promotion(self, candidate_id: str, reason: str) -> dict[str, Any]:
        state = self.get_state()
        pending = list(state.get("pending_promotions") or [])
        candidate = next((item for item in pending if str(item.get("id")) == str(candidate_id)), None)
        if not candidate:
            return {"ok": False, "error": "candidate_not_found"}
        state["pending_promotions"] = [item for item in pending if str(item.get("id")) != str(candidate_id)]
        state["suppressed_changes"].append(
            {
                "id": uuid.uuid4().hex,
                "candidate_id": candidate_id,
                "summary": candidate.get("summary", ""),
                "reason": reason,
                "created_at": _utcnow_iso(),
            }
        )
        self._save_state(state)
        self._append_audit(
            {
                "id": uuid.uuid4().hex,
                "created_at": _utcnow_iso(),
                "event_type": "promotion_suppressed",
                "dimension": candidate.get("dimension", "mixed"),
                "status": "suppressed",
                "summary": candidate.get("summary", ""),
                "evidence_count": int(candidate.get("support_count", 0)),
                "payload": {"candidate": candidate, "reason": reason},
                "human_readable_reason": reason,
            }
        )
        return {"ok": True}

    async def rebuild(
        self,
        *,
        relationship_state: dict[str, Any] | None = None,
        life_events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        runtime_profile = load_runtime_profile(self.runtime_profile_path)
        new_state = _default_state()
        created_at = _utcnow_iso()
        rebuild_signals: list[dict[str, Any]] = []

        for item in list(runtime_profile.get("shared_experiences") or [])[:10]:
            rebuild_signals.append(
                self._build_signal(
                    source_kind="episodic",
                    dimension="backstory",
                    subtype="shared_experience",
                    direction="carry",
                    confidence=0.7,
                    stability=0.78,
                    novelty=0.4,
                    importance=0.62,
                    summary=str(item),
                    evidence_refs=[str(item)],
                    candidate_patch={"backstory": {"shared_experiences": [str(item)]}},
                    created_at=created_at,
                    window_index=0,
                    reason="rebuild_runtime_shared",
                )
            )

        for item in list(runtime_profile.get("life_experiences") or [])[:10]:
            rebuild_signals.append(
                self._build_signal(
                    source_kind="self_memory",
                    dimension="backstory",
                    subtype="life_experience",
                    direction="carry",
                    confidence=0.74,
                    stability=0.82,
                    novelty=0.45,
                    importance=0.68,
                    summary=str(item),
                    evidence_refs=[str(item)],
                    candidate_patch={"backstory": {"life_experiences": [str(item)]}},
                    created_at=created_at,
                    window_index=0,
                    reason="rebuild_runtime_life",
                )
            )

        if isinstance(relationship_state, dict) and relationship_state.get("relationship_label"):
            new_state["last_seen_relationship_label"] = str(relationship_state.get("relationship_label"))

        if isinstance(life_events, list):
            for item in life_events[:10]:
                description = _compact_text(item.get("description"))
                if not description:
                    continue
                rebuild_signals.append(
                    self._build_signal(
                        source_kind="life_event",
                        dimension="backstory",
                        subtype="life_experience",
                        direction="carry",
                        confidence=0.76,
                        stability=0.8,
                        novelty=0.52,
                        importance=0.8,
                        summary=description,
                        evidence_refs=[description],
                        candidate_patch={"backstory": {"life_experiences": [description]}},
                        created_at=created_at,
                        window_index=0,
                        reason="rebuild_life_state",
                    )
                )

        new_state["signals"] = rebuild_signals
        self._save_state(new_state)
        self._append_audit(
            {
                "id": uuid.uuid4().hex,
                "created_at": created_at,
                "event_type": "state_rebuilt",
                "dimension": "mixed",
                "status": "runtime",
                "summary": f"已从 runtime、relationship 与 life state 回建 {len(rebuild_signals)} 条演化信号。",
                "evidence_count": len(rebuild_signals),
                "payload": {"signals": rebuild_signals},
                "human_readable_reason": "这次回建会保留运行态痕迹，但不会直接改写核心 persona。",
            }
        )
        await self.reflect(reason="manual_rebuild")
        return {"ok": True, "signals": len(rebuild_signals)}

    def get_snapshot(self) -> dict[str, Any]:
        state = self.get_state()
        runtime_profile = load_runtime_profile(self.runtime_profile_path)
        profile = self._load_json_file("profile.json")
        backstory = self._load_json_file("backstory.json")
        values = self._load_json_file("values.json")
        speaking_style = self._load_json_file("speaking_style.json")
        pending = list(state.get("pending_promotions") or [])
        recent_applied = self._recent_events_count("core_patch_applied", days=7)
        active_signals = [item for item in state.get("signals") or [] if item.get("status") in {"captured", "merged"}]
        suppressed_recent = [item for item in state.get("suppressed_changes") or [] if self._is_recent(item.get("created_at"), 7)]

        phase = "稳定"
        if suppressed_recent:
            phase = "冲突抑制"
        elif pending:
            phase = "待晋升"
        elif recent_applied:
            phase = "已晋升"
        elif active_signals:
            phase = "积累中"

        return {
            "bot_id": self.bot_id,
            "overview": {
                "phase": phase,
                "last_reflection_at": state.get("last_reflection_at", ""),
                "last_promotion_at": state.get("last_promotion_at", ""),
                "active_signal_count": len(active_signals),
                "pending_promotion_count": len(pending),
                "evolution_count_7d": recent_applied + len(suppressed_recent),
            },
            "snapshot": {
                "core": {
                    "personality_tags": profile.get("personality_tags", []),
                    "tone": speaking_style.get("tone", ""),
                    "values_summary": self._build_values_summary(values),
                    "backstory_growth_summary": _compact_text(
                        backstory.get("shared_growth_summary") or backstory.get("life_growth_summary") or backstory.get("summary")
                    ),
                },
                "runtime": {
                    "shared_growth_summary": runtime_profile.get("shared_growth_summary", ""),
                    "life_growth_summary": runtime_profile.get("life_growth_summary", ""),
                    "active_style_drift": state.get("runtime_reflection", {}).get("active_style_drift", []),
                    "active_value_drift": state.get("runtime_reflection", {}).get("active_value_drift", []),
                },
                "pending": [self._promotion_candidate_view(item) for item in pending[:6]],
            },
            "diagnostics": self._build_readable_diagnostics(state),
        }

    def get_timeline(
        self,
        *,
        cursor: str | None = None,
        limit: int = DEFAULT_TIMELINE_LIMIT,
        dimension: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        items = self._load_audit_items()
        if dimension and dimension != "all":
            items = [item for item in items if str(item.get("dimension") or "") == dimension]
        if status and status != "all":
            mapped_statuses = {
                "promoted": {"promoted"},
                "suppressed": {"suppressed"},
                "runtime": {"runtime", "captured", "merged"},
            }
            allowed = mapped_statuses.get(status, {status})
            items = [item for item in items if str(item.get("status") or "") in allowed]
        items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        offset = int(cursor or 0)
        page = items[offset: offset + max(1, limit)]
        next_cursor = offset + len(page)
        return {
            "items": [self._timeline_item_view(item) for item in page],
            "next_cursor": str(next_cursor) if next_cursor < len(items) else None,
            "has_more": next_cursor < len(items),
        }

    def get_event_detail(self, event_id: str) -> dict[str, Any] | None:
        item = next((row for row in self._load_audit_items() if str(row.get("id")) == str(event_id)), None)
        if not item:
            return None
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        diffs = payload.get("diffs") if isinstance(payload.get("diffs"), list) else []
        signal_payload = payload if item.get("event_type") == "signal_captured" else payload.get("candidate", payload)
        return {
            "id": item.get("id"),
            "created_at": item.get("created_at"),
            "event_type": item.get("event_type"),
            "dimension": item.get("dimension"),
            "status": item.get("status"),
            "summary": item.get("summary", ""),
            "human_readable_reason": item.get("human_readable_reason", ""),
            "evidence_refs": list(signal_payload.get("evidence_refs") or []),
            "scores": {
                "confidence": signal_payload.get("confidence"),
                "stability": signal_payload.get("stability"),
                "novelty": signal_payload.get("novelty"),
                "importance": signal_payload.get("importance"),
            },
            "candidate_patch": signal_payload.get("candidate_patch") if isinstance(signal_payload.get("candidate_patch"), dict) else {},
            "reason": signal_payload.get("promotion_reason") or signal_payload.get("suppression_reason") or item.get("human_readable_reason", ""),
            "diffs": diffs,
        }

    def get_state_view(self) -> dict[str, Any]:
        state = self.get_state()
        return {
            "state": state,
            "human_readable_diagnostics": self._build_readable_diagnostics(state),
        }

    def get_diagnostics(self) -> dict[str, Any]:
        state = self.get_state()
        return {
            "captured_signal_count": len([item for item in state.get("signals") or [] if item.get("status") in {"captured", "merged"}]),
            "pending_promotion_count": len(state.get("pending_promotions") or []),
            "last_reflection_at": state.get("last_reflection_at", ""),
            "last_promotion_at": state.get("last_promotion_at", ""),
            "suppressed_promotions": len(state.get("suppressed_changes") or []),
        }

    def get_link_refs(self, *, limit: int = 4) -> dict[str, Any]:
        safe_limit = max(1, int(limit))
        timeline_items = self.get_timeline(limit=safe_limit).get("items", [])
        pending = list(self.get_state().get("pending_promotions") or [])
        diagnostics = self.get_diagnostics()
        return {
            "timeline_preview": timeline_items[:safe_limit],
            "latest_event_ids": [str(item.get("id") or "") for item in timeline_items[:safe_limit] if str(item.get("id") or "").strip()],
            "latest_signal_ids": [
                str(item.get("id") or "")
                for item in timeline_items[:safe_limit]
                if str(item.get("event_type") or "") == "signal_captured" and str(item.get("id") or "").strip()
            ],
            "latest_pending_candidate_ids": [
                str(item.get("id") or "")
                for item in pending[:safe_limit]
                if str(item.get("id") or "").strip()
            ],
            "pending_candidates": [self._promotion_candidate_view(item) for item in pending[:safe_limit]],
            "diagnostics": diagnostics,
        }

    def _load_audit_items(self) -> list[dict[str, Any]]:
        path = self.audit_path
        if not path or not path.exists():
            return []
        items: list[dict[str, Any]] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    items.append(payload)
        except Exception:
            return []
        return items

    def _build_signal(
        self,
        *,
        source_kind: str,
        dimension: str,
        subtype: str,
        direction: str,
        confidence: float,
        stability: float,
        novelty: float,
        importance: float,
        summary: str,
        evidence_refs: list[str],
        candidate_patch: dict[str, Any],
        created_at: str,
        window_index: int,
        reason: str,
        extras: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": uuid.uuid4().hex,
            "created_at": created_at,
            "source_kind": source_kind,
            "dimension": dimension,
            "subtype": subtype,
            "direction": direction,
            "confidence": round(confidence, 3),
            "stability": round(stability, 3),
            "novelty": round(novelty, 3),
            "importance": round(importance, 3),
            "summary": _compact_text(summary),
            "evidence_refs": [item for item in evidence_refs if _compact_text(item)],
            "candidate_patch": candidate_patch,
            "status": "captured",
            "window_index": int(window_index),
            "reason": reason,
            **(extras or {}),
        }

    def _infer_feedback_signal(
        self,
        *,
        user_text: str,
        bot_text: str,
        relationship_state: dict[str, Any],
        created_at: str,
        window_index: int,
    ) -> dict[str, Any] | None:
        if not user_text:
            return None
        lower = user_text.lower()
        if "你最近" in user_text or "你变得" in user_text or "希望你" in user_text or "别总是" in user_text:
            summary = user_text[:120]
            if any(token in user_text for token in ("温柔", "冷淡", "直接", "黏人", "体贴", "稳重")):
                trait = next((token for token in ("温柔", "冷淡", "直接", "黏人", "体贴", "稳重") if token in user_text), "")
                return self._build_signal(
                    source_kind="turn",
                    dimension="personality",
                    subtype="self_concept",
                    direction="nudge",
                    confidence=0.77,
                    stability=0.63,
                    novelty=0.7,
                    importance=0.76,
                    summary=f"用户直接评价 Bot 最近的性格变化：{summary}",
                    evidence_refs=[summary],
                    candidate_patch={"profile": {"personality_tags": [trait]}} if trait else {},
                    created_at=created_at,
                    window_index=window_index,
                    reason="direct_user_feedback_personality",
                )
            if any(token in user_text for token in ("说话", "语气", "表达", "口头禅")):
                return self._build_signal(
                    source_kind="turn",
                    dimension="speaking_style",
                    subtype="style_feedback",
                    direction="nudge",
                    confidence=0.8,
                    stability=0.66,
                    novelty=0.72,
                    importance=0.78,
                    summary=f"用户直接评价了 Bot 的说话方式：{summary}",
                    evidence_refs=[summary, bot_text[:120]],
                    candidate_patch={"speaking_style": {"style_notes": [summary]}},
                    created_at=created_at,
                    window_index=window_index,
                    reason="direct_user_feedback_style",
                )
        if any(token in lower for token in ("谢谢", "喜欢你", "信任你", "离不开你")):
            return self._build_signal(
                source_kind="turn",
                dimension="relationship",
                subtype="shared_experience",
                direction="warm",
                confidence=0.72,
                stability=0.68,
                novelty=0.56,
                importance=0.74,
                summary=f"用户对 Bot 给出了正向关系反馈：{user_text[:120]}",
                evidence_refs=[user_text[:120]],
                candidate_patch={"values": {"relationship_principles": ["更重视稳定回应与被信任的关系感"]}},
                created_at=created_at,
                window_index=window_index,
                reason="positive_relationship_feedback",
            )
        return None

    def _infer_shared_experience_signal(
        self,
        *,
        user_text: str,
        created_at: str,
        window_index: int,
    ) -> dict[str, Any] | None:
        if len(user_text) < 10:
            return None
        if "我们" not in user_text and "一起" not in user_text and "上次" not in user_text:
            return None
        return self._build_signal(
            source_kind="turn",
            dimension="backstory",
            subtype="shared_experience",
            direction="carry",
            confidence=0.69,
            stability=0.58,
            novelty=0.6,
            importance=0.64,
            summary=f"这轮对话提到了共同经历或共同处境：{user_text[:120]}",
            evidence_refs=[user_text[:120]],
            candidate_patch={"backstory": {"shared_experiences": [user_text[:120]]}},
            created_at=created_at,
            window_index=window_index,
            reason="shared_turn_reference",
        )

    def _infer_style_signal(
        self,
        *,
        user_text: str,
        bot_text: str,
        created_at: str,
        window_index: int,
    ) -> dict[str, Any] | None:
        if not bot_text or len(bot_text) < 6:
            return None
        if "。" in bot_text and any(token in user_text for token in ("怎么想", "为什么这么说", "你现在")):
            return self._build_signal(
                source_kind="self_memory",
                dimension="speaking_style",
                subtype="self_concept",
                direction="stabilize",
                confidence=0.6,
                stability=0.54,
                novelty=0.46,
                importance=0.52,
                summary="Bot 在解释自身想法时形成了较稳定的表达姿态。",
                evidence_refs=[bot_text[:120]],
                candidate_patch={"speaking_style": {"style_notes": ["最近更习惯先解释感受，再给出回应。"]}},
                created_at=created_at,
                window_index=window_index,
                reason="bot_output_style_trace",
            )
        return None

    def _is_effective_turn(self, user_text: str) -> bool:
        if not user_text or len(user_text) <= 8:
            return False
        stripped = user_text.strip()
        if stripped.startswith("/"):
            return False
        if stripped in {"嗯", "哦", "好", "行", "在", "收到", "ok", "OK"}:
            return False
        if all(ch in "!?！？~～.,，。 " for ch in stripped):
            return False
        return True

    def _build_reflection_outputs(
        self,
        *,
        active_signals: list[dict[str, Any]],
        existing_pending: list[dict[str, Any]],
        cfg: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for signal in active_signals:
            path = self._candidate_primary_path(signal.get("candidate_patch") if isinstance(signal.get("candidate_patch"), dict) else {})
            key = f"{signal.get('dimension')}|{path}"
            grouped.setdefault(key, []).append(signal)

        hypotheses: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        suppressed: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []

        for key, supports in grouped.items():
            support_count = len(supports)
            windows = len({int(item.get("window_index", 0)) for item in supports})
            avg_stability = sum(float(item.get("stability", 0) or 0) for item in supports) / max(1, support_count)
            avg_confidence = sum(float(item.get("confidence", 0) or 0) for item in supports) / max(1, support_count)
            dimension = str(supports[0].get("dimension") or "")
            candidate_patch = self._merge_candidate_patches([item.get("candidate_patch") for item in supports])
            primary_path = self._candidate_primary_path(candidate_patch)
            threshold = self._threshold_for_path(primary_path, cfg)
            if primary_path.startswith("backstory.") and self._has_major_backstory_support(supports):
                threshold = {
                    **threshold,
                    "signals": int(cfg.get("thresholds", {}).get("backstory_major_event_signals", 1)),
                }
            meets_support = support_count >= threshold["signals"]
            meets_windows = windows >= threshold["windows"]
            self_evidence_required = threshold.get("requires_self_evidence", False)
            has_self_evidence = any(str(item.get("source_kind") or "") in {"self_memory", "life_event"} for item in supports)
            allowed, block_reason = self._is_path_auto_allowed(primary_path, cfg)
            summary = supports[-1].get("summary", "")

            hypothesis = {
                "id": uuid.uuid4().hex,
                "dimension": dimension,
                "field_path": primary_path,
                "summary": summary,
                "support_count": support_count,
                "window_count": windows,
                "avg_stability": round(avg_stability, 3),
                "avg_confidence": round(avg_confidence, 3),
                "threshold": threshold,
            }
            hypotheses.append(hypothesis)

            if meets_support and meets_windows and (not self_evidence_required or has_self_evidence) and allowed:
                pending.append(
                    {
                        "id": uuid.uuid4().hex,
                        "dimension": dimension,
                        "field_path": primary_path,
                        "summary": summary,
                        "support_count": support_count,
                        "window_count": windows,
                        "candidate_patch": candidate_patch,
                        "status": "pending",
                        "auto_apply": True,
                        "promotion_reason": self._promotion_reason(primary_path, support_count, windows),
                    }
                )
                diagnostics.append(
                    {
                        "field_path": primary_path,
                        "status": "ready",
                        "message": self._promotion_reason(primary_path, support_count, windows),
                    }
                )
            else:
                reason = block_reason or self._suppression_reason(
                    primary_path=primary_path,
                    support_count=support_count,
                    threshold=threshold,
                    windows=windows,
                    has_self_evidence=has_self_evidence,
                )
                suppressed.append(
                    {
                        "id": uuid.uuid4().hex,
                        "dimension": dimension,
                        "field_path": primary_path,
                        "summary": summary,
                        "support_count": support_count,
                        "window_count": windows,
                        "reason": reason,
                    }
                )
                diagnostics.append(
                    {
                        "field_path": primary_path,
                        "status": "blocked",
                        "message": reason,
                    }
                )

        existing_pending_ids = {str(item.get("field_path")): item for item in existing_pending if isinstance(item, dict)}
        final_pending = list(existing_pending)
        for item in pending:
            if item["field_path"] in existing_pending_ids:
                continue
            final_pending.append(item)
        return hypotheses, final_pending, suppressed, diagnostics

    def _build_runtime_reflection(self, signals: list[dict[str, Any]]) -> dict[str, Any]:
        shared = [item.get("summary", "") for item in signals if item.get("dimension") == "backstory" and item.get("subtype") == "shared_experience"]
        life = [item.get("summary", "") for item in signals if item.get("source_kind") == "life_event"]
        style = [item.get("summary", "") for item in signals if item.get("dimension") == "speaking_style"]
        values = [item.get("summary", "") for item in signals if item.get("dimension") in {"values", "relationship"}]
        personality = [item.get("summary", "") for item in signals if item.get("dimension") == "personality"]
        relationship = [item.get("summary", "") for item in signals if item.get("dimension") == "relationship"]
        return {
            "shared_growth_summary": shared[-1] if shared else "",
            "life_growth_summary": life[-1] if life else "",
            "active_style_drift": _unique_list([item for item in style if item][:3]),
            "active_value_drift": _unique_list([item for item in values if item][:3]),
            "active_personality_drift": _unique_list([item for item in personality if item][:3]),
            "latest_relationship_drift": relationship[-1] if relationship else "",
        }

    def _merge_candidate_patches(self, patches: list[Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for patch in patches:
            if not isinstance(patch, dict):
                continue
            result = self._merge_nested_patch(result, patch)
        return result

    def _merge_nested_patch(self, base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
        merged = copy.deepcopy(base)
        for key, value in update.items():
            if isinstance(value, dict):
                current = merged.get(key) if isinstance(merged.get(key), dict) else {}
                merged[key] = self._merge_nested_patch(current, value)
            elif isinstance(value, list):
                current = list(merged.get(key, []) or [])
                merged[key] = _unique_list([*current, *value])
            else:
                merged[key] = value
        return merged

    def _candidate_primary_path(self, patch: dict[str, Any]) -> str:
        for file_key in ("profile", "speaking_style", "values", "backstory"):
            value = patch.get(file_key)
            if isinstance(value, dict):
                for inner_key in value.keys():
                    return f"{file_key}.{inner_key}"
        return "unknown"

    def _threshold_for_path(self, path: str, cfg: dict[str, Any]) -> dict[str, Any]:
        thresholds = cfg.get("thresholds", {})
        if path.startswith("backstory."):
            return {"signals": int(thresholds.get("backstory_support_signals", 2)), "windows": 1}
        if path == "profile.personality_tags":
            return {
                "signals": int(thresholds.get("profile_tags_support_signals", 3)),
                "windows": int(thresholds.get("profile_tags_windows", 2)),
            }
        if path.startswith("speaking_style."):
            return {
                "signals": int(thresholds.get("speaking_style_support_signals", 3)),
                "windows": 1,
                "requires_self_evidence": True,
            }
        if path == "values.non_negotiable":
            return {
                "signals": int(thresholds.get("non_negotiable_support_signals", 4)),
                "windows": int(thresholds.get("non_negotiable_windows", 3)),
            }
        if path.startswith("values."):
            return {"signals": int(thresholds.get("soft_values_support_signals", 2)), "windows": 1}
        if path == "profile.occupation":
            return {"signals": 1, "windows": 1, "requires_major": True}
        return {"signals": 2, "windows": 1}

    def _has_major_backstory_support(self, supports: list[dict[str, Any]]) -> bool:
        return any(
            str(item.get("source_kind") or "") == "life_event"
            and str(item.get("life_event_type") or "") in {"major", "milestone", "birthday"}
            for item in supports
        )

    def _is_path_auto_allowed(self, path: str, cfg: dict[str, Any]) -> tuple[bool, str]:
        protection = cfg.get("field_protection", {})
        forbidden = set(protection.get("forbidden_paths", []) or [])
        if path in forbidden:
            return False, f"{path} 属于硬保护字段，系统不会自动改写。"
        auto_fields = cfg.get("auto_fields", {})
        if path.startswith("values.") and not auto_fields.get("values", True):
            return False, "当前配置禁止自动改 values 相关字段。"
        if path.startswith("speaking_style.") and not auto_fields.get("speaking_style", True):
            return False, "当前配置禁止自动改 speaking_style。"
        if path == "profile.personality_tags" and not auto_fields.get("profile_tags", True):
            return False, "当前配置禁止自动改 personality_tags。"
        return True, ""

    def _suppression_reason(
        self,
        *,
        primary_path: str,
        support_count: int,
        threshold: dict[str, Any],
        windows: int,
        has_self_evidence: bool,
    ) -> str:
        if support_count < threshold["signals"]:
            return f"{primary_path} 还差证据数量，当前 {support_count} 条，阈值 {threshold['signals']} 条。"
        if windows < threshold["windows"]:
            return f"{primary_path} 还没有跨足够的反思窗口，当前 {windows} 个，要求 {threshold['windows']} 个。"
        if threshold.get("requires_self_evidence") and not has_self_evidence:
            return f"{primary_path} 需要包含 Bot 自身输出或人生事件作为行为证据。"
        return f"{primary_path} 暂未满足晋升条件。"

    def _promotion_reason(self, path: str, support_count: int, windows: int) -> str:
        return f"{path} 已累计 {support_count} 条支持信号，并跨越 {windows} 个反思窗口，满足晋升条件。"

    def _reflection_summary(
        self,
        runtime_reflection: dict[str, Any],
        pending_promotions: list[dict[str, Any]],
        suppressed_changes: list[dict[str, Any]],
    ) -> str:
        parts: list[str] = []
        if runtime_reflection.get("shared_growth_summary"):
            parts.append(f"共同经历影响：{runtime_reflection['shared_growth_summary']}")
        if runtime_reflection.get("life_growth_summary"):
            parts.append(f"个人人生影响：{runtime_reflection['life_growth_summary']}")
        if pending_promotions:
            parts.append(f"有 {len(pending_promotions)} 项变化已进入待晋升。")
        if suppressed_changes:
            parts.append(f"有 {len(suppressed_changes)} 项变化因为证据不足或保护规则被压住。")
        return " ".join(parts) if parts else "本次反思未产生新的可晋升变化。"

    def _signal_reason(self, signal: dict[str, Any]) -> str:
        source_kind = signal.get("source_kind")
        if source_kind == "life_event":
            return "这是一次 life event 信号，会先进入运行态，再由反思决定是否晋升。"
        if source_kind == "relationship":
            return "关系状态出现了明确变化，所以系统立即记录了这条演化信号。"
        if source_kind == "self_memory":
            return "Bot 最近自己的表达方式形成了可复用模式，所以被记录为风格证据。"
        return "这条信号来自日常对话，不会直接改核心 persona，只会先进入演化缓冲层。"

    def _humanize_diagnostics(self, diagnostics: list[dict[str, Any]]) -> str:
        if not diagnostics:
            return "这次反思没有发现需要说明的阻塞。"
        return "；".join(str(item.get("message") or "").strip() for item in diagnostics[:4] if str(item.get("message") or "").strip())

    def _build_readable_diagnostics(self, state: dict[str, Any]) -> list[str]:
        diagnostics = list(state.get("diagnostics") or [])
        if diagnostics:
            return [str(item.get("message") or "").strip() for item in diagnostics if str(item.get("message") or "").strip()]
        pending = list(state.get("pending_promotions") or [])
        if pending:
            return ["已有待晋升变化，等待自动或人工批准。"]
        if state.get("signals"):
            return ["变化还在积累中，当前证据不足以进入核心 persona。"]
        return ["当前没有活跃演化信号，Bot 处于稳定阶段。"]

    def _build_values_summary(self, values: dict[str, Any]) -> str:
        parts: list[str] = []
        for key in ("non_negotiable", "soft_values", "relationship_principles", "recent_realizations"):
            raw = values.get(key)
            if isinstance(raw, list) and raw:
                parts.append(" / ".join(str(item) for item in raw[:2]))
        return "；".join(parts[:2])

    def _recent_events_count(self, event_type: str, *, days: int) -> int:
        now = datetime.now().astimezone()
        count = 0
        for item in self._load_audit_items():
            if str(item.get("event_type") or "") != event_type:
                continue
            created_at = self._parse_datetime(item.get("created_at"))
            if created_at and now - created_at <= timedelta(days=days):
                count += 1
        return count

    def _is_recent(self, value: object, days: int) -> bool:
        created_at = self._parse_datetime(value)
        if created_at is None:
            return False
        return datetime.now().astimezone() - created_at <= timedelta(days=days)

    def _parse_datetime(self, value: object) -> Optional[datetime]:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    def _timeline_item_view(self, item: dict[str, Any]) -> dict[str, Any]:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        return {
            "id": item.get("id"),
            "created_at": item.get("created_at"),
            "event_type": item.get("event_type"),
            "dimension": item.get("dimension"),
            "status": item.get("status"),
            "summary": item.get("summary", ""),
            "evidence_count": int(item.get("evidence_count", 0) or 0),
            "wrote_core_persona": str(item.get("event_type") or "") == "core_patch_applied",
            "human_readable_reason": item.get("human_readable_reason", ""),
            "candidate_id": payload.get("candidate", {}).get("id") if isinstance(payload.get("candidate"), dict) else None,
        }

    def _promotion_candidate_view(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item.get("id"),
            "field_path": item.get("field_path", ""),
            "summary": item.get("summary", ""),
            "support_count": item.get("support_count", 0),
            "window_count": item.get("window_count", 0),
            "status": item.get("status", "pending"),
            "promotion_reason": item.get("promotion_reason", ""),
        }

    def _apply_nested_update(
        self,
        *,
        target: dict[str, Any],
        update: dict[str, Any],
        prefix: str,
        diffs: list[EvolutionDiff],
    ) -> None:
        for key, value in update.items():
            path = f"{prefix}.{key}"
            before = copy.deepcopy(target.get(key))
            if isinstance(value, dict):
                current = target.get(key)
                if not isinstance(current, dict):
                    current = {}
                    target[key] = current
                self._apply_nested_update(target=current, update=value, prefix=path, diffs=diffs)
                after = copy.deepcopy(target.get(key))
                if before != after:
                    diffs.append(EvolutionDiff(field_path=path, before=before, after=after))
                continue
            if isinstance(value, list):
                current = list(target.get(key, []) or [])
                after = _unique_list([*current, *value])
                target[key] = after
            else:
                target[key] = value
            after = copy.deepcopy(target.get(key))
            if before != after:
                diffs.append(EvolutionDiff(field_path=path, before=before, after=after))

    def _protected_reason_for_patch(self, candidate: dict[str, Any], patch: dict[str, Any]) -> str:
        primary_path = self._candidate_primary_path(patch)
        allowed, reason = self._is_path_auto_allowed(primary_path, self.get_config())
        if not allowed:
            return reason
        threshold = self._threshold_for_path(primary_path, self.get_config())
        if primary_path == "profile.occupation" and threshold.get("requires_major"):
            if not any(
                str(signal.get("source_kind") or "") == "life_event" and str(signal.get("life_event_type") or "") in {"major", "milestone"}
                for signal in self.get_state().get("signals") or []
            ):
                return "occupation 只能由 verified major life change 改写。"
        if primary_path == "values.non_negotiable" and int(candidate.get("support_count", 0)) < int(threshold.get("signals", 4)):
            return "non_negotiable 属于高保护字段，普通对话证据不足以自动改写。"
        return ""
