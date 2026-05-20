"""Relationship state store.

The relationship layer is intentionally more stable than the extractor output.
LLMs can suggest a stage, but the store owns the durable state and applies
hysteresis so ordinary mood shifts do not rewrite the relationship every turn.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite


class RelationshipStore:
    """Dynamic relationship state between one bot and one user."""

    DEFAULT_LABEL = "朋友"
    DEFAULT_STATUS = "稳定"
    SCORE_SCALE = 100

    DEFAULT_SCORES = {
        "intimacy_score": 25.0,
        "trust_score": 35.0,
        "tension_score": 0.0,
        "affection_score": 30.0,
        "attitude_score": 50.0,
    }

    STAGE_RANK = {
        "疏远": 0,
        "刚认识": 1,
        "朋友": 2,
        "好朋友": 3,
        "暧昧中": 4,
        "恋人": 5,
    }
    RANK_STAGE = {rank: stage for stage, rank in STAGE_RANK.items()}

    def __init__(self, db_path: str | Path, persona_backstory_path: str | None = None):
        self.db_path = str(db_path)
        self._persona_backstory_path = persona_backstory_path

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS relationship_state (
                    bot_id TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT 'default_user',
                    relationship_label TEXT DEFAULT '朋友',
                    relationship_status TEXT DEFAULT '稳定',
                    intimacy_score REAL DEFAULT 25,
                    trust_score REAL DEFAULT 35,
                    tension_score REAL DEFAULT 0,
                    affection_score REAL DEFAULT 30,
                    attitude_score REAL DEFAULT 50,
                    relationship_score REAL DEFAULT 35,
                    stage_confidence REAL DEFAULT 0.55,
                    positive_streak INTEGER DEFAULT 0,
                    negative_streak INTEGER DEFAULT 0,
                    score_scale INTEGER DEFAULT 100,
                    last_conflict_at TEXT,
                    last_repair_at TEXT,
                    last_meaningful_contact_at TEXT,
                    last_stage_change_at TEXT,
                    open_emotional_threads_json TEXT,
                    key_moments_json TEXT,
                    relationship_narrative TEXT,
                    current_posture TEXT,
                    interaction_guidance TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(bot_id, user_id)
                )
                """
            )
            await self._ensure_schema(db)
            await db.commit()

    async def _ensure_schema(self, db):
        cursor = await db.execute("PRAGMA table_info(relationship_state)")
        columns = [row[1] for row in await cursor.fetchall()]
        added_score_scale = False
        migrations = [
            ("relationship_status", "ALTER TABLE relationship_state ADD COLUMN relationship_status TEXT DEFAULT '稳定'"),
            ("relationship_score", "ALTER TABLE relationship_state ADD COLUMN relationship_score REAL DEFAULT 35"),
            ("stage_confidence", "ALTER TABLE relationship_state ADD COLUMN stage_confidence REAL DEFAULT 0.55"),
            ("positive_streak", "ALTER TABLE relationship_state ADD COLUMN positive_streak INTEGER DEFAULT 0"),
            ("negative_streak", "ALTER TABLE relationship_state ADD COLUMN negative_streak INTEGER DEFAULT 0"),
            ("score_scale", "ALTER TABLE relationship_state ADD COLUMN score_scale INTEGER DEFAULT 10"),
            ("last_stage_change_at", "ALTER TABLE relationship_state ADD COLUMN last_stage_change_at TEXT"),
            ("relationship_narrative", "ALTER TABLE relationship_state ADD COLUMN relationship_narrative TEXT"),
            ("current_posture", "ALTER TABLE relationship_state ADD COLUMN current_posture TEXT"),
            ("interaction_guidance", "ALTER TABLE relationship_state ADD COLUMN interaction_guidance TEXT"),
        ]
        for name, ddl in migrations:
            if name not in columns:
                await db.execute(ddl)
                if name == "score_scale":
                    added_score_scale = True

        cursor = await db.execute(
            "SELECT COUNT(*) FROM relationship_state WHERE COALESCE(score_scale, 10) != ?",
            (self.SCORE_SCALE,),
        )
        needs_migration = (await cursor.fetchone())[0] > 0
        if added_score_scale or needs_migration:
            await self._migrate_legacy_scores(db)

    async def _migrate_legacy_scores(self, db):
        cursor = await db.execute(
            """
            SELECT bot_id, user_id, relationship_label, intimacy_score, trust_score,
                   tension_score, affection_score, attitude_score, key_moments_json,
                   updated_at
            FROM relationship_state
            WHERE COALESCE(score_scale, 10) != ?
            """,
            (self.SCORE_SCALE,),
        )
        rows = await cursor.fetchall()
        for row in rows:
            bot_id, user_id, label, intimacy, trust, tension, affection, attitude, moments_json, updated_at = row
            state = {
                "relationship_label": _normalize_stage(label) or self.DEFAULT_LABEL,
                "relationship_status": self.DEFAULT_STATUS,
                "intimacy_score": _legacy_dimension_to_100(intimacy),
                "trust_score": _legacy_dimension_to_100(trust),
                "tension_score": _legacy_tension_to_100(tension),
                "affection_score": _legacy_dimension_to_100(affection),
                "attitude_score": _legacy_score_to_100(attitude),
                "key_moments": _load_json_list(moments_json),
            }
            state["relationship_score"] = self._calculate_relationship_score(state)
            state["relationship_status"] = self._derive_status(state)
            await db.execute(
                """
                UPDATE relationship_state
                SET relationship_label = ?, relationship_status = ?, intimacy_score = ?,
                    trust_score = ?, tension_score = ?, affection_score = ?,
                    attitude_score = ?, relationship_score = ?, stage_confidence = ?,
                    positive_streak = COALESCE(positive_streak, 0),
                    negative_streak = COALESCE(negative_streak, 0),
                    score_scale = ?, last_stage_change_at = COALESCE(last_stage_change_at, ?)
                WHERE bot_id = ? AND user_id = ?
                """,
                (
                    state["relationship_label"],
                    state["relationship_status"],
                    state["intimacy_score"],
                    state["trust_score"],
                    state["tension_score"],
                    state["affection_score"],
                    state["attitude_score"],
                    state["relationship_score"],
                    0.65,
                    self.SCORE_SCALE,
                    updated_at,
                    bot_id,
                    user_id,
                ),
            )

    async def get_state(self, *, bot_id: str, user_id: str = "default_user") -> dict:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT relationship_label, relationship_status, intimacy_score, trust_score,
                       tension_score, affection_score, attitude_score, relationship_score,
                       stage_confidence, positive_streak, negative_streak, score_scale,
                       last_conflict_at, last_repair_at, last_meaningful_contact_at,
                       last_stage_change_at, open_emotional_threads_json,
                       key_moments_json, relationship_narrative, current_posture,
                       interaction_guidance, updated_at
                FROM relationship_state
                WHERE bot_id = ? AND user_id = ?
                """,
                (bot_id, user_id),
            )
            row = await cursor.fetchone()
        if not row:
            return self._default_state(bot_id, user_id)

        state = {
            "bot_id": bot_id,
            "user_id": user_id,
            "relationship_label": _normalize_stage(row[0]) or self.DEFAULT_LABEL,
            "relationship_status": row[1] or self.DEFAULT_STATUS,
            "intimacy_score": _score(row[2], self.DEFAULT_SCORES["intimacy_score"]),
            "trust_score": _score(row[3], self.DEFAULT_SCORES["trust_score"]),
            "tension_score": _score(row[4], self.DEFAULT_SCORES["tension_score"]),
            "affection_score": _score(row[5], self.DEFAULT_SCORES["affection_score"]),
            "attitude_score": _score(row[6], self.DEFAULT_SCORES["attitude_score"]),
            "relationship_score": _score(row[7], 0.0),
            "stage_confidence": _clamp(_score(row[8], 0.55), 0, 1),
            "positive_streak": int(row[9] or 0),
            "negative_streak": int(row[10] or 0),
            "score_scale": int(row[11] or self.SCORE_SCALE),
            "last_conflict_at": row[12],
            "last_repair_at": row[13],
            "last_meaningful_contact_at": row[14],
            "last_stage_change_at": row[15],
            "open_emotional_threads": _load_json_list(row[16]),
            "key_moments": _load_json_list(row[17]),
            "relationship_narrative": row[18],
            "current_posture": row[19],
            "interaction_guidance": row[20],
            "updated_at": row[21],
        }
        if state["score_scale"] != self.SCORE_SCALE:
            state = self._normalize_legacy_state(state)
        if not state["relationship_score"]:
            state["relationship_score"] = self._calculate_relationship_score(state)
        return self._with_derived_fields(state)

    async def apply_event(
        self,
        *,
        bot_id: str,
        user_id: str = "default_user",
        label: Optional[str] = None,
        intimacy_delta: float = 0,
        trust_delta: float = 0,
        tension_delta: float = 0,
        affection_delta: float = 0,
        attitude_delta: float = 0,
        key_moment: Optional[str] = None,
        open_thread: Optional[str] = None,
    ) -> dict:
        state = await self.get_state(bot_id=bot_id, user_id=user_id)
        now = datetime.now().isoformat()
        previous_label = _normalize_stage(state.get("relationship_label")) or self.DEFAULT_LABEL
        label_hint = _normalize_stage(label)

        deltas = {
            "intimacy_delta": _dimension_delta(intimacy_delta),
            "trust_delta": _dimension_delta(trust_delta),
            "tension_delta": _dimension_delta(tension_delta),
            "affection_delta": _dimension_delta(affection_delta),
            "attitude_delta": _attitude_delta(attitude_delta),
        }

        state["intimacy_score"] = _clamp(float(state.get("intimacy_score", 0)) + deltas["intimacy_delta"], 0, 100)
        state["trust_score"] = _clamp(float(state.get("trust_score", 0)) + deltas["trust_delta"], 0, 100)
        state["tension_score"] = _clamp(float(state.get("tension_score", 0)) + deltas["tension_delta"], 0, 100)
        state["affection_score"] = _clamp(float(state.get("affection_score", 0)) + deltas["affection_delta"], 0, 100)
        state["attitude_score"] = _clamp(float(state.get("attitude_score", 0)) + deltas["attitude_delta"], 0, 100)

        if deltas["tension_delta"] <= 0 and (
            deltas["trust_delta"] > 0 or deltas["intimacy_delta"] > 0 or deltas["affection_delta"] > 0
        ):
            repair_bonus = min(6.0, (max(deltas["trust_delta"], 0) + max(deltas["intimacy_delta"], 0)) / 2)
            state["tension_score"] = _clamp(state["tension_score"] - repair_bonus, 0, 100)

        if deltas["tension_delta"] > 0:
            state["last_conflict_at"] = now
        if deltas["tension_delta"] < 0 or deltas["trust_delta"] > 0:
            state["last_repair_at"] = now

        if open_thread:
            threads = list(state.get("open_emotional_threads") or [])
            if open_thread not in threads:
                threads.append(open_thread)
            state["open_emotional_threads"] = threads[-10:]
        if key_moment:
            moments = list(state.get("key_moments") or [])
            if key_moment not in moments:
                moments.append(key_moment)
            state["key_moments"] = moments[-20:]

        event = self._event_profile(
            label_hint=label_hint,
            key_moment=key_moment,
            open_thread=open_thread,
            deltas=deltas,
        )
        self._update_streaks(state, event)
        state["relationship_score"] = self._calculate_relationship_score(state)
        state["relationship_status"] = self._derive_status(state)
        state["relationship_label"] = self._choose_stable_stage(previous_label, label_hint, state, event)
        if state["relationship_label"] == "恋人":
            state["open_emotional_threads"] = [
                item
                for item in list(state.get("open_emotional_threads") or [])
                if not _is_stale_pre_commitment_thread(item)
            ][:10]
        state["stage_confidence"] = self._next_confidence(
            float(state.get("stage_confidence", 0.55)),
            previous_label=previous_label,
            current_label=state["relationship_label"],
            event=event,
        )
        state["updated_at"] = now
        state["score_scale"] = self.SCORE_SCALE
        if state["relationship_label"] != previous_label:
            state["last_stage_change_at"] = now
        if any(
            [
                label_hint,
                key_moment,
                open_thread,
                deltas["intimacy_delta"],
                deltas["trust_delta"],
                deltas["affection_delta"],
                deltas["attitude_delta"],
            ]
        ):
            state["last_meaningful_contact_at"] = now
        state.update(self._build_relationship_narrative(state, event=event))

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO relationship_state (
                    bot_id, user_id, relationship_label, relationship_status,
                    intimacy_score, trust_score, tension_score, affection_score,
                    attitude_score, relationship_score, stage_confidence,
                    positive_streak, negative_streak, score_scale, last_conflict_at,
                    last_repair_at, last_meaningful_contact_at, last_stage_change_at,
                    open_emotional_threads_json, key_moments_json, relationship_narrative,
                    current_posture, interaction_guidance, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bot_id,
                    user_id,
                    state["relationship_label"],
                    state["relationship_status"],
                    state["intimacy_score"],
                    state["trust_score"],
                    state["tension_score"],
                    state["affection_score"],
                    state["attitude_score"],
                    state["relationship_score"],
                    state["stage_confidence"],
                    state["positive_streak"],
                    state["negative_streak"],
                    self.SCORE_SCALE,
                    state.get("last_conflict_at"),
                    state.get("last_repair_at"),
                    state.get("last_meaningful_contact_at"),
                    state.get("last_stage_change_at"),
                    json.dumps(state.get("open_emotional_threads", []), ensure_ascii=False),
                    json.dumps(state.get("key_moments", []), ensure_ascii=False),
                    state.get("relationship_narrative", ""),
                    state.get("current_posture", ""),
                    state.get("interaction_guidance", ""),
                    now,
                ),
            )
            await db.commit()
        state = self._with_derived_fields(state)
        self._sync_runtime_profile(state)
        return state

    async def clear(self, *, bot_id: str | None = None, user_id: str | None = None) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            if bot_id and user_id:
                cursor = await db.execute(
                    "DELETE FROM relationship_state WHERE bot_id = ? AND user_id = ?",
                    (bot_id, user_id),
                )
            elif bot_id:
                cursor = await db.execute("DELETE FROM relationship_state WHERE bot_id = ?", (bot_id,))
            else:
                cursor = await db.execute("DELETE FROM relationship_state")
            await db.commit()
            return max(cursor.rowcount or 0, 0)

    def _default_state(self, bot_id: str, user_id: str) -> dict:
        state = {
            "bot_id": bot_id,
            "user_id": user_id,
            "relationship_label": self.DEFAULT_LABEL,
            "relationship_status": self.DEFAULT_STATUS,
            "intimacy_score": self.DEFAULT_SCORES["intimacy_score"],
            "trust_score": self.DEFAULT_SCORES["trust_score"],
            "tension_score": self.DEFAULT_SCORES["tension_score"],
            "affection_score": self.DEFAULT_SCORES["affection_score"],
            "attitude_score": self.DEFAULT_SCORES["attitude_score"],
            "relationship_score": 0.0,
            "stage_confidence": 0.55,
            "positive_streak": 0,
            "negative_streak": 0,
            "score_scale": self.SCORE_SCALE,
            "last_conflict_at": None,
            "last_repair_at": None,
            "last_meaningful_contact_at": None,
            "last_stage_change_at": None,
            "open_emotional_threads": [],
            "key_moments": [],
            "updated_at": datetime.now().isoformat(),
        }
        state["relationship_score"] = self._calculate_relationship_score(state)
        state.update(self._build_relationship_narrative(state))
        return self._with_derived_fields(state)

    def _normalize_legacy_state(self, state: dict) -> dict:
        state = dict(state)
        for key in ("intimacy_score", "trust_score", "affection_score"):
            state[key] = _legacy_dimension_to_100(state.get(key))
        state["attitude_score"] = _legacy_score_to_100(state.get("attitude_score"))
        state["tension_score"] = _legacy_tension_to_100(state.get("tension_score"))
        state["relationship_score"] = self._calculate_relationship_score(state)
        state["relationship_status"] = self._derive_status(state)
        state["score_scale"] = self.SCORE_SCALE
        return state

    def _with_derived_fields(self, state: dict) -> dict:
        state = dict(state)
        state["relationship_label"] = _normalize_stage(state.get("relationship_label")) or self.DEFAULT_LABEL
        state["relationship_level"] = state["relationship_label"]
        state["relationship_stage"] = state["relationship_label"]
        state["relationship_score"] = round(float(state.get("relationship_score", 0)), 1)
        state["relationship_score_100"] = state["relationship_score"]
        state["relationship_level_index"] = self._relationship_level_index(state)
        state["score_scale"] = self.SCORE_SCALE
        narrative = self._build_relationship_narrative(state)
        for key, value in narrative.items():
            if not str(state.get(key) or "").strip():
                state[key] = value
        return state

    def _calculate_relationship_score(self, state: dict) -> float:
        score = (
            _score(state.get("intimacy_score"), 0) * 0.30
            + _score(state.get("trust_score"), 0) * 0.25
            + _score(state.get("affection_score"), 0) * 0.25
            + _score(state.get("attitude_score"), 0) * 0.20
            - _score(state.get("tension_score"), 0) * 0.25
        )
        return round(_clamp(score, 0, 100), 1)

    def _derive_status(self, state: dict) -> str:
        tension = _score(state.get("tension_score"), 0)
        score = _score(state.get("relationship_score"), self._calculate_relationship_score(state))
        if tension >= 65:
            return "紧张"
        if score <= 20:
            return "疏远"
        return self.DEFAULT_STATUS

    def _build_relationship_narrative(self, state: dict, event: dict | None = None) -> dict[str, str]:
        label = _normalize_stage(state.get("relationship_label")) or self.DEFAULT_LABEL
        status = str(state.get("relationship_status") or self.DEFAULT_STATUS)
        tension = _score(state.get("tension_score"), 0)
        trust = _score(state.get("trust_score"), 0)
        intimacy = _score(state.get("intimacy_score"), 0)
        affection = _score(state.get("affection_score"), 0)
        score = _score(state.get("relationship_score"), self._calculate_relationship_score(state))
        key_moments = _load_json_list(json.dumps(state.get("key_moments") or [], ensure_ascii=False))
        open_threads = _load_json_list(json.dumps(state.get("open_emotional_threads") or [], ensure_ascii=False))
        if label == "恋人":
            open_threads = [item for item in open_threads if not _is_stale_pre_commitment_thread(item)]

        if tension >= 65:
            posture = "关系里有明显紧张，先放慢、承认感受，不要用玩笑压过去。"
        elif tension >= 40:
            posture = "关系里有一点绷，回复要柔和，少做过度亲密推进。"
        elif label in {"暧昧中", "恋人"} or affection >= 62:
            posture = "可以保留熟悉和亲近感，但亲密表达要自然，不要为了升温而用力。"
        elif label == "好朋友" or trust >= 48:
            posture = "关系有稳定信任，可以像熟人一样承接，但保持分寸。"
        else:
            posture = "关系仍在建立，保持轻松、真诚和克制。"

        if open_threads:
            guidance = f"优先照顾未完成话题：{open_threads[-1]}。"
        elif tension >= 45:
            guidance = "先修复情绪，再解释或推进任务。"
        elif event and event.get("repair_signal"):
            guidance = "修复刚发生过，回应里要让用户感到被认真接住。"
        elif label == "恋人":
            guidance = "承接已经确认的恋人关系；可用少量共同记忆和亲近语气，但不要否认关系事实。"
        elif label == "暧昧中":
            guidance = "可用少量共同记忆和亲近语气，但不要把关系状态说成报告。"
        else:
            guidance = "让关系背景影响语气即可，不主动报数值或阶段。"
        if label == "恋人" and "不要否认关系事实" not in guidance:
            guidance = f"{guidance} 同时承接已经确认的恋人关系，不要否认关系事实。"

        closeness = "还在建立"
        if score >= 75:
            closeness = "很亲近"
        elif score >= 55:
            closeness = "逐渐亲近"
        elif score >= 35:
            closeness = "有基本信任"
        if tension >= 45:
            closeness += "，但近期有紧张需要照顾"

        moment_text = f"最近重要时刻：{key_moments[-1]}" if key_moments else "还没有特别明确的共同关键时刻"
        if label == "恋人":
            narrative = f"你们已经确认恋人/男女朋友关系，关系{closeness}；{moment_text}。"
        else:
            narrative = f"你们目前像{label}，关系{closeness}；{moment_text}。"
        return {
            "relationship_narrative": _compact(narrative, 180),
            "current_posture": _compact(posture, 140),
            "interaction_guidance": _compact(guidance, 160),
        }

    def _base_stage_from_scores(self, state: dict) -> str:
        score = _score(state.get("relationship_score"), self._calculate_relationship_score(state))
        intimacy = _score(state.get("intimacy_score"), 0)
        affection = _score(state.get("affection_score"), 0)
        trust = _score(state.get("trust_score"), 0)
        if score >= 85 and intimacy >= 72 and affection >= 75 and trust >= 65:
            return "恋人"
        if score >= 68 and intimacy >= 55 and affection >= 60:
            return "暧昧中"
        if score >= 50 and trust >= 42:
            return "好朋友"
        if score >= 28:
            return "朋友"
        if score >= 18:
            return "刚认识"
        return "疏远"

    def _choose_stable_stage(self, current_label: str, label_hint: str, state: dict, event: dict) -> str:
        current = _normalize_stage(current_label) or self.DEFAULT_LABEL
        score_stage = self._base_stage_from_scores(state)

        if event["rupture_signal"] and (label_hint == "疏远" or _score(state.get("relationship_score"), 0) < 28):
            return "疏远"

        candidate = score_stage
        if label_hint:
            if label_hint == "紧张":
                candidate = current
            elif _rank(label_hint) > _rank(current):
                if self._has_promotion_evidence(label_hint, state, event):
                    candidate = label_hint
                else:
                    candidate = current
            elif _rank(label_hint) < _rank(current):
                if self._has_demotion_evidence(state, event):
                    candidate = label_hint
                else:
                    candidate = current
            else:
                candidate = current

        return self._guard_transition(current, candidate, state, event)

    def _guard_transition(self, current: str, candidate: str, state: dict, event: dict) -> str:
        current_rank = _rank(current)
        candidate_rank = _rank(candidate)
        if candidate_rank == current_rank:
            return current

        if candidate_rank > current_rank:
            if not self._has_promotion_evidence(candidate, state, event):
                return current
            if event["explicit_commitment"] or (candidate == "暧昧中" and event["romantic_signal"]):
                return candidate
            # Let affection grow visibly, but do not skip several relationship
            # stages because one extraction pass got over-excited.
            return self.RANK_STAGE[min(candidate_rank, current_rank + 1)]

        if self._has_demotion_evidence(state, event):
            return candidate
        return current

    def _has_promotion_evidence(self, target: str, state: dict, event: dict) -> bool:
        if event["explicit_commitment"]:
            return True
        if not event["positive_signal"]:
            return False
        score = _score(state.get("relationship_score"), 0)
        if target == "好朋友":
            return event["meaningful"] or score >= 48 or int(state.get("positive_streak", 0)) >= 2
        if target == "暧昧中":
            return (
                event["romantic_signal"]
                or score >= 66
                or (_score(state.get("affection_score"), 0) >= 58 and _score(state.get("intimacy_score"), 0) >= 52)
            )
        if target == "恋人":
            return event["explicit_commitment"] or (
                score >= 86 and _score(state.get("trust_score"), 0) >= 68 and event["romantic_signal"]
            )
        return event["positive_signal"]

    def _has_demotion_evidence(self, state: dict, event: dict) -> bool:
        return (
            event["rupture_signal"]
            or int(state.get("negative_streak", 0)) >= 2
            or (_score(state.get("tension_score"), 0) >= 72 and event["negative_signal"])
            or (_score(state.get("relationship_score"), 0) < 18 and event["negative_signal"])
        )

    def _event_profile(
        self,
        *,
        label_hint: str,
        key_moment: Optional[str],
        open_thread: Optional[str],
        deltas: dict[str, float],
    ) -> dict:
        text = " ".join(str(item or "") for item in [label_hint, key_moment, open_thread])
        positive_amount = (
            max(deltas["intimacy_delta"], 0)
            + max(deltas["trust_delta"], 0)
            + max(deltas["affection_delta"], 0)
            + max(deltas["attitude_delta"], 0)
            + max(-deltas["tension_delta"], 0)
        )
        negative_amount = (
            max(-deltas["intimacy_delta"], 0)
            + max(-deltas["trust_delta"], 0)
            + max(-deltas["affection_delta"], 0)
            + max(-deltas["attitude_delta"], 0)
            + max(deltas["tension_delta"], 0)
        )
        explicit_commitment = any(word in text for word in ["在一起", "确认关系", "恋人", "情侣", "交往", "成为伴侣"])
        romantic_signal = explicit_commitment or any(word in text for word in ["暧昧", "表白", "喜欢", "心动", "吃醋", "牵手"])
        rupture_signal = any(word in text for word in ["分手", "断联", "拉黑", "绝交", "不想见", "结束关系", "严重伤害"])
        meaningful = bool(key_moment) or positive_amount >= 8 or romantic_signal or explicit_commitment
        positive_signal = positive_amount >= 4 or romantic_signal or explicit_commitment
        negative_signal = negative_amount >= 6 or rupture_signal or label_hint in {"紧张", "疏远"}
        repair_signal = deltas["tension_delta"] < 0 or deltas["trust_delta"] > 0 or any(
            word in text for word in ["道歉", "和好", "修复", "解释清楚", "原谅"]
        )
        return {
            "positive_amount": positive_amount,
            "negative_amount": negative_amount,
            "positive_signal": positive_signal,
            "negative_signal": negative_signal,
            "repair_signal": repair_signal,
            "meaningful": meaningful,
            "romantic_signal": romantic_signal,
            "explicit_commitment": explicit_commitment,
            "rupture_signal": rupture_signal,
        }

    def _update_streaks(self, state: dict, event: dict):
        positive = int(state.get("positive_streak", 0) or 0)
        negative = int(state.get("negative_streak", 0) or 0)
        if event["negative_signal"] and event["negative_amount"] > event["positive_amount"]:
            state["negative_streak"] = min(10, negative + 1)
            state["positive_streak"] = max(0, positive - 1)
        elif event["positive_signal"] and event["positive_amount"] >= event["negative_amount"]:
            state["positive_streak"] = min(10, positive + 1)
            state["negative_streak"] = max(0, negative - 1)
        elif event["repair_signal"]:
            state["negative_streak"] = max(0, negative - 1)
            state["positive_streak"] = positive
        else:
            state["positive_streak"] = positive
            state["negative_streak"] = negative

    def _next_confidence(self, current: float, *, previous_label: str, current_label: str, event: dict) -> float:
        confidence = current
        if previous_label == current_label:
            if event["meaningful"]:
                confidence += 0.03
        else:
            confidence = 0.64 if event["explicit_commitment"] or event["rupture_signal"] else 0.58
        if event["negative_signal"] and not event["rupture_signal"]:
            confidence -= 0.02
        return round(_clamp(confidence, 0.35, 0.95), 2)

    def _relationship_level_index(self, state: dict) -> int:
        label = _normalize_stage(state.get("relationship_label")) or self.DEFAULT_LABEL
        if label == "恋人":
            return 10
        if label == "暧昧中":
            return max(8, min(9, round(_score(state.get("relationship_score"), 70) / 10)))
        if label == "好朋友":
            return max(6, min(7, round(_score(state.get("relationship_score"), 55) / 10)))
        if label == "朋友":
            return max(4, min(5, round(_score(state.get("relationship_score"), 35) / 10)))
        if label == "刚认识":
            return max(2, min(3, round(_score(state.get("relationship_score"), 20) / 10)))
        return 1

    def _runtime_profile_path(self) -> Optional[Path]:
        if not self._persona_backstory_path:
            return None
        return Path(self._persona_backstory_path).parent / "runtime_profile.json"

    def _sync_runtime_profile(self, state: dict):
        path = self._runtime_profile_path()
        if not path:
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            data = {}
        data["relationship_to_user"] = state.get("relationship_label", self.DEFAULT_LABEL)
        data["attitude_score"] = state.get("attitude_score", 50)
        data["relationship_state"] = {
            "stage": state.get("relationship_label", self.DEFAULT_LABEL),
            "status": state.get("relationship_status", self.DEFAULT_STATUS),
            "narrative": state.get("relationship_narrative", ""),
            "current_posture": state.get("current_posture", ""),
            "interaction_guidance": state.get("interaction_guidance", ""),
            "relationship_score": state.get("relationship_score", 0),
            "intimacy_score": state.get("intimacy_score", 0),
            "trust_score": state.get("trust_score", 0),
            "affection_score": state.get("affection_score", 0),
            "tension_score": state.get("tension_score", 0),
            "score_scale": self.SCORE_SCALE,
        }
        if state.get("key_moments"):
            data["key_moments"] = state["key_moments"]
        data["updated_at"] = datetime.now().isoformat()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

    async def close(self):
        return None


def _load_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if str(item).strip()]


def _is_stale_pre_commitment_thread(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    stale_cues = (
        "尚未明确回应",
        "尚未明确答复",
        "尚未获得明确回应",
        "等待答案",
        "等待助手",
        "等助手答复",
        "确认正式关系",
        "关系下一步正式确认",
        "还没正式答应",
        "还没有正式答应",
        "未正式答应",
        "可能想就此确认正式关系",
        "你们目前像恋人",
    )
    return any(cue in text for cue in stale_cues)


def _compact(text: object, limit: int) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 3)].rstrip() + "..."


def _normalize_stage(label: object) -> str:
    text = str(label or "").strip()
    if not text:
        return ""
    aliases = {
        "陌生": "刚认识",
        "陌生网友": "刚认识",
        "初识": "刚认识",
        "普通朋友": "朋友",
        "好友": "好朋友",
        "亲密朋友": "好朋友",
        "暧昧": "暧昧中",
        "暧昧关系": "暧昧中",
        "情侣": "恋人",
        "伴侣": "恋人",
        "男朋友": "恋人",
        "女朋友": "恋人",
        "恋爱中": "恋人",
        "疏离": "疏远",
        "关系紧张": "紧张",
    }
    if text in aliases:
        return aliases[text]
    if text in {"刚认识", "朋友", "好朋友", "暧昧中", "恋人", "疏远", "紧张"}:
        return text
    for keyword, stage in [
        ("恋人", "恋人"),
        ("情侣", "恋人"),
        ("伴侣", "恋人"),
        ("暧昧", "暧昧中"),
        ("好朋友", "好朋友"),
        ("好友", "好朋友"),
        ("朋友", "朋友"),
        ("紧张", "紧张"),
        ("疏远", "疏远"),
        ("疏离", "疏远"),
        ("陌生", "刚认识"),
    ]:
        if keyword in text:
            return stage
    return text if text in RelationshipStore.STAGE_RANK else ""


def _rank(label: str) -> int:
    return RelationshipStore.STAGE_RANK.get(_normalize_stage(label), RelationshipStore.STAGE_RANK[RelationshipStore.DEFAULT_LABEL])


def _dimension_delta(value: object) -> float:
    number = _number(value)
    if abs(number) <= 1:
        number *= 8
    return _clamp(number, -20, 20)


def _attitude_delta(value: object) -> float:
    number = _number(value)
    if abs(number) <= 5:
        number *= 4
    return _clamp(number, -20, 20)


def _legacy_score_to_100(value: object) -> float:
    number = _number(value)
    return round(_clamp((number + 10) * 5, 0, 100), 1)


def _legacy_dimension_to_100(value: object) -> float:
    number = _number(value)
    return round(_clamp(number * 10, 0, 100), 1)


def _legacy_tension_to_100(value: object) -> float:
    return round(_clamp(_number(value) * 10, 0, 100), 1)


def _number(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _score(value: object, default: float) -> float:
    try:
        return _clamp(float(value), 0, 100)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
