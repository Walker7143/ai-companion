"""Build memory prompt suffixes from retrieved memory."""

from __future__ import annotations

from dataclasses import dataclass

from ..context.tokenizer import TokenEstimator
from .conscious import ConsciousContext
from .retriever import RetrievedMemory


@dataclass
class PromptBlock:
    name: str
    title: str
    body: str
    usage: str
    budget: int
    priority: int
    text: str = ""
    raw_chars: int = 0
    final_chars: int = 0
    truncated: bool = False

    def render(self) -> str:
        if not self.body:
            return ""
        body = _trim_text(self.body, self.budget)
        self.raw_chars = len(self.body)
        self.final_chars = len(body)
        self.truncated = self.raw_chars > self.final_chars
        self.text = f"{self.title}\n{body}\n{self.usage}"
        return self.text


class MemoryPromptBuilder:
    """Convert retrieved memory into a compact system prompt suffix."""

    def __init__(self, max_chars: int = 4400):
        self.max_chars = max_chars
        self.understanding_char_limits = {
            "casual_chat": min(2600, max(1400, int(max_chars * 0.24))),
            "task_request": min(1800, max(1000, int(max_chars * 0.16))),
            "planning": min(3600, max(1800, int(max_chars * 0.30))),
            "emotional_support": min(4200, max(2200, int(max_chars * 0.36))),
            "relationship_repair": min(4600, max(2400, int(max_chars * 0.40))),
            "recall_past": min(4200, max(2200, int(max_chars * 0.36))),
            "proactive_generation": min(3600, max(1800, int(max_chars * 0.30))),
        }

    def build(self, retrieved: RetrievedMemory, conscious: ConsciousContext | None = None) -> str:
        suffix, _diagnostics = self.build_with_diagnostics(retrieved, conscious=conscious)
        return suffix

    def build_with_diagnostics(
        self,
        retrieved: RetrievedMemory,
        conscious: ConsciousContext | None = None,
    ) -> tuple[str, dict]:
        blocks = self._build_blocks(retrieved, conscious=conscious)
        parts: list[str] = []
        block_diagnostics: dict[str, dict] = {}
        for block in sorted(blocks, key=lambda item: item.priority):
            text = block.render()
            if not text:
                continue
            parts.append(text)
            block_diagnostics[block.name] = {
                "budget_chars": block.budget,
                "raw_body_chars": block.raw_chars,
                "final_body_chars": block.final_chars,
                "raw_body_tokens_est": TokenEstimator.estimate(block.body),
                "final_body_tokens_est": TokenEstimator.estimate(block.text),
                "rendered_chars": len(text),
                "rendered_tokens_est": TokenEstimator.estimate(text),
                "truncated": block.truncated,
            }

        suffix = "\n".join(parts)
        suffix_raw_chars = len(suffix)
        suffix_truncated = False
        if len(suffix) > self.max_chars:
            suffix = suffix[: self.max_chars - 3] + "..."
            suffix_truncated = True
        diagnostics = {
            "max_chars": self.max_chars,
            "raw_chars": suffix_raw_chars,
            "final_chars": len(suffix),
            "raw_tokens_est": TokenEstimator.estimate("\n".join(parts)),
            "final_tokens_est": TokenEstimator.estimate(suffix),
            "truncated": suffix_truncated,
            "blocks": block_diagnostics,
        }
        return suffix, diagnostics

    def _build_blocks(self, retrieved: RetrievedMemory, conscious: ConsciousContext | None = None) -> list[PromptBlock]:
        blocks: list[PromptBlock] = []
        budgets = self._block_budgets(retrieved.intent)
        anchored_fact_lines = self._format_anchored_fact_items(retrieved)
        anchored_fact_keys = {
            item.get("key")
            for item in getattr(self, "_last_anchored_fact_items", [])
            if isinstance(item, dict) and item.get("key")
        }
        if conscious is not None:
            conscious_text = conscious.render(max_chars=self._conscious_char_limit(retrieved.intent))
            if conscious_text:
                blocks.append(
                    PromptBlock(
                        name="conscious",
                        title="【本轮意识工作区】",
                        body=conscious_text,
                        usage=(
                            "使用方式：这是此刻自然浮到脑子里的少量线索；优先让它影响语气、分寸和承接方式，"
                            "不要把它当资料逐条复述。"
                        ),
                        budget=budgets["conscious"],
                        priority=10,
                    )
                )

        if anchored_fact_lines:
            blocks.append(
                PromptBlock(
                    name="anchored_facts",
                    title="【本轮必须承接的记忆】",
                    body="\n".join(anchored_fact_lines),
                    usage=(
                        "使用方式：这些事实和用户当前这句话直接相关。回复必须默认你已经知道这些背景，"
                        "不要反问已知事实；若涉及敏感身体/健康信息，只承接和关心，不展开隐私细节。"
                    ),
                    budget=budgets["anchored_facts"],
                    priority=15,
                )
            )

        understanding_text = self._format_understanding(retrieved)
        if understanding_text:
            blocks.append(
                PromptBlock(
                    name="understanding",
                    title="【你对用户的理解】",
                    body=understanding_text,
                    usage=(
                        "使用方式：把这些当作相处背景，而不是答案清单。"
                        "回复时优先照顾用户当下这句话；只有在自然、有帮助的时候，才顺手提到相关细节。"
                        "不要生硬地说“我记得你的资料里写着”。"
                    ),
                    budget=budgets["understanding"],
                    priority=20,
                )
            )

        relationship_text = self._format_relationship(retrieved)
        if relationship_text:
            blocks.append(
                PromptBlock(
                    name="relationship",
                    title="【关系状态】",
                    body=relationship_text,
                    usage="使用方式：这只影响语气和分寸，不要直接向用户报数值。",
                    budget=budgets["relationship"],
                    priority=30,
                )
            )

        daily_text = self._format_daily_context(retrieved)
        if daily_text:
            blocks.append(
                PromptBlock(
                    name="daily",
                    title="【最近日常连续性】",
                    body=daily_text,
                    usage=(
                        "使用方式：这是用户最近十天内跨通道与你相处的短期背景。"
                        "当前会话优先；只在自然、必要时参考，不要逐字复述，也不要表现得像在翻日志。"
                    ),
                    budget=budgets["daily"],
                    priority=40,
                )
            )

        fact_lines = self._format_semantic_items(retrieved, skip_keys=anchored_fact_keys)
        if fact_lines:
            blocks.append(
                PromptBlock(
                    name="semantic",
                    title="【语义记忆补充】",
                    body="\n".join(fact_lines),
                    usage="使用方式：这些是和当前意图相关的零散事实，只在自然、有帮助时使用。",
                    budget=budgets["semantic"],
                    priority=50,
                )
            )

        if retrieved.episodic_recall:
            moment_lines = [
                self._format_episode_line(m)
                for m in retrieved.episodic_recall
                if m.get("summary") and not self._skip_episode_for_intent(m, retrieved.intent)
            ]
            if moment_lines:
                blocks.append(
                    PromptBlock(
                        name="episodic",
                        title="【可能相关的共同经历】",
                        body="\n".join(moment_lines),
                        usage="使用方式：这些经历只在能让回应更贴近用户时引用；不要为了展示记忆而引用。",
                        budget=budgets["episodic"],
                        priority=60,
                    )
                )
        return blocks

    def _block_budgets(self, intent: str) -> dict[str, int]:
        intent = intent or "casual_chat"
        if intent == "task_request":
            weights = {
                "conscious": 0.14,
                "understanding": 0.24,
                "relationship": 0.10,
                "daily": 0.08,
                "anchored_facts": 0.08,
                "semantic": 0.12,
                "episodic": 0.06,
            }
        elif intent in {"emotional_support", "relationship_repair", "recall_past"}:
            weights = {
                "conscious": 0.18,
                "understanding": 0.34,
                "relationship": 0.16,
                "daily": 0.12,
                "anchored_facts": 0.08,
                "semantic": 0.10,
                "episodic": 0.14,
            }
        else:
            weights = {
                "conscious": 0.14,
                "understanding": 0.28,
                "relationship": 0.14,
                "daily": 0.10,
                "anchored_facts": 0.08,
                "semantic": 0.08,
                "episodic": 0.08,
            }
        return {
            key: max(220, int(self.max_chars * value))
            for key, value in weights.items()
        }

    def _conscious_char_limit(self, intent: str) -> int:
        if intent in {"recall_past", "relationship_repair", "emotional_support"}:
            return min(1800, max(900, int(self.max_chars * 0.15)))
        if intent == "task_request":
            return min(900, max(500, int(self.max_chars * 0.08)))
        return min(1200, max(650, int(self.max_chars * 0.10)))

    def _format_understanding(self, retrieved: RetrievedMemory) -> str:
        data = retrieved.user_understanding or {}
        lines: list[str] = []
        intent = retrieved.intent or "casual_chat"
        deep_intent = intent in {
            "emotional_support",
            "relationship_repair",
            "recall_past",
            "planning",
            "proactive_generation",
        }
        task_intent = intent == "task_request"
        max_chars = self.understanding_char_limits.get(
            intent,
            self.understanding_char_limits["casual_chat"],
        )
        custom_limit = 4 if deep_intent else 2

        layered_text = self._format_layered_understanding(data, intent=intent, max_chars=max_chars)
        if layered_text:
            return layered_text

        # v2 shape: manual/auto. v1 shape is also supported below.
        manual = data.get("manual") if isinstance(data.get("manual"), dict) else {}
        auto = data.get("auto") if isinstance(data.get("auto"), dict) else {}
        if not manual and not auto:
            manual = data
            auto = {"facts": data.get("auto_facts", {})} if isinstance(data, dict) else {}

        summary = str(manual.get("summary") or "").strip()
        if summary:
            lines.append(f"用户手动设定的整体理解：{_compact_prompt_text(summary, 900 if deep_intent else 600)}")

        manual_identity = _clean_dict(manual.get("identity"))
        if manual_identity:
            lines.append("用户手动设定的身份信息：")
            lines.extend([f"  - {k}: {v}" for k, v in manual_identity.items()])

        manual_facts = _clean_dict(manual.get("facts"))
        if manual_facts:
            lines.append("用户手动设定的事实：")
            fact_limit = 8 if deep_intent else 4
            lines.extend([f"  - {k}: {v}" for k, v in list(manual_facts.items())[:fact_limit]])

        manual_interaction = _clean_interaction_style(manual.get("interaction_style"))
        if any(manual_interaction.values()):
            lines.append("用户手动设定的互动风格：")
            lines.extend(_format_interaction_style(manual_interaction))

        core_manual_sections = [
            ("preferences", "用户手动设定的偏好"),
            ("dislikes", "用户手动设定的不喜欢/避开的事"),
            ("communication_style", "用户手动设定的沟通方式"),
            ("boundaries", "用户手动设定的边界"),
            ("relationship_expectations", "用户手动设定的关系期待"),
            ("important_people", "用户手动设定的重要关系"),
            ("current_context", "用户手动设定的当前状态"),
            ("open_threads", "用户手动设定的后续话题"),
        ]
        for key, title in core_manual_sections:
            items = _clean_list(manual.get(key))
            if items:
                lines.append(f"{title}：")
                lines.extend([f"  - {item}" for item in items[: _section_item_limit(key, intent)]])

        notes = _clean_list(manual.get("notes"))
        if notes and not task_intent:
            lines.append("用户手动补充说明：")
            lines.extend([f"  - {item}" for item in _select_edge_items(notes, 3 if deep_intent else 2)])

        manual_deep_sections = [
            ("personality_observations", "用户手动设定的性格观察"),
            ("emotional_patterns", "用户手动设定的情绪模式"),
            ("stressors", "用户手动设定的压力源"),
            ("comfort_strategies", "用户手动设定的有效陪伴方式"),
            ("attachment_and_distance", "用户手动设定的亲近与距离模式"),
            ("values_and_principles", "用户手动设定的价值观和原则"),
            ("life_context", "用户手动设定的生活背景"),
            ("goals_and_projects", "用户手动设定的目标和项目"),
            ("routines", "用户手动设定的作息和习惯"),
            ("recent_changes", "用户手动设定的近期变化"),
        ]
        for key, title in _section_pairs_for_intent(manual_deep_sections, intent):
            items = _clean_list(manual.get(key))
            if items:
                lines.append(f"{title}：")
                lines.extend([f"  - {item}" for item in items[: _section_item_limit(key, intent)]])

        manual_extra = _format_extra_fields(
            manual,
            known_keys=_SECTION_KEYS,
            title="用户手动补充的自定义字段",
            limit=custom_limit,
        )
        if manual_extra:
            lines.extend(manual_extra)

        top_extra = _format_extra_fields(
            data,
            known_keys=_TOP_LEVEL_KEYS,
            title="用户理解文件中的自定义字段",
            limit=custom_limit,
        )
        if top_extra:
            lines.extend(top_extra)

        auto_summary = str(auto.get("profile_summary") or auto.get("summary") or "").strip()
        if auto_summary:
            lines.append(f"Bot 在相处中逐渐形成的理解：{_compact_prompt_text(auto_summary, 700 if deep_intent else 420)}")

        auto_identity = _clean_dict(auto.get("identity"))
        if auto_identity:
            lines.append("自动补充的身份信息：")
            lines.extend([f"  - {k}: {v}" for k, v in auto_identity.items()])

        auto_interaction = _clean_interaction_style(auto.get("interaction_style"))
        if any(auto_interaction.values()):
            lines.append("自动学习到的互动风格：")
            lines.extend(_format_interaction_style(auto_interaction))

        auto_facts = _clean_dict(auto.get("facts"))
        if auto_facts and not task_intent:
            lines.append("从日常对话自动补充的事实：")
            fact_limit = 6 if deep_intent else 3
            lines.extend([f"  - {k}: {v}" for k, v in list(auto_facts.items())[:fact_limit]])

        auto_sections = [
            ("preferences", "自动补充的偏好"),
            ("dislikes", "自动补充的不喜欢/避开的事"),
            ("communication_style", "自动补充的沟通方式"),
            ("boundaries", "自动补充的边界"),
            ("important_people", "自动补充的重要关系"),
            ("current_context", "自动补充的当前状态"),
            ("open_threads", "自动补充的后续话题"),
            ("emotional_patterns", "观察到的情绪模式"),
            ("stressors", "近期压力源"),
            ("comfort_strategies", "有效的安慰/陪伴方式"),
            ("attachment_and_distance", "亲近与距离模式"),
            ("values_and_principles", "价值观和原则"),
            ("life_context", "自动补充的生活背景"),
            ("goals_and_projects", "目标和项目"),
            ("routines", "作息和习惯"),
            ("recent_changes", "近期变化"),
        ]
        for key, title in _section_pairs_for_intent(auto_sections, intent):
            items = _clean_list(auto.get(key))
            if items:
                lines.append(f"{title}：")
                lines.extend([f"  - {item}" for item in items[: _section_item_limit(key, intent)]])

        auto_extra = _format_extra_fields(
            auto,
            known_keys=_SECTION_KEYS | {"last_refresh_at"},
            title="自动理解中的自定义字段",
            limit=custom_limit,
        )
        if auto_extra and deep_intent:
            lines.extend(auto_extra)

        relationship_memory = data.get("relationship_memory") if isinstance(data.get("relationship_memory"), dict) else {}
        relationship_sections = [
            ("how_user_treats_bot", "用户如何对待 Bot"),
            ("what_user_seems_to_need_from_bot", "用户似乎需要 Bot 提供的关系位置"),
            ("things_that_brought_them_closer", "让关系变近的时刻"),
            ("things_that_created_tension", "制造距离或紧张的点"),
            ("repair_preferences", "关系修复偏好"),
        ]
        for key, title in _section_pairs_for_intent(relationship_sections, intent):
            items = _clean_list(relationship_memory.get(key))
            if items:
                lines.append(f"{title}：")
                lines.extend([f"  - {item}" for item in items[: _section_item_limit(key, intent)]])

        return _trim_lines(lines, max_chars=max_chars)

    def _format_layered_understanding(self, data: dict, *, intent: str, max_chars: int) -> str:
        layered = data.get("layered") if isinstance(data.get("layered"), dict) else {}
        if not layered:
            return ""
        lines: list[str] = []
        core = layered.get("core") if isinstance(layered.get("core"), dict) else {}
        current = layered.get("current") if isinstance(layered.get("current"), dict) else {}
        deep = layered.get("deep") if isinstance(layered.get("deep"), dict) else {}
        sensitive = layered.get("sensitive") if isinstance(layered.get("sensitive"), dict) else {}

        summary = str(core.get("summary") or "").strip()
        if summary:
            lines.append(f"核心理解：{_compact_prompt_text(summary, 420)}")
        sensitive_source_keys = _clean_list(sensitive.get("source_keys"))
        identity = _clean_dict(core.get("identity"))
        if identity:
            lines.append("用户手动设定的身份信息：")
            lines.extend([f"  - {k}: {v}" for k, v in list(identity.items())[:6]])
        facts = _clean_dict(core.get("facts"))
        if facts and intent != "task_request":
            lines.append("用户手动设定的事实：")
            lines.extend([f"  - {k}: {v}" for k, v in list(facts.items())[:4]])
        for key, title in [
            ("preferences", "稳定偏好"),
            ("dislikes", "不喜欢/避开的事"),
            ("communication_style", "沟通方式"),
            ("boundaries", "边界"),
            ("relationship_expectations", "关系期待"),
        ]:
            items = _clean_list(core.get(key))
            if items:
                lines.append(f"{title}：")
                lines.extend([f"  - {item}" for item in items[: _layer_item_limit("core", key, intent)]])

        for key, title in [
            ("current_context", "当前状态"),
            ("open_threads", "未完话题"),
            ("goals_and_projects", "目标和项目"),
            ("recent_changes", "近期变化"),
            ("stressors", "近期压力源"),
            ("routines", "作息和习惯"),
        ]:
            if not _layer_allows("current", key, intent):
                continue
            items = _clean_list(current.get(key))
            if items:
                item_lines = [
                    f"  - {item}"
                    for idx, item in enumerate(items[: _layer_item_limit("current", key, intent, total=len(items))])
                    if not _is_sensitive_layer_item("current", key, idx, sensitive_source_keys)
                ]
                if item_lines:
                    lines.append(f"{title}：")
                    lines.extend(item_lines)

        for key, title in [
            ("personality_observations", "性格观察"),
            ("emotional_patterns", "观察到的情绪模式"),
            ("comfort_strategies", "有效的安慰/陪伴方式"),
            ("attachment_and_distance", "亲近与距离模式"),
            ("values_and_principles", "价值观和原则"),
            ("life_context", "用户手动设定的生活背景"),
        ]:
            if not _layer_allows("deep", key, intent):
                continue
            items = _clean_list(deep.get(key))
            if items:
                item_lines = [
                    f"  - {item}"
                    for idx, item in enumerate(items[: _layer_item_limit("deep", key, intent)])
                    if not _is_sensitive_layer_item("deep", key, idx, sensitive_source_keys)
                ]
                if item_lines:
                    lines.append(f"{title}：")
                    lines.extend(item_lines)

        relationship = deep.get("relationship_memory") if isinstance(deep.get("relationship_memory"), dict) else {}
        for key, title in [
            ("what_user_seems_to_need_from_bot", "关系中的需要"),
            ("things_that_brought_them_closer", "让关系变近的时刻"),
            ("things_that_created_tension", "制造距离或紧张的点"),
            ("repair_preferences", "关系修复偏好"),
            ("how_user_treats_bot", "用户如何对待 Bot"),
        ]:
            if not _layer_allows("relationship", key, intent):
                continue
            items = _clean_list(relationship.get(key))
            if items:
                lines.append(f"{title}：")
                lines.extend([f"  - {item}" for item in items[: _layer_item_limit("relationship", key, intent)]])

        sensitive_topics = _clean_list(sensitive.get("topics"))
        sensitive_guidance = _clean_list(sensitive.get("guidance"))
        if sensitive_topics and intent in {"casual_chat", "planning", "task_request"}:
            lines.append("敏感记忆使用边界：")
            lines.extend([f"  - {item}" for item in sensitive_guidance[:2]])
        elif sensitive_topics and intent in {"emotional_support", "relationship_repair", "recall_past"}:
            lines.append("敏感记忆使用边界：")
            lines.extend([f"  - {item}" for item in sensitive_guidance[:2]])
            lines.append("  - 相关敏感线索：" + "、".join(sensitive_topics[:5]))

        extra = self._format_layered_extra_fields(data, intent=intent)
        if extra:
            lines.extend(extra)

        return _trim_lines(lines, max_chars=max_chars)

    def _format_layered_extra_fields(self, data: dict, *, intent: str) -> list[str]:
        if intent == "task_request":
            return []
        manual = data.get("manual") if isinstance(data.get("manual"), dict) else {}
        lines: list[str] = []
        manual_extra = _format_extra_fields(
            manual,
            known_keys=_SECTION_KEYS,
            title="用户手动补充的自定义字段",
            limit=4 if intent in {"emotional_support", "relationship_repair", "recall_past", "planning"} else 2,
        )
        if manual_extra:
            lines.extend(manual_extra)
        top_extra = _format_extra_fields(
            data,
            known_keys=_TOP_LEVEL_KEYS,
            title="用户理解文件中的自定义字段",
            limit=3 if intent in {"emotional_support", "relationship_repair", "recall_past", "planning"} else 1,
        )
        if top_extra:
            lines.extend(top_extra)
        return lines

    def _format_daily_context(self, retrieved: RetrievedMemory) -> str:
        data = retrieved.daily_context or {}
        summaries = data.get("summaries") if isinstance(data.get("summaries"), list) else []
        messages = data.get("recent_messages") if isinstance(data.get("recent_messages"), list) else []
        self_memory = data.get("self_memory") if isinstance(data.get("self_memory"), list) else []
        if not summaries and not messages and not self_memory:
            return ""

        lines: list[str] = []
        today = data.get("today")
        today_summary = None
        older_summaries = []
        for item in summaries:
            if not isinstance(item, dict):
                continue
            if item.get("local_date") == today:
                today_summary = item
            else:
                older_summaries.append(item)

        if today_summary and today_summary.get("summary"):
            lines.append(f"  - 今天：{str(today_summary.get('summary'))[:240]}")
            for key, title in [
                ("open_threads", "今天未完话题"),
                ("commitments", "今天承诺/待办"),
                ("mood", "今天情绪线索"),
            ]:
                values = _clean_list(today_summary.get(key))
                if values:
                    lines.append(f"    {title}：" + "；".join(values[:3]))

        if older_summaries:
            lines.append("  - 最近几天：")
            for item in older_summaries[:5]:
                date = item.get("local_date") or "未知日期"
                summary = str(item.get("summary") or "").strip()
                if summary:
                    lines.append(f"    - {date}: {summary[:180]}")

        if messages:
            lines.append("  - 其他通道最近几条：")
            for item in messages[-8:]:
                if not isinstance(item, dict):
                    continue
                platform = item.get("platform") or "unknown"
                role = "用户" if item.get("role") == "user" else "助手"
                content = str(item.get("content") or "").strip()
                if content:
                    lines.append(f"    - [{platform}] {role}: {content[:120]}")

        if self_memory:
            lines.append("  - Bot 自己最近主动做过的事：")
            for item in self_memory[:5]:
                if not isinstance(item, dict):
                    continue
                content = str(item.get("content") or "").strip()
                if not content:
                    continue
                kind = item.get("kind") or "assistant_initiated"
                date = item.get("local_date") or "最近"
                lines.append(f"    - {date} [{kind}]: {content[:120]}")

        return "\n".join(lines)

    def _format_relationship(self, retrieved: RetrievedMemory) -> str:
        state = retrieved.relationship_state or {}
        lines: list[str] = []
        narrative = str(state.get("relationship_narrative") or "").strip()
        posture = str(state.get("current_posture") or "").strip()
        guidance = str(state.get("interaction_guidance") or "").strip()
        if narrative:
            lines.append(f"  - 关系叙事：{narrative}")
        if posture:
            lines.append(f"  - 当前姿态：{posture}")
        if guidance:
            lines.append(f"  - 互动建议：{guidance}")
        label = state.get("relationship_label") or state.get("relationship_level")
        if label and not narrative:
            lines.append(f"  - 关系：{label}")
        status = str(state.get("relationship_status") or "").strip()
        if status and status != "稳定":
            lines.append(f"  - 当前状态：{status}")
        score = _float(state.get("relationship_score"))
        if score > 0 and not narrative:
            lines.append(f"  - 综合关系温度：{score:.0f}/100")
        dimension_lines = []
        for key, title in [
            ("intimacy_score", "亲密"),
            ("trust_score", "信任"),
            ("affection_score", "心动/好感"),
            ("tension_score", "紧张"),
        ]:
            value = _float(state.get(key))
            if value > 0:
                dimension_lines.append(f"{title}{value:.0f}")
        if dimension_lines and not narrative:
            lines.append("  - 维度：" + "，".join(dimension_lines))
        confidence = _float(state.get("stage_confidence"))
        if confidence > 0:
            lines.append(f"  - 阶段稳定度：{confidence:.0%}")
        tension = _float(state.get("tension_score"))
        if tension >= 45:
            lines.append("  - 当前关系可能有紧张感，回复需要更克制、先修复情绪。")
        open_threads = state.get("open_emotional_threads") or []
        if isinstance(open_threads, list) and open_threads:
            lines.append("  - 未完成情绪话题：" + "；".join(str(item) for item in open_threads[:3]))
        return "\n".join(lines)

    def _format_anchored_fact_items(self, retrieved: RetrievedMemory) -> list[str]:
        items = _anchored_semantic_items(retrieved)
        self._last_anchored_fact_items = items
        lines: list[str] = []
        for item in items:
            category = item.get("category") or "general"
            key = item.get("key")
            value = item.get("value")
            if not key or not value:
                continue
            if _is_sensitive_fact(item):
                lines.append(f"  - [{category}] {key}: {value}（敏感背景：只顺着当前话题承接，不主动追问细节）")
            else:
                lines.append(f"  - [{category}] {key}: {value}")
        return lines

    def _format_semantic_items(self, retrieved: RetrievedMemory, *, skip_keys: set[str] | None = None) -> list[str]:
        known_keys = set()
        known_values = set()
        skip_keys = skip_keys or set()
        understanding = retrieved.user_understanding
        if isinstance(understanding, dict):
            manual = understanding.get("manual") if isinstance(understanding.get("manual"), dict) else {}
            auto = understanding.get("auto") if isinstance(understanding.get("auto"), dict) else {}
            for section in (manual, auto):
                identity = _clean_dict(section.get("identity"))
                known_keys.update(identity.keys())
                known_values.update(identity.values())
                facts = _clean_dict(section.get("facts"))
                known_keys.update(facts.keys())
                known_values.update(facts.values())
                for list_key in (
                    "preferences", "dislikes", "communication_style", "boundaries", "important_people",
                    "relationship_expectations", "current_context", "open_threads", "notes",
                    "emotional_patterns", "stressors",
                    "comfort_strategies", "attachment_and_distance", "values_and_principles",
                    "life_context", "goals_and_projects", "routines", "recent_changes",
                ):
                    known_values.update(_clean_list(section.get(list_key)))
                for extra_key, extra_value in _extra_items(section, _SECTION_KEYS):
                    known_keys.add(extra_key)
                    known_values.update(_value_tokens(extra_value))
                interaction = _clean_interaction_style(section.get("interaction_style"))
                for key, value in interaction.items():
                    if isinstance(value, list):
                        known_values.update(value)
                    elif value:
                        known_values.add(str(value))
            relationship_memory = understanding.get("relationship_memory") if isinstance(understanding.get("relationship_memory"), dict) else {}
            for list_key in (
                "how_user_treats_bot", "what_user_seems_to_need_from_bot",
                "things_that_brought_them_closer", "things_that_created_tension",
                "repair_preferences",
            ):
                known_values.update(_clean_list(relationship_memory.get(list_key)))
            known_keys.update(_clean_dict(understanding.get("facts")).keys())
            legacy_auto = _clean_dict(understanding.get("auto_facts"))
            known_keys.update(legacy_auto.keys())
            known_values.update(legacy_auto.values())
            layered = understanding.get("layered") if isinstance(understanding.get("layered"), dict) else {}
            core = layered.get("core") if isinstance(layered.get("core"), dict) else {}
            for dict_key in ("identity", "facts"):
                section = core.get(dict_key) if isinstance(core.get(dict_key), dict) else {}
                known_keys.update(str(key).strip() for key in section.keys())
                known_values.update(str(value).strip() for value in section.values())
            for list_key in ("preferences", "dislikes", "communication_style", "boundaries", "relationship_expectations"):
                known_values.update(_clean_list(core.get(list_key)))
            for extra_key, extra_value in _extra_items(understanding, _TOP_LEVEL_KEYS):
                known_keys.add(extra_key)
                known_values.update(_value_tokens(extra_value))
        lines = []
        for item in retrieved.semantic_items:
            key = item.get("key")
            value = item.get("value")
            if not key or not value or key in skip_keys or key in known_keys or value in known_values:
                continue
            category = item.get("category") or "general"
            lines.append(f"  - [{category}] {key}: {value}")
        return lines

    def _format_episode_line(self, item: dict) -> str:
        summary = str(item.get("summary") or "").strip()[:120]
        relationship_effect = str(item.get("relationship_effect") or "").strip()
        sensitivity = str(item.get("sensitivity") or "").strip()
        label = ""
        if sensitivity == "sensitive":
            label = "敏感"
        elif relationship_effect and relationship_effect != "普通":
            label = relationship_effect
        return f"  - [{label}] {summary}" if label else f"  - {summary}"

    def _skip_episode_for_intent(self, item: dict, intent: str) -> bool:
        sensitivity = str(item.get("sensitivity") or "normal").lower()
        if sensitivity != "sensitive":
            return False
        return intent not in {"recall_past", "relationship_repair", "emotional_support"}


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clean_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for key, val in value.items():
        k = str(key).strip()
        v = str(val).strip()
        if k and v:
            result[k] = v
    return result


def _clean_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _clean_interaction_style(value: object) -> dict[str, object]:
    result: dict[str, object] = {
        "preferred_reply_length": "",
        "accepted_humor": [],
        "disliked_phrases": [],
        "natural_openings": [],
        "avoid_patterns": [],
    }
    if isinstance(value, dict):
        result["preferred_reply_length"] = str(value.get("preferred_reply_length") or "").strip()
        for key in ("accepted_humor", "disliked_phrases", "natural_openings", "avoid_patterns"):
            result[key] = _clean_list(value.get(key))
    return result


def _format_interaction_style(style: dict[str, object]) -> list[str]:
    lines: list[str] = []
    if style.get("preferred_reply_length"):
        lines.append(f"  - 回复长度：{style['preferred_reply_length']}")
    for key, title in [
        ("accepted_humor", "可接受的幽默"),
        ("disliked_phrases", "不喜欢的表达"),
        ("natural_openings", "自然开场"),
        ("avoid_patterns", "避免模式"),
    ]:
        values = style.get(key)
        if isinstance(values, list) and values:
            lines.append(f"  - {title}：" + "；".join(str(v) for v in values[:5]))
    return lines


def _anchored_semantic_items(retrieved: RetrievedMemory) -> list[dict]:
    """Facts that are too relevant to remain as soft background this turn."""
    selected: list[dict] = []
    selected.extend(_stable_continuity_items(retrieved.user_understanding))

    for item in retrieved.semantic_items:
        if not isinstance(item, dict) or not _should_anchor_semantic_item(item):
            continue
        selected.append(dict(item))

    result: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in selected:
        key = str(item.get("key") or "").strip()
        value = str(item.get("value") or "").strip()
        if not key or not value:
            continue
        marker = (key, value)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
        if len(result) >= 6:
            break
    return result


def _stable_continuity_items(understanding: object) -> list[dict]:
    if not isinstance(understanding, dict):
        return []
    layered = understanding.get("layered") if isinstance(understanding.get("layered"), dict) else {}
    core = layered.get("core") if isinstance(layered.get("core"), dict) else {}
    current = layered.get("current") if isinstance(layered.get("current"), dict) else {}
    identity = _clean_dict(core.get("identity"))

    items: list[dict] = []
    current_city = identity.get("current_city") or identity.get("城市") or identity.get("所在城市")
    living_status = identity.get("living_status") or identity.get("居住状态")
    if current_city:
        value = f"用户当前在{current_city}"
        if living_status and str(living_status) not in value:
            value = f"{value}；{living_status}"
        items.append({
            "key": "当前所在地",
            "value": value,
            "category": "life_context",
            "retrieval_reasons": {"stable_continuity": True},
        })

    for item in _clean_list(current.get("current_context")):
        if any(cue in item for cue in ("在北京", "人在北京", "一个人在北京", "独居")):
            items.append({
                "key": "当前生活状态",
                "value": item,
                "category": "life_context",
                "retrieval_reasons": {"stable_continuity": True},
            })
            break
    return items


def _should_anchor_semantic_item(item: dict) -> bool:
    reasons = item.get("retrieval_reasons") if isinstance(item.get("retrieval_reasons"), dict) else {}
    overlap = _float(reasons.get("query_cue_overlap"))
    salient_overlap = _float(reasons.get("salient_overlap"))
    category = str(item.get("category") or "")
    confidence = _float(item.get("confidence"))
    text = f"{item.get('key', '')} {item.get('value', '')}"

    if overlap or salient_overlap:
        return category in _ANCHORABLE_FACT_CATEGORIES or _is_sensitive_fact(item)
    if confidence >= 0.92 and any(cue in text for cue in _HIGH_IMPACT_FACT_CUES):
        return category in {"identity", "life_context", "goals", "routines"}
    return False


def _is_sensitive_fact(item: dict) -> bool:
    text = f"{item.get('key', '')} {item.get('value', '')}"
    return any(cue in text for cue in _SENSITIVE_FACT_CUES)


_ANCHORABLE_FACT_CATEGORIES = {
    "identity",
    "life_context",
    "goals",
    "routines",
    "important_people",
    "preferences",
    "dislikes",
    "boundaries",
    "open_threads",
}

_HIGH_IMPACT_FACT_CUES = {
    "北京",
    "大理",
    "城市",
    "位置",
    "出行",
    "29号",
    "腿脚",
    "身体",
    "医生",
    "减肥",
}

_SENSITIVE_FACT_CUES = {
    "身体",
    "健康",
    "腿",
    "脚",
    "腰",
    "神经",
    "失禁",
    "乙肝",
    "医生",
    "病",
}


_SECTION_KEYS = {
    "summary",
    "profile_summary",
    "identity",
    "facts",
    "preferences",
    "dislikes",
    "communication_style",
    "boundaries",
    "relationship_expectations",
    "interaction_style",
    "important_people",
    "current_context",
    "open_threads",
    "notes",
    "personality_observations",
    "emotional_patterns",
    "stressors",
    "comfort_strategies",
    "attachment_and_distance",
    "values_and_principles",
    "life_context",
    "goals_and_projects",
    "routines",
    "recent_changes",
}

_TOP_LEVEL_KEYS = {
    "version",
    "updated_at",
    "manual",
    "auto",
    "relationship_memory",
    "layered",
    "meta",
    "summary",
    "facts",
    "preferences",
    "dislikes",
    "communication_style",
    "boundaries",
    "important_people",
    "current_context",
    "open_threads",
    "auto_facts",
}


def _extra_items(container: object, known_keys: set[str]):
    if not isinstance(container, dict):
        return []
    return [
        (str(key).strip(), value)
        for key, value in container.items()
        if str(key).strip() and str(key).strip() not in known_keys and _has_prompt_value(value)
    ]


def _format_extra_fields(container: object, *, known_keys: set[str], title: str, limit: int | None = None) -> list[str]:
    items = _extra_items(container, known_keys)
    if not items:
        return []
    lines = [f"{title}："]
    selected = items if limit is None or limit <= 0 else items[:limit]
    for key, value in selected:
        rendered = _render_value(value)
        if rendered:
            lines.append(f"  - {key}: {rendered}")
    return lines if len(lines) > 1 else []


def _section_pairs_for_intent(pairs: list[tuple[str, str]], intent: str) -> list[tuple[str, str]]:
    intent = intent or "casual_chat"
    if intent == "task_request":
        allowed = {"communication_style", "preferences", "dislikes", "boundaries", "goals_and_projects", "open_threads"}
    elif intent == "emotional_support":
        allowed = {
            "emotional_patterns",
            "stressors",
            "comfort_strategies",
            "attachment_and_distance",
            "values_and_principles",
            "life_context",
            "current_context",
            "recent_changes",
            "things_that_brought_them_closer",
            "communication_style",
            "dislikes",
            "boundaries",
            "repair_preferences",
            "things_that_created_tension",
            "what_user_seems_to_need_from_bot",
        }
    elif intent == "relationship_repair":
        allowed = {
            "boundaries",
            "communication_style",
            "dislikes",
            "relationship_expectations",
            "emotional_patterns",
            "comfort_strategies",
            "attachment_and_distance",
            "what_user_seems_to_need_from_bot",
            "things_that_brought_them_closer",
            "things_that_created_tension",
            "repair_preferences",
            "open_threads",
        }
    elif intent == "recall_past":
        allowed = {
            "important_people",
            "life_context",
            "goals_and_projects",
            "routines",
            "recent_changes",
            "things_that_brought_them_closer",
            "how_user_treats_bot",
            "what_user_seems_to_need_from_bot",
            "personality_observations",
            "values_and_principles",
            "dislikes",
        }
    elif intent == "planning":
        allowed = {
            "goals_and_projects",
            "routines",
            "recent_changes",
            "current_context",
            "open_threads",
            "communication_style",
            "preferences",
            "dislikes",
            "life_context",
        }
    else:
        allowed = {
            "preferences",
            "dislikes",
            "communication_style",
            "boundaries",
            "important_people",
            "current_context",
            "open_threads",
            "recent_changes",
            "life_context",
            "what_user_seems_to_need_from_bot",
            "things_that_brought_them_closer",
        }
    return [(key, title) for key, title in pairs if key in allowed]


def _layer_allows(layer: str, key: str, intent: str) -> bool:
    intent = intent or "casual_chat"
    if layer == "current":
        if intent == "task_request":
            return key in {"open_threads", "goals_and_projects"}
        if intent == "casual_chat":
            return key in {"current_context", "open_threads", "recent_changes"}
        if intent == "planning":
            return key in {"current_context", "open_threads", "goals_and_projects", "recent_changes", "routines"}
        return True
    if layer == "deep":
        if intent in {"emotional_support", "relationship_repair", "recall_past", "proactive_generation"}:
            return True
        if intent == "planning":
            return key in {"life_context", "values_and_principles", "comfort_strategies"}
        return False
    if layer == "relationship":
        if intent in {"emotional_support", "relationship_repair", "recall_past", "proactive_generation"}:
            return True
        return key in {"what_user_seems_to_need_from_bot", "repair_preferences"} and intent == "planning"
    return True


def _layer_item_limit(layer: str, key: str, intent: str, *, total: int | None = None) -> int:
    deep_intent = intent in {"emotional_support", "relationship_repair", "recall_past", "proactive_generation"}
    if layer == "core":
        return 4 if intent in {"casual_chat", "task_request"} else 6
    if layer == "current":
        if key == "current_context" and intent == "casual_chat":
            return min(max(total or 0, 4), 8)
        return 2 if intent == "task_request" else 4
    if layer in {"deep", "relationship"}:
        return 4 if deep_intent else 2
    return 3


def _is_sensitive_layer_item(layer: str, key: str, index: int, source_keys: list[str]) -> bool:
    candidates = {
        f"{layer}.{key}.{index}",
    }
    if layer == "deep":
        candidates.add(f"auto.{key}.{index}")
        candidates.add(f"manual.{key}.{index}")
    if layer == "current":
        candidates.add(f"auto.{key}.{index}")
        candidates.add(f"manual.{key}.{index}")
    return any(candidate in source_keys for candidate in candidates)


def _section_item_limit(key: str, intent: str) -> int:
    deep = intent in {"emotional_support", "relationship_repair", "recall_past", "planning", "proactive_generation"}
    if key in {"stressors", "comfort_strategies", "things_that_created_tension", "repair_preferences"}:
        return 4 if deep else 2
    if key in {"notes", "open_threads", "recent_changes", "current_context"}:
        return 3 if deep else 2
    if key in {"important_people", "things_that_brought_them_closer"}:
        return 4 if intent in {"recall_past", "relationship_repair"} else 2
    return 3 if deep else 2


def _select_edge_items(items: list[str], limit: int) -> list[str]:
    if limit <= 0 or len(items) <= limit:
        return items
    if limit == 1:
        return [items[-1]]
    head_count = max(1, limit // 2)
    tail_count = max(1, limit - head_count)
    selected = items[:head_count] + items[-tail_count:]
    result: list[str] = []
    for item in selected:
        if item not in result:
            result.append(item)
    return result


def _trim_lines(lines: list[str], *, max_chars: int) -> str:
    if max_chars <= 0:
        return "\n".join(lines)
    result: list[str] = []
    total = 0
    for line in lines:
        projected = total + len(line) + (1 if result else 0)
        if projected > max_chars:
            remaining = max_chars - total - (1 if result else 0)
            if remaining > 12:
                result.append(line[: remaining - 3] + "...")
            break
        result.append(line)
        total = projected
    text = "\n".join(result)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _compact_prompt_text(value: object, max_chars: int) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _trim_text(value: object, max_chars: int) -> str:
    text = str(value or "").strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _has_prompt_value(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_prompt_value(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_prompt_value(v) for v in value)
    return value is not None


def _render_value(value: object, max_chars: int = 800) -> str:
    import json

    if isinstance(value, str):
        rendered = value.strip()
    elif isinstance(value, (int, float, bool)):
        rendered = str(value)
    elif isinstance(value, list):
        parts = [_render_value(item, max_chars=240) for item in value if _has_prompt_value(item)]
        rendered = "；".join(part for part in parts if part)
    elif isinstance(value, dict):
        rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        rendered = str(value).strip()

    if len(rendered) > max_chars:
        return rendered[: max_chars - 3] + "..."
    return rendered


def _value_tokens(value: object) -> set[str]:
    if isinstance(value, dict):
        tokens = set()
        for key, val in value.items():
            key = str(key).strip()
            if key:
                tokens.add(key)
            tokens.update(_value_tokens(val))
        return tokens
    if isinstance(value, list):
        tokens = set()
        for item in value:
            tokens.update(_value_tokens(item))
        return tokens
    rendered = _render_value(value)
    return {rendered} if rendered else set()
