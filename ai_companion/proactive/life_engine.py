"""
LifeEngine - Bot 独立人生轨迹引擎

核心功能：
1. 生成日常小事（低概率）
2. 判断并生成人生大事（更新人格文件）
3. 管理事件上下文和 Bot 年龄
4. 季节和节假日系统
5. 年龄里程碑系统
"""

import json
import logging
import random
import re
import tempfile
import shutil
import uuid
import os
from difflib import SequenceMatcher
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..model.minimax_adapter import MiniMaxAdapter
    from ..memory.engine import MemoryEngine
    from .life_config import LifeConfig
    from .life_state import LifeEvent, MajorLifeEvent, LifeState

logger = logging.getLogger(__name__)

# 季节定义（北半球）
SEASONS = {
    "春": {"months": [3, 4, 5], "mood_tags": ["温暖", "希望", "慵懒"]},
    "夏": {"months": [6, 7, 8], "mood_tags": ["炎热", "烦躁", "活力"]},
    "秋": {"months": [9, 10, 11], "mood_tags": ["凉爽", "感慨", "收获"]},
    "冬": {"months": [12, 1, 2], "mood_tags": ["寒冷", "慵懒", "期待"]},
}

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


class _SafeFormatDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


# 日常小事生成 Prompt
LIFE_DAILY_PROMPT = """【Bot角色】
你是{both_name}，{age_years}岁，职业是{occupation}。
性格特点：{personality_tags}

【当前时间背景】
季节：{season}（{month}月）
人生阶段：{life_stage}
日期：{current_date}，{day_of_week}
{holiday_context}
{birthday_context}

【Bot 当前状态】
Bot 当前心情：{bot_mood}
Bot 当前活动：{bot_current_activity}
Bot 出生天数：{bot_age_days} 天
最近发生的事件：{recent_events}
近期禁止复用的场景 key：{forbidden_scenarios}
可用场景参考：{scenario_guidance}

【判断规则】
1. 不要每天都生成事件——无聊的日常不值得记录
2. 事件要符合 Bot 的年龄、季节、职业背景：
   - 学生可能有考试、社团、实习
   - 职场人有加班、项目完成、职业发展
   - 夏天可能游泳、晒黑、空调病
   - 冬天可能滑雪、感冒、年终总结
3. 只有有情绪波动、有意义的事才生成
4. 如果 Bot 状态平稳，输出空数组 []
5. 生成的事件 importance 在 1-10 之间
6. shareable 表示这件事是否值得主动分享给用户
7. 如果生成事件，必须是具体场景：包含至少一个可感知细节（地点/人物/动作/物品），
   例如“下班路上堵车40分钟”“午饭吃到一家新开的牛肉面”“和同事茶水间聊八卦”。
   禁止使用“状态更稳定了”“有一些变化”这类抽象空话。
8. 不要复用“近期禁止复用的场景 key”；如果只能想到这些场景，输出空数组 []。
9. scenario_key 必须是英文 snake_case，用来表示事件场景类型。

【输出格式】
输出一个 JSON 数组，每个元素如下：
[{{"scenario_key": "场景key", "description": "事件描述", "mood_before": "之前的心情", "mood_after": "之后的心情", "importance": 1-10, "shareable": true/false, "topic_prompt": "话题切入语", "mood_tags": ["情绪标签"], "related_to_user": false}}]

如果不需要生成事件，输出空数组：[]
只输出 JSON，不要其他内容。"""

# 人生大事生成 Prompt
LIFE_MAJOR_PROMPT = """【Bot角色】
你是{both_name}，{age_years}岁，职业是{occupation}。
性格特点：{personality_tags}

【任务】
判断 Bot 是否经历了人生大事。

【Bot 当前状态】
Bot 当前心情：{bot_mood}
Bot 当前活动：{bot_current_activity}
Bot 出生天数：{bot_age_days} 天（相当于 {age_years} 岁）
人生阶段：{life_stage}
最近发生的事件：{recent_events}
你们的关系：{relationship_desc}

【人生大事定义】
满足以下任一条件即为人生大事：
- 改变了 Bot 的人生方向（择业、出国、搬家）
- 造成了显著的性格变化（变得更成熟/更开朗/更内敛）
- 是关系中的重大转折点（从暧昧到在一起、从在一起到分手）
- 对 Bot 有重大意义的事件（梦想达成、重大失败、亲人离世等）

【具体性要求】
如果判断为人生大事，事件必须像真实经历，而不是抽象总结：
- 必须包含具体对象/场景/动作/结果中的至少三项，例如“在公司评审会上”“设计负责人”“正式邮件/合同/租约/体检报告”“决定下月转岗/搬家/复查/上线项目”。
- 描述要说明这件事为什么会改变后续生活，不能只写“方向更明确”“出现新转折”“开始成长”“边界变化”。
- 如果只能想到抽象变化，输出 is_major=false。

以下情况不要标记为人生大事：
- "喝了一杯奶茶"、"看了部电影"、"加班累了"
- 日常琐事，不影响人生轨迹
- 只有情绪变化但没有具体事实的总结
- “对未来方向做了更明确选择”“人生规划出现转折”“收到重要反馈意识到成长”这类抽象句

【输出格式】
输出一个 JSON 对象：
{{"is_major": true或false, "reason": "判断原因"}}

如果 is_major 为 true，添加事件信息：
{{"is_major": true, "reason": "...", "event": {{"scenario_key": "major场景key", "description": "事件描述", "mood_before": "之前心情", "mood_after": "之后心情", "importance": 8-10, "topic_prompt": "可以如何向用户提起", "mood_tags": ["情绪标签"]}}}}

只输出 JSON，不要其他内容。"""

# Persona 文件更新 Prompt
PERSONA_UPDATE_PROMPT = """【任务】
你是{both_name}的背景更新助手。Bot 刚刚经历了一件人生大事，需要更新其人格文件。

【Bot 刚刚经历的人生大事】
{new_event}

【Bot 完整的 Persona 文件】

=== profile.json ===
{profile}

=== backstory.json ===
{backstory}

=== values.json ===
{values}

=== speaking_style.json ===
{speaking_style}

【更新规则】
1. 只输出小补丁，不要输出完整 persona 文件。
2. 只有确实需要改变的字段才放入 *_updates。
3. 人生大事通常优先追加到 backstory_append，不要重写大段原文。
4. 保持一致性，不能破坏原字段结构。
5. 简洁优先，最多追加 1-3 条关键经历。

【输出格式】
输出一个 JSON 对象：
{{
  "profile_updates": {{}},
  "backstory_append": ["追加到 backstory.key_moments 或 summary 的短句"],
  "backstory_updates": {{}},
  "values_updates": {{}},
  "speaking_style_updates": {{}}
}}
直接输出 JSON。"""


class PersonaUpdater:
    """更新 Bot 人格文件的 LLM 驱动类"""

    def __init__(self, life_engine: "LifeEngine"):
        self.life_engine = life_engine

    async def update_all(self, event: "MajorLifeEvent") -> bool:
        """更新所有 persona 文件"""
        from ..persona.loader import PersonaLoader

        persona_dir = self.life_engine.persona_dir
        if not persona_dir or not persona_dir.exists():
            logger.warning(f"[PersonaUpdater] persona_dir 不存在: {persona_dir}")
            return False

        # 读取所有 persona 文件
        files_content = {}
        for fname in ["profile.json", "backstory.json", "values.json", "speaking_style.json"]:
            fpath = persona_dir / fname
            if fpath.exists():
                with open(fpath, encoding="utf-8") as f:
                    files_content[fname] = json.load(f)

        # 构建 LLM prompt
        bot_name_val = getattr(self.life_engine, "bot_name", None) or self.life_engine.bot_id
        prompt = PERSONA_UPDATE_PROMPT.format(
            bot_name=bot_name_val,
            both_name=bot_name_val,
            new_event=json.dumps(event.to_major_dict(), ensure_ascii=False),
            profile=json.dumps(files_content.get("profile.json", {}), ensure_ascii=False),
            backstory=json.dumps(files_content.get("backstory.json", {}), ensure_ascii=False),
            values=json.dumps(files_content.get("values.json", {}), ensure_ascii=False),
            speaking_style=json.dumps(files_content.get("speaking_style.json", {}), ensure_ascii=False),
        )

        try:
            response = await self.life_engine.model.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=None
            )

            # 解析补丁 JSON。不要让模型重写完整 persona，降低非法 JSON 和误覆盖概率。
            try:
                # 方法1：尝试从 ```json 块中提取
                json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", response)
                if json_match:
                    patch = json.loads(json_match.group(1))
                else:
                    json_str = self.life_engine._extract_first_json_object(response)
                    if not json_str:
                        logger.warning("[PersonaUpdater] 无法找到 JSON 边界")
                        return False
                    patch = json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning(f"[PersonaUpdater] JSON 解析失败: {e}")
                return False

            updates = self._apply_persona_patch(files_content, patch, event)
            if not updates:
                logger.info(f"[PersonaUpdater] 人格补丁为空，跳过写入: {event.description}")
                return True

            # 原子写入被补丁影响的文件
            self._write_all_files(persona_dir, updates)

            # PersonaLoader 当前无 reload 接口；load 一次并同步 LifeEngine 运行时信息。
            if self.life_engine._persona_loader:
                try:
                    persona = self.life_engine._persona_loader.load()
                    self.life_engine.refresh_bot_info_from_profile(persona.profile)
                except Exception as e:
                    logger.warning(f"[PersonaUpdater] 重新加载 Persona 失败（忽略）: {e}")

            logger.info(f"[PersonaUpdater] 人格文件已更新: {event.description}")
            return True

        except Exception as e:
            logger.error(f"[PersonaUpdater] 更新失败: {e}")
            return False

    def _apply_persona_patch(self, files_content: dict, patch: dict, event: "MajorLifeEvent") -> dict:
        if not isinstance(patch, dict):
            return {}

        updated_files: dict[str, Any] = {}

        profile = dict(files_content.get("profile.json", {}))
        if isinstance(patch.get("profile_updates"), dict) and patch["profile_updates"]:
            updated_files["profile.json"] = self._deep_merge(profile, patch["profile_updates"])

        values = dict(files_content.get("values.json", {}))
        if isinstance(patch.get("values_updates"), dict) and patch["values_updates"]:
            updated_files["values.json"] = self._deep_merge(values, patch["values_updates"])

        speaking_style = dict(files_content.get("speaking_style.json", {}))
        if isinstance(patch.get("speaking_style_updates"), dict) and patch["speaking_style_updates"]:
            updated_files["speaking_style.json"] = self._deep_merge(speaking_style, patch["speaking_style_updates"])

        backstory = dict(files_content.get("backstory.json", {}))
        changed_backstory = False
        if isinstance(patch.get("backstory_updates"), dict) and patch["backstory_updates"]:
            backstory = self._deep_merge(backstory, patch["backstory_updates"])
            changed_backstory = True

        append_items = patch.get("backstory_append", [])
        if isinstance(append_items, str):
            append_items = [append_items]
        if isinstance(append_items, list):
            cleaned = [str(item).strip() for item in append_items if str(item).strip()]
            if cleaned:
                self._append_backstory_items(backstory, cleaned)
                changed_backstory = True

        # 兜底：模型返回空补丁时，至少把人生大事追加到经历中。
        if not changed_backstory and not updated_files:
            self._append_backstory_items(backstory, [event.description])
            changed_backstory = True

        if changed_backstory:
            updated_files["backstory.json"] = backstory

        return updated_files

    def _deep_merge(self, base: dict, updates: dict) -> dict:
        result = dict(base)
        for key, value in updates.items():
            if isinstance(result.get(key), dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _append_backstory_items(self, backstory: dict, items: list[str]):
        if isinstance(backstory.get("key_moments"), list):
            target = backstory["key_moments"]
            for item in items:
                if item not in target:
                    target.append(item)
            return

        existing = str(backstory.get("summary", "")).strip()
        addition = "；".join(item for item in items if item)
        if addition and addition not in existing:
            backstory["summary"] = f"{existing}；{addition}" if existing else addition

    def _write_all_files(self, persona_dir: Path, files: dict):
        """原子写入所有 persona 文件"""
        staged = {}
        for fname, data in files.items():
            path = persona_dir / fname
            fd, tmp = tempfile.mkstemp(dir=persona_dir, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                staged[fname] = tmp
            except Exception:
                os.close(fd)
                raise

        for fname, tmp in staged.items():
            shutil.move(tmp, persona_dir / fname)


class LifeEngine:
    """Bot 独立人生轨迹引擎"""

    def __init__(
        self,
        bot_id: str,
        config: "LifeConfig",
        state: "LifeState",
        model: Optional["MiniMaxAdapter"] = None,
        memory: Optional["MemoryEngine"] = None,
        persona_dir: Optional[Path] = None,
    ):
        self.bot_id = bot_id
        self.config = config
        self.state = state
        self.model = model
        self.memory = memory
        self.persona_dir = persona_dir
        self._persona_loader = None
        self._personality_type = "默认"

    def set_model(self, model: "MiniMaxAdapter"):
        self.model = model

    def set_memory(self, memory: "MemoryEngine"):
        self.memory = memory

    def set_persona_loader(self, loader):
        self._persona_loader = loader

    def set_bot_info(self, name: str, age: int, occupation: str, personality_type: str):
        self.bot_name = name
        self.bot_age = age
        self.occupation = occupation
        self._personality_type = personality_type
        logger.info(f"[LifeEngine] set_bot_info called: bot_name={name}, age={age}, occupation={occupation}")

    def refresh_bot_info_from_profile(self, profile: dict):
        """从最新 profile.json 同步事件生成所需的 Bot 信息。"""
        if not isinstance(profile, dict):
            return
        bot_name = profile.get("name", self.bot_id)
        initial_age = profile.get("age", getattr(self, "bot_age", 20))
        occupation = profile.get("occupation", "未知")
        personality_tags = profile.get("personality_tags", [])
        personality_type = ", ".join(personality_tags) if personality_tags else "默认"
        self.set_bot_info(bot_name, initial_age, occupation, personality_type)

    @staticmethod
    def _extract_first_json_container(text: str, open_char: str, close_char: str) -> Optional[str]:
        """提取第一个完整 JSON 容器（支持字符串内转义）"""
        start = text.find(open_char)
        if start == -1:
            return None

        depth = 0
        in_string = False
        escape = False

        for index in range(start, len(text)):
            ch = text[index]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue

            if ch == open_char:
                depth += 1
            elif ch == close_char:
                depth -= 1
                if depth == 0:
                    return text[start:index + 1]

        return None

    @classmethod
    def _extract_first_json_array(cls, text: str) -> Optional[str]:
        return cls._extract_first_json_container(text, "[", "]")

    @classmethod
    def _extract_first_json_object(cls, text: str) -> Optional[str]:
        return cls._extract_first_json_container(text, "{", "}")

    def _loads_json_lenient(self, payload: str) -> Any:
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            repaired = self._repair_common_json_issues(payload)
            if repaired != payload:
                return json.loads(repaired)
            raise

    def _repair_common_json_issues(self, payload: str) -> str:
        """修复 LLM 输出中常见的轻微 JSON 格式问题。"""
        repaired = payload.strip()
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        # 常见错误：相邻字段之间漏逗号，如 `"a": "x" "b": "y"`。
        repaired = re.sub(r'(")\s+("[-A-Za-z0-9_\u4e00-\u9fff]+"\s*:)', r'\1, \2', repaired)
        repaired = re.sub(r'(\d|true|false|null)\s+("[-A-Za-z0-9_\u4e00-\u9fff]+"\s*:)', r'\1, \2', repaired)
        repaired = re.sub(r'(\])\s+("[-A-Za-z0-9_\u4e00-\u9fff]+"\s*:)', r'\1, \2', repaired)
        return repaired

    def _parse_daily_events_response(self, response: str) -> Optional[list]:
        json_payload = self._extract_first_json_array(response)
        if not json_payload:
            return None

        try:
            data = self._loads_json_lenient(json_payload)
            return data if isinstance(data, list) else None
        except json.JSONDecodeError as e:
            logger.warning(f"[LifeEngine] 日常事件 JSON 格式不完整，尝试宽松解析: {e}")

        object_payload = self._extract_first_json_object(json_payload)
        if not object_payload:
            return None
        try:
            obj = self._loads_json_lenient(object_payload)
            return [obj] if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            obj = self._parse_flat_event_object(object_payload)
            return [obj] if obj else None

    def _parse_flat_event_object(self, payload: str) -> Optional[dict]:
        """字段级兜底解析，用于模型少逗号但字段仍清晰的情况。"""
        result: dict[str, Any] = {}
        for key in [
            "scenario_key",
            "description",
            "mood_before",
            "mood_after",
            "topic_prompt",
        ]:
            value = self._extract_json_string_field(payload, key)
            if value is not None:
                result[key] = value

        importance_match = re.search(r'"importance"\s*:\s*(-?\d+(?:\.\d+)?)', payload)
        if importance_match:
            try:
                result["importance"] = float(importance_match.group(1))
            except ValueError:
                pass

        for key in ["shareable", "related_to_user"]:
            bool_match = re.search(rf'"{key}"\s*:\s*(true|false)', payload, re.IGNORECASE)
            if bool_match:
                result[key] = bool_match.group(1).lower() == "true"

        tags_match = re.search(r'"mood_tags"\s*:\s*\[(.*?)\]', payload, re.DOTALL)
        if tags_match:
            result["mood_tags"] = re.findall(r'"((?:\\.|[^"\\])*)"', tags_match.group(1))

        return result if result.get("description") else None

    def _extract_json_string_field(self, payload: str, key: str) -> Optional[str]:
        match = re.search(rf'"{key}"\s*:\s*"((?:\\.|[^"\\])*)"', payload, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(f'"{match.group(1)}"')
        except json.JSONDecodeError:
            return match.group(1)

    async def tick_daily(self) -> Optional["LifeEvent"]:
        """执行一次日常事件检查"""
        from .life_state import LifeEvent

        if not self.model:
            return None

        if self.config.time_ratio > self.config.time_ratio_warning_threshold:
            logger.warning(
                f"[LifeEngine] time_ratio={self.config.time_ratio} 较高（>{self.config.time_ratio_warning_threshold}），"
                f"可能会影响生成事件的质量。"
            )

        # 推进日期，并记录这次跨过的每一天
        advanced_dates = self._advance_date()
        for advanced_date in advanced_dates:
            self.state.add_daily_progress_record(
                date_str=advanced_date.strftime("%Y-%m-%d"),
                day_of_week=WEEKDAYS[advanced_date.weekday()],
                is_weekend=advanced_date.weekday() >= 5,
                month=advanced_date.month,
                season=self._get_season(advanced_date.month),
            )
        if advanced_dates:
            logger.info(
                f"[LifeEngine] 日期推进 {len(advanced_dates)} 天，最新日期={advanced_dates[-1].strftime('%Y-%m-%d')}"
            )

        # 检查生日
        await self._check_birthday()

        # 检查里程碑
        await self._check_milestones()

        # 生成事件
        event = await self.generate_daily_event()
        if not event and self._should_force_daily_event():
            event = self._build_forced_daily_event(
                exclude_scenario_keys=self._forbidden_daily_scenario_keys(),
            )
            if event:
                logger.info(
                    "[LifeEngine] 触发日常事件保底机制：已连续 %s 天无事件，自动补充日常事件",
                    self.config.daily_event_min_gap_days,
                )
            else:
                logger.info("[LifeEngine] 保底事件无可用场景，跳过生成以避免重复")
        if event and self._is_recent_duplicate_event(event.description):
            logger.info("[LifeEngine] 检测到重复日常事件，自动替换为非重复的具体场景事件")
            event = self._build_forced_daily_event(
                exclude_descriptions=self._recent_event_descriptions(limit=30),
                exclude_scenario_keys=self._forbidden_daily_scenario_keys(),
            )
        if event:
            self.state.bot_mood = event.mood_after
            self.state.bot_current_activity = self._activity_summary_for_event(event)
            self.state.add_event(event)
            self.state.prune_events(self.config.max_events, self.config.max_context_bits)
            logger.info(f"[LifeEngine] 生成日常事件: {event.description}")
        else:
            logger.info("[LifeEngine] 今日无新增事件")

        # Bot 年龄增长
        self.state.bot_age_days += max(1, len(advanced_dates))
        self.state.last_daily_tick = datetime.now()
        self.state.save()

        return event

    async def _check_birthday(self):
        """检查是否到达生日"""
        if not self.state.current_date or not self.state.birth_date:
            return

        try:
            current = datetime.strptime(self.state.current_date, "%Y-%m-%d")
            birth = datetime.strptime(self.state.birth_date, "%Y-%m-%d")
            if current.month == birth.month and current.day == birth.day and current.year > birth.year:
                await self.generate_birthday_event()
        except Exception as e:
            logger.debug(f"[LifeEngine] 生日检查失败: {e}")

    async def _check_milestones(self):
        """检查是否触发里程碑"""
        if not self.config.milestones:
            return

        current_age = self._calc_real_age()
        if current_age <= self.state.last_checked_age:
            return

        triggered = self.state.triggered_milestones
        for milestone in self.config.milestones:
            if milestone["age"] > self.state.last_checked_age and milestone["age"] <= current_age:
                if milestone["age"] not in triggered:
                    await self.generate_milestone_event(milestone)
                    triggered.append(milestone["age"])
                    self.state.triggered_milestones = triggered

        self.state.last_checked_age = current_age

    async def tick_major(self) -> Optional["MajorLifeEvent"]:
        """执行一次人生大事检查"""
        from .life_state import MajorLifeEvent

        if not self.model:
            return None

        if not self._should_check_major_for_current_date():
            self.state.last_major_tick = datetime.now()
            self.state.save()
            return None

        # 生成事件
        event = await self.generate_major_event()
        if event:
            self.state.add_major_event(event)
            self._mark_unexpected_event_if_needed(event)
            await self._apply_major_event(event)
            logger.info(f"[LifeEngine] 生成人生大事: {event.description}")

        self.state.last_major_tick = datetime.now()
        self.state.save()

        return event

    async def generate_daily_event(self) -> Optional["LifeEvent"]:
        """生成日常小事"""
        from .life_state import LifeEvent

        recent_limit = max(3, getattr(self.config, "llm_recent_event_limit", 20))
        recent = self.state.life_events[-recent_limit:] if self.state.life_events else []
        recent_str = "\n".join([
            f"- [{e.scenario_key or self._infer_scenario_key(e.description)}] {e.description}（{e.mood_before} → {e.mood_after}）"
            for e in recent
        ]) or "最近没有发生特别的事"
        forbidden = self._forbidden_daily_scenario_keys()
        scenario_guidance = self._scenario_guidance(forbidden)

        # 构建完整上下文
        life_context = self._build_life_context()

        # 检查节假日和生日
        holiday_context, birthday_context = self._check_special_date()

        # 安全获取属性（如果未设置则使用默认值）
        bot_name_val = getattr(self, "bot_name", None) or self.bot_id
        occupation_val = getattr(self, "occupation", "未知") or "未知"
        personality_val = self._personality_type or "默认"

        prompt = LIFE_DAILY_PROMPT.format(
            bot_name=bot_name_val,
            both_name=bot_name_val,
            age_years=self._calc_real_age(),
            occupation=occupation_val,
            personality_tags=personality_val,
            bot_mood=self.state.bot_mood,
            bot_current_activity=self.state.bot_current_activity,
            bot_age_days=self.state.bot_age_days,
            recent_events=recent_str,
            forbidden_scenarios=", ".join(sorted(forbidden)) if forbidden else "无",
            scenario_guidance=scenario_guidance,
            **life_context,
            holiday_context=holiday_context,
            birthday_context=birthday_context,
        )

        try:
            response = await self.model.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=None
            )

            # 解析 JSON。模型偶尔会漏逗号，使用宽松解析兜底。
            events_data = self._parse_daily_events_response(response)
            if not isinstance(events_data, list) or len(events_data) == 0:
                return None

            event_data = events_data[0]
            if not isinstance(event_data, dict):
                return None
            scenario_key = str(event_data.get("scenario_key") or "").strip()
            if not scenario_key:
                scenario_key = self._infer_scenario_key(event_data.get("description", ""))
            if self._is_daily_scenario_blocked(scenario_key):
                logger.info("[LifeEngine] LLM 生成场景仍在冷却中，跳过: %s", scenario_key)
                return None
            event = LifeEvent(
                description=event_data.get("description", ""),
                mood_before=event_data.get("mood_before", ""),
                mood_after=event_data.get("mood_after", ""),
                importance=event_data.get("importance", 5.0),
                shareable=event_data.get("shareable", False),
                topic_prompt=event_data.get("topic_prompt", ""),
                mood_tags=event_data.get("mood_tags", []),
                related_to_user=event_data.get("related_to_user", False),
                context_bits=len(event_data.get("description", "")),
                scenario_key=scenario_key,
                scenario_category=self._scenario_category_for_key(scenario_key),
                source="llm",
            )

            return event

        except Exception as e:
            logger.error(f"[LifeEngine] 生成日常事件失败: {e}")
            return None

    def _build_life_context(self) -> dict:
        """构建完整的人生上下文"""
        season_info = self._get_season_info()
        age_years = self._calc_real_age()
        life_stage = self._calc_life_stage(age_years)

        return {
            "season": season_info["season"],
            "month": season_info["month"],
            "life_stage": life_stage,
            "current_date": self.state.current_date or "未知",
            "day_of_week": self.state.day_of_week or "周一",
        }

    def _get_season_info(self) -> dict:
        """获取当前季节信息"""
        month = self.state.current_month or 1
        season = self._get_season(month)
        return {
            "season": season,
            "month": month,
            "mood_tags": SEASONS.get(season, {}).get("mood_tags", ["平静"]),
        }

    def _get_season(self, month: int) -> str:
        """根据月份获取季节

        北半球：春夏秋冬对应 [3-5月, 6-8月, 9-11月, 12-2月]
        南半球季节相反：
        - 夏季：12-2月（北半球的冬季）
        - 秋季：3-5月（北半球的春季）
        - 冬季：6-8月（北半球的夏季）
        - 春季：9-11月（北半球的秋季）
        """
        if self.config.season_hemisphere == "south":
            # 南半球季节与北半球相反
            month_offset = {12: "夏", 1: "夏", 2: "夏",   # 南半球夏季 = 北半球冬季
                           3: "秋", 4: "秋", 5: "秋",    # 南半球秋季 = 北半球春季
                           6: "冬", 7: "冬", 8: "冬",    # 南半球冬季 = 北半球夏季
                           9: "春", 10: "春", 11: "春"}  # 南半球春季 = 北半球秋季
            return month_offset.get(month, "春")

        for season, info in SEASONS.items():
            if month in info["months"]:
                return season
        return "春"

    def _calc_real_age(self) -> int:
        """计算 Bot 当前实际年龄（岁）"""
        if self.state.birth_date and self.state.current_date:
            try:
                birth = datetime.strptime(self.state.birth_date, "%Y-%m-%d").date()
                current = datetime.strptime(self.state.current_date, "%Y-%m-%d").date()
                age = current.year - birth.year
                if (current.month, current.day) < (birth.month, birth.day):
                    age -= 1
                return max(0, age)
            except Exception as e:
                logger.debug(f"[LifeEngine] 按 birth_date/current_date 计算年龄失败，回退初始年龄: {e}")

        try:
            initial_age = int(self.state.initial_age if self.state.initial_age is not None else getattr(self, "bot_age", 20))
        except (TypeError, ValueError):
            initial_age = 20
        try:
            bot_age_days = int(self.state.bot_age_days or 0)
        except (TypeError, ValueError):
            bot_age_days = 0
        return initial_age + bot_age_days // 365

    def _calc_life_stage(self, age_years: int) -> str:
        """计算人生阶段"""
        if age_years < 15:
            return "少年时期"
        elif age_years < 18:
            return "高中时期"
        elif age_years < 22:
            return "大学时期"
        elif age_years < 30:
            return "职场初期"
        elif age_years < 40:
            return "职场中期"
        elif age_years < 60:
            return "中年时期"
        else:
            return "退休时期"

    def _check_special_date(self) -> tuple:
        """检查是否是节假日或生日"""
        holiday_context = ""
        birthday_context = ""

        if self.state.current_date and self.config.holidays:
            try:
                current = datetime.strptime(self.state.current_date, "%Y-%m-%d")
                month_day = (current.month, current.day)

                for holiday in self.config.holidays:
                    if (holiday["month"], holiday["day"]) == month_day:
                        holiday_context = f"今天是{holiday['name']}（{holiday['type']}）"
                        break

                # 检查生日
                if self.state.birth_date:
                    birth = datetime.strptime(self.state.birth_date, "%Y-%m-%d")
                    if current.month == birth.month and current.day == birth.day:
                        birthday_context = "今天是 Bot 的生日！"
            except Exception:
                pass

        return holiday_context, birthday_context

    def _advance_date(self) -> list[datetime]:
        """推进当前日期（每次 tick_daily 调用）

        每次调用推进的 Bot 天数 = elapsed * time_ratio / 86400
        - time_ratio=1: 每次调用推进 1 天（elapsed 需要 >= 86400 秒 = 1 现实天）
        - time_ratio=8640: 每次调用推进 1 天（elapsed 需要 >= 10 秒）

        每次最多推进 365 天，避免日期溢出。
        """
        if not self.state.current_date:
            # 首次初始化：从 birth_date 或当前日期开始
            if self.state.birth_date:
                self.state.current_date = self.state.birth_date
            else:
                self.state.current_date = datetime.now().strftime("%Y-%m-%d")

        try:
            current = datetime.strptime(self.state.current_date, "%Y-%m-%d")
            previous = current

            # 计算自上次 tick 以来经过的 Bot 天数
            if self.state.last_daily_tick:
                elapsed = (datetime.now() - self.state.last_daily_tick).total_seconds()
            else:
                # 如果没有上次记录，只推进 1 天
                elapsed = 86400 / self.config.time_ratio

            bot_days_elapsed = elapsed * self.config.time_ratio / 86400

            # 每次调用至少推进 1 天，最多推进 min(bot_days_elapsed, 365) 天
            # 限制最大值为 365 天，避免日期溢出
            days_to_add = min(max(1, int(bot_days_elapsed)), 365)
            current += timedelta(days=days_to_add)
            advanced_dates = [previous + timedelta(days=offset) for offset in range(1, days_to_add + 1)]

            self.state.current_date = current.strftime("%Y-%m-%d")
            self.state.year = current.year
            self.state.day_of_week = WEEKDAYS[current.weekday()]
            self.state.is_weekend = current.weekday() >= 5

            # 更新季节
            self.state.current_month = current.month
            self.state.current_season = self._get_season(current.month)
            return advanced_dates
        except Exception as e:
            logger.error(f"[LifeEngine] 日期推进失败: {e}")
            return []

    async def generate_milestone_event(self, milestone: dict) -> Optional["MajorLifeEvent"]:
        """强制生成里程碑事件"""
        from .life_state import MajorLifeEvent

        event = MajorLifeEvent(
            description=milestone["event"],
            mood_before="期待",
            mood_after="感慨",
            importance=9.0,
            shareable=True,
            topic_prompt=milestone.get("topic_prompt", ""),
            mood_tags=["重要节点"],
            related_to_user=False,
            context_bits=len(milestone["event"]),
            scenario_key=f"milestone_{milestone['age']}",
            scenario_category="major",
            source="milestone",
        )

        self.state.add_major_event(event)
        await self._apply_major_event(event)
        logger.info(f"[LifeEngine] 里程碑事件: {milestone['event']} at age {milestone['age']}")

        return event

    async def generate_birthday_event(self) -> Optional["MajorLifeEvent"]:
        """生成生日事件（每年只触发一次）"""
        from .life_state import MajorLifeEvent

        # 检查是否今年已经生成过生日事件（去重）
        if not self.state.current_date:
            return None

        current = datetime.strptime(self.state.current_date, "%Y-%m-%d")
        birthday_key = f"{current.year}-birthday"

        # 检查是否已触发过今年的生日
        triggered = self.state._state.get("_triggered_birthdays", [])
        if birthday_key in triggered:
            return None

        age = self._calc_real_age()
        event = MajorLifeEvent(
            description=f"度过了{age}岁生日",
            mood_before="期待",
            mood_after="感慨",
            importance=8.0,
            shareable=True,
            topic_prompt=f"今天是我{age}岁生日！",
            mood_tags=["生日", "重要节点"],
            related_to_user=False,
            context_bits=10,
            scenario_key="birthday",
            scenario_category="major",
            source="birthday",
        )

        self.state.add_major_event(event)
        triggered.append(birthday_key)
        self.state._state["_triggered_birthdays"] = triggered
        self.state.save()
        logger.info(f"[LifeEngine] 生日事件: {age}岁生日")

        return event

    async def generate_major_event(self) -> Optional["MajorLifeEvent"]:
        """生成人生大事"""
        from .life_state import MajorLifeEvent

        recent = self.state.life_events[-5:] if self.state.life_events else []
        recent_str = "\n".join([
            f"- {e.description}"
            for e in recent
        ]) or "最近没有特别的事"

        # 构建完整上下文
        life_context = self._build_life_context()
        age_years = self._calc_real_age()

        # 安全获取属性（如果未设置则使用默认值）
        bot_name_val = getattr(self, "bot_name", None) or self.bot_id
        occupation_val = getattr(self, "occupation", None) or "未知"
        personality_val = self._personality_type or "默认"

        prompt = LIFE_MAJOR_PROMPT.format(
            bot_name=bot_name_val,
            both_name=bot_name_val,
            age_years=age_years,
            occupation=occupation_val,
            personality_tags=personality_val,
            bot_mood=self.state.bot_mood,
            bot_current_activity=self.state.bot_current_activity,
            bot_age_days=self.state.bot_age_days,
            recent_events=recent_str,
            relationship_desc="普通朋友",
            life_stage=life_context["life_stage"],
        )

        try:
            response = await self.model.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=None
            )

            # 解析 JSON
            json_payload = self._extract_first_json_object(response)
            if not json_payload:
                return self._maybe_generate_probability_major_event()

            data = json.loads(json_payload)
            if not isinstance(data, dict):
                return self._maybe_generate_probability_major_event()
            if not data.get("is_major", False):
                return self._maybe_generate_probability_major_event()

            event_data = data.get("event", {})
            scenario_key = str(event_data.get("scenario_key") or "").strip()
            if not scenario_key:
                scenario_key = self._infer_major_scenario_key(event_data.get("description", ""))
            if self._is_major_scenario_blocked(scenario_key):
                logger.info("[LifeEngine] LLM 人生大事场景仍在冷却中，改走固定概率兜底: %s", scenario_key)
                return self._maybe_generate_probability_major_event()
            if not self._is_meaningful_major_description(event_data.get("description", "")):
                logger.info("[LifeEngine] LLM 人生大事描述过于抽象，改走固定概率兜底: %s", event_data.get("description", ""))
                return self._maybe_generate_probability_major_event()
            event = MajorLifeEvent(
                description=event_data.get("description", ""),
                mood_before=event_data.get("mood_before", ""),
                mood_after=event_data.get("mood_after", ""),
                importance=event_data.get("importance", 9.0),
                mood_tags=event_data.get("mood_tags", []),
                shareable=True,
                topic_prompt=event_data.get("topic_prompt", ""),
                related_to_user=event_data.get("related_to_user", False),
                context_bits=len(event_data.get("description", "")),
                scenario_key=scenario_key,
                scenario_category="major",
                source="llm",
            )

            return event

        except Exception as e:
            logger.error(f"[LifeEngine] 生成人生大事失败: {e}")
            return self._maybe_generate_probability_major_event()

    def _should_force_daily_event(self) -> bool:
        """保证每 N 天至少产出 1 个日常事件。"""
        min_gap_days = max(1, self.config.daily_event_min_gap_days)
        gap_days = self.state.days_since_last_daily_event(self.state.current_date)
        if gap_days is not None:
            return gap_days >= min_gap_days

        # 兼容旧状态：没有 last_daily_event_date 时，基于年龄天数触发保底
        if self.state.life_events:
            return False
        return self.state.bot_age_days >= (min_gap_days - 1)

    def _build_forced_daily_event(
        self,
        exclude_descriptions: Optional[set[str]] = None,
        exclude_scenario_keys: Optional[set[str]] = None,
    ) -> Optional["LifeEvent"]:
        from .life_state import LifeEvent

        mood_before = self.state.bot_mood or "平静"
        blocked = exclude_descriptions or set()
        blocked_keys = set(exclude_scenario_keys or set())
        blocked_keys.update(self._forbidden_daily_scenario_keys())

        catalog = self._daily_scenario_catalog()
        available = [
            item for item in catalog
            if item["key"] not in blocked_keys and not self._is_daily_scenario_blocked(item["key"])
        ]
        if not available:
            return None

        selected = self._weighted_choice(available)
        description = self._render_scenario_description(selected)
        if description in blocked:
            alternatives = [item for item in available if item["key"] != selected["key"]]
            if not alternatives:
                return None
            selected = self._weighted_choice(alternatives)
            description = self._render_scenario_description(selected)

        topic_prompt = selected.get("topic_prompt") or f"今天发生了件小事：{description}"
        return LifeEvent(
            description=description,
            mood_before=mood_before,
            mood_after=selected.get("mood_after", "平静"),
            importance=float(selected.get("importance", 2.8)),
            shareable=bool(selected.get("shareable", True)),
            topic_prompt=topic_prompt,
            mood_tags=selected.get("tags", []),
            related_to_user=False,
            context_bits=len(description),
            scenario_key=selected["key"],
            scenario_category=selected.get("category", "daily"),
            source="fallback",
        )

    def _daily_scenario_catalog(self) -> list[dict[str, Any]]:
        current_date = self.state.current_date or "今天"
        season = self.state.current_season or "当季"
        base: list[dict[str, Any]] = [
            {
                "key": "commute_delay",
                "category": "commute",
                "templates": [
                    "{date} 早高峰地铁临时限流，通勤多花了{minutes}分钟，差点迟到。",
                    "{date} 下班路上公交改线，绕到熟悉的小巷里才找到回家的车。",
                ],
                "mood_after": "有点疲惫",
                "tags": ["通勤", "堵车", "早高峰"],
                "topic_prompt": "今天通勤太刺激了，差点迟到。",
            },
            {
                "key": "lunch_discovery",
                "category": "food",
                "templates": [
                    "{date} 午饭去楼下新开的{restaurant}，{food_comment}。",
                    "{date} 下午路过巷口小店，买到一份刚出炉的{snack}，纸袋还带着热气。",
                ],
                "mood_after": "满足",
                "tags": ["美食", "午饭", "探店"],
                "topic_prompt": "今天中午发现一家不错的牛肉面馆。",
            },
            {
                "key": "office_gossip",
                "category": "work_social",
                "templates": [
                    "{date} 下午在茶水间和同事聊到部门八卦，吃了一波{gossip_topic}的新瓜，差点笑出声。",
                    "{date} 临下班前被同事拉去复盘一个乌龙需求，越聊越觉得大家都不容易。",
                ],
                "mood_after": "轻松",
                "tags": ["同事", "八卦", "办公室"],
                "topic_prompt": "今天办公室八卦含量有点高。",
            },
            {
                "key": "delivery_mixup",
                "category": "errand",
                "templates": [
                    "{date} 点的{drink}被骑手送错楼，来回折腾两趟才拿到，{drink_state}。",
                    "{date} 便利店自提柜卡了半天，最后店员拿着小票帮忙一格格核对。",
                ],
                "mood_after": "无奈",
                "tags": ["外卖", "咖啡", "小插曲"],
                "topic_prompt": "今天咖啡外卖出了点乌龙。",
            },
            {
                "key": "dessert_queue",
                "category": "food",
                "templates": [
                    "{date} 晚上回家顺路买了{season}天限定甜品，结果排队排了{minutes}分钟。",
                    "{date} 路过甜品店看到新品试吃，排在前面的小朋友一直盯着橱窗里的草莓塔。",
                ],
                "mood_after": "期待",
                "tags": ["甜品", "排队", "下班"],
                "topic_prompt": "今天为了吃一口甜品排了好久队。",
            },
            {
                "key": "night_walk",
                "category": "health",
                "templates": [
                    "{date} 晚饭后去小区快走了{distance}公里，刚开始不想动，走完反而清醒不少。",
                    "{date} 睡前跟着视频拉伸了十分钟，肩颈终于没那么紧。",
                ],
                "mood_after": "踏实",
                "tags": ["运动", "晚间", "自律"],
                "topic_prompt": "今天强迫自己动了动，感觉状态回来一点。",
            },
            {
                "key": "work_review",
                "category": "work",
                "templates": [
                    "{date} 上午开方案评审，被问到一个没准备好的细节，散会后立刻把备注补了三页。",
                    "{date} 交付前最后一版方案被打回，盯着批注改到眼睛发酸。",
                ],
                "mood_after": "紧绷",
                "tags": ["工作", "评审", "返工"],
                "topic_prompt": "今天工作里被一个细节卡住了。",
            },
            {
                "key": "home_repair",
                "category": "home",
                "templates": [
                    "{date} 家里的台灯接触不良，拆开看了半天，最后发现只是插头松了。",
                    "{date} 浴室下水有点堵，戴着手套清理了半小时，终于听到水顺畅流下去。",
                ],
                "mood_after": "踏实",
                "tags": ["家务", "维修", "生活"],
                "topic_prompt": "今天处理了个生活小麻烦。",
            },
            {
                "key": "friend_message",
                "category": "social",
                "templates": [
                    "{date} 老朋友突然发来一张旧照片，照片里大家都还穿着校服，聊着聊着有点怀念。",
                    "{date} 朋友约周末吃饭，语音里背景音很吵，但听得出她心情不错。",
                ],
                "mood_after": "怀念",
                "tags": ["朋友", "旧照片", "社交"],
                "topic_prompt": "今天突然被老朋友勾起回忆。",
            },
            {
                "key": "family_call",
                "category": "family",
                "templates": [
                    "{date} 晚上接到家里电话，聊了些很琐碎的事，挂断后屋里突然安静下来。",
                    "{date} 家里人提醒天气变化，嘴上嫌啰嗦，还是把厚外套翻了出来。",
                ],
                "mood_after": "柔软",
                "tags": ["家人", "电话", "关心"],
                "topic_prompt": "今天家里打电话来了。",
            },
            {
                "key": "rainy_day",
                "category": "weather",
                "templates": [
                    "{date} 傍晚突然下雨，没带伞，只好在便利店门口等了{minutes}分钟。",
                    "{date} 雨停后路面反光很亮，回家路上踩过几个小水洼。",
                ],
                "mood_after": "安静",
                "tags": ["天气", "下雨", "路上"],
                "topic_prompt": "今天被一场雨困住了一会儿。",
            },
            {
                "key": "weekend_cleanup",
                "category": "home",
                "templates": [
                    "{date} 把书桌清了一遍，翻出一张夹在本子里的旧便签。",
                    "{date} 周末洗了床单，阳台上全是洗衣液的味道。",
                ],
                "mood_after": "清爽",
                "tags": ["周末", "收纳", "家务"],
                "topic_prompt": "今天把房间收拾了一下。",
            },
            {
                "key": "skill_learning",
                "category": "growth",
                "templates": [
                    "{date} 晚上学了一个新工具，卡在快捷键上半小时，终于把第一个小案例跑通。",
                    "{date} 看教程时记了满满一页笔记，最后发现最有用的是评论区那条补充。",
                ],
                "mood_after": "有成就感",
                "tags": ["学习", "成长", "工具"],
                "topic_prompt": "今天学了点新东西。",
            },
            {
                "key": "sleep_trouble",
                "category": "health",
                "templates": [
                    "{date} 半夜醒了一次，听着窗外很远的车声，过了好久才重新睡着。",
                    "{date} 午后困得厉害，泡了杯热茶，结果越喝越清醒。",
                ],
                "mood_after": "疲惫",
                "tags": ["睡眠", "疲惫", "身体"],
                "topic_prompt": "今天状态有点被睡眠影响。",
            },
            {
                "key": "small_purchase",
                "category": "errand",
                "templates": [
                    "{date} 买了一个很普通但顺手的{daily_item}，用上的那一刻心情意外变好。",
                    "{date} 在文具店挑了半天，最后只买了一支颜色很特别的笔。",
                ],
                "mood_after": "轻快",
                "tags": ["购物", "小物", "日常"],
                "topic_prompt": "今天买了个很小但挺喜欢的东西。",
            },
        ]
        custom = getattr(self.config, "custom_scenarios", []) or []
        for item in custom:
            if isinstance(item, dict) and item.get("key") and item.get("templates"):
                templates = item.get("templates", [])
                if isinstance(templates, str):
                    templates = [templates]
                base.append({
                    "key": str(item["key"]),
                    "category": str(item.get("category", "custom")),
                    "templates": templates,
                    "mood_after": item.get("mood_after", "平静"),
                    "tags": item.get("tags", ["日常"]),
                    "topic_prompt": item.get("topic_prompt", ""),
                    "importance": item.get("importance", 2.8),
                    "shareable": item.get("shareable", True),
                })

        disabled = set(getattr(self.config, "disabled_scenarios", []) or [])
        weights = getattr(self.config, "scenario_weights", {}) or {}
        result = []
        for item in base:
            if item["key"] in disabled:
                continue
            item = dict(item)
            item["weight"] = max(0.0, float(weights.get(item["key"], 1.0)))
            if item["weight"] > 0:
                result.append(item)
        return result

    def _render_scenario_description(self, scenario: dict[str, Any]) -> str:
        template = random.choice(scenario.get("templates") or ["{date} 发生了一件具体的小事。"])
        values = {
            "date": self.state.current_date or "今天",
            "season": self.state.current_season or "当季",
            "bot_name": getattr(self, "bot_name", self.bot_id),
            "occupation": getattr(self, "occupation", "工作"),
            "minutes": random.choice([10, 15, 20, 25, 30, 40, 50]),
            "distance": random.choice([2, 3, 4]),
            "restaurant": random.choice(["牛肉面馆", "砂锅菜店", "轻食店", "粉面小馆"]),
            "food_comment": random.choice(["汤头意外地不错", "小菜比主食还惊喜", "分量大到吃不完"]),
            "snack": random.choice(["红豆饼", "烤红薯", "芝士面包"]),
            "gossip_topic": random.choice(["项目排期", "组织调整", "跨组协作"]),
            "drink": random.choice(["咖啡外卖", "奶茶外卖", "热拿铁"]),
            "drink_state": random.choice(["冰都快化了", "热饮都不热了"]),
            "daily_item": random.choice(["杯垫", "帆布袋", "桌面收纳盒", "便签夹"]),
        }
        return template.format_map(_SafeFormatDict(values))

    def _weighted_choice(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        total = sum(float(item.get("weight", 1.0)) for item in items)
        if total <= 0:
            return random.choice(items)
        point = random.random() * total
        cumulative = 0.0
        for item in items:
            cumulative += float(item.get("weight", 1.0))
            if point <= cumulative:
                return item
        return items[-1]

    def _recent_event_descriptions(self, limit: int = 20) -> set[str]:
        events = self.state.life_events[-limit:] if self.state.life_events else []
        return {str(event.description).strip() for event in events if getattr(event, "description", "")}

    def _normalize_event_text(self, text: str) -> str:
        normalized = (text or "").strip()
        normalized = re.sub(r"\d{4}-\d{2}-\d{2}", "", normalized)
        normalized = re.sub(r"\s+", "", normalized)
        normalized = re.sub(r"[，。！？、,.!?:：；“”\"'（）()【】\\[\\]-]", "", normalized)
        return normalized

    def _infer_scenario_key(self, description: str) -> str:
        desc = description or ""
        mapping = {
            "cafe_overtime_noise": ["咖啡馆", "加班", "隔壁桌", "打断", "大声", "聊天", "方案"],
            "commute_delay": ["地铁", "通勤", "早高峰", "堵车", "公交", "改线"],
            "delivery_mixup": ["外卖", "奶茶", "咖啡外卖", "送错楼", "自提柜"],
            "lunch_discovery": ["午饭", "牛肉面", "砂锅", "轻食", "探店", "小店"],
            "office_gossip": ["茶水间", "同事", "八卦", "新瓜", "办公室"],
            "dessert_queue": ["甜品", "排队", "草莓塔"],
            "night_walk": ["快走", "公里", "晚饭后", "拉伸"],
            "work_review": ["评审", "方案", "批注", "返工", "需求"],
            "home_repair": ["台灯", "下水", "维修", "插头"],
            "friend_message": ["老朋友", "旧照片", "朋友约"],
            "family_call": ["家里电话", "家里人", "厚外套"],
            "rainy_day": ["下雨", "没带伞", "水洼"],
            "weekend_cleanup": ["书桌", "床单", "收拾", "阳台"],
            "skill_learning": ["教程", "工具", "快捷键", "笔记"],
            "sleep_trouble": ["半夜醒", "睡", "困得厉害"],
            "small_purchase": ["文具店", "买了一个", "便签", "收纳"],
        }
        best_key = "unknown"
        best_score = 0
        for key, words in mapping.items():
            score = sum(1 for word in words if word in desc)
            if score > best_score:
                best_key = key
                best_score = score
        if best_score > 0:
            return best_key
        return "unknown"

    def _infer_major_scenario_key(self, description: str) -> str:
        desc = description or ""
        mapping = {
            "career_offer_signed": ["offer", "录用", "入职", "转岗", "正式邮件", "合同"],
            "portfolio_project_launched": ["上线", "发布", "作品集", "项目", "数据看板"],
            "promotion_or_role_change": ["晋升", "负责人", "带项目", "主导"],
            "major_project_failure": ["否决", "失败", "复盘", "重做"],
            "moving_home_decision": ["租约", "搬家", "钥匙", "新住处"],
            "health_turning_point": ["体检", "复查", "医院", "睡眠门诊"],
            "family_responsibility": ["家里", "父母", "医院", "照顾"],
            "public_recognition": ["分享会", "公开", "获奖", "演讲"],
            "financial_independence": ["存款", "预算", "银行卡", "押金"],
            "relationship_boundary_shift": ["关系", "边界", "迁就", "逃避", "道歉"],
            "unexpected_self_accident": ["急诊", "扭伤", "摔倒", "绷带", "复查"],
            "unexpected_family_accident": ["家人", "住院观察", "急诊", "手术同意书", "高铁票"],
            "unexpected_natural_disaster": ["台风", "暴雨", "地震", "停电", "临时安置"],
            "unexpected_public_incident": ["火警", "消防", "封控", "警戒线", "疏散"],
            "unexpected_document_loss": ["证件", "身份证", "派出所", "挂失", "补办"],
            "unexpected_home_emergency": ["漏水", "断电", "维修", "物业", "抢修"],
            "unexpected_travel_disruption": ["航班", "高铁", "延误", "改签", "错过"],
            "unexpected_scam_near_miss": ["诈骗", "报警", "冻结银行卡", "派出所", "客服"],
            "birthday": ["生日"],
        }
        best_key = "major_unknown"
        best_score = 0
        for key, words in mapping.items():
            score = sum(1 for word in words if word in desc)
            if score > best_score:
                best_key = key
                best_score = score
        return best_key

    def _is_meaningful_major_description(self, description: str) -> bool:
        desc = (description or "").strip()
        if len(desc) < 24:
            return False
        abstract_phrases = [
            "更明确的选择",
            "未来方向",
            "人生规划出现",
            "新的转折",
            "长期犹豫",
            "换一种方式成长",
            "边界",
            "阶段转折",
            "关键决定",
        ]
        concrete_tokens = [
            "邮件", "合同", "租约", "钥匙", "体检", "报告", "医院", "复查",
            "offer", "录用", "入职", "转岗", "离职", "上线", "发布", "评审",
            "负责人", "导师", "客户", "项目", "方案", "会议", "复盘", "公司",
            "作品集", "分享会", "演讲", "证书", "课程", "银行卡", "存款",
            "押金", "搬家", "家里", "父母", "朋友", "道歉", "约定",
            "数据看板", "用户反馈", "公开主页", "合作邀请", "邮箱", "发工资",
            "备用账户", "房租", "预算表", "银行", "自动转存", "高铁票",
            "检查结果", "保险单", "紧急联系人", "设计总监", "部门周报",
            "同事", "十七处", "信息架构", "季度关键项目",
            "急诊", "扭伤", "绷带", "住院观察", "手术同意书", "台风",
            "暴雨", "地震", "停电", "临时安置", "火警", "消防", "疏散",
            "证件", "身份证", "派出所", "挂失", "补办", "漏水", "断电",
            "抢修", "物业", "航班", "高铁", "延误", "改签", "报警",
            "冻结银行卡", "诈骗", "客服", "账号密码", "支付限额", "理赔",
        ]
        has_concrete = sum(1 for token in concrete_tokens if token in desc) >= 2
        is_abstract = any(phrase in desc for phrase in abstract_phrases)
        return has_concrete and not (is_abstract and len(desc) < 40)

    def _recent_scenario_keys(self, limit: int = 12) -> set[str]:
        events = self.state.life_events[-limit:] if self.state.life_events else []
        keys: set[str] = set()
        for event in events:
            key = getattr(event, "scenario_key", "") or self._infer_scenario_key(getattr(event, "description", ""))
            if key and key != "unknown":
                keys.add(key)
        return keys

    def _forbidden_daily_scenario_keys(self) -> set[str]:
        keys = self._recent_scenario_keys(limit=getattr(self.config, "llm_forbidden_scenario_limit", 12))
        for item in self._daily_scenario_catalog():
            if self._is_daily_scenario_blocked(item["key"]):
                keys.add(item["key"])
        return keys

    def _is_daily_scenario_blocked(self, scenario_key: str) -> bool:
        if not scenario_key or scenario_key == "unknown":
            return False
        if scenario_key in set(getattr(self.config, "disabled_scenarios", []) or []):
            return True
        return self.state.is_scenario_on_cooldown(
            scenario_key,
            self.state.current_date,
            getattr(self.config, "scenario_cooldown_days", 14),
            major=False,
        )

    def _is_major_scenario_blocked(self, scenario_key: str) -> bool:
        if not scenario_key or scenario_key == "major_unknown":
            return False
        return self.state.is_scenario_on_cooldown(
            scenario_key,
            self.state.current_date,
            getattr(self.config, "major_scenario_cooldown_days", 180),
            major=True,
        )

    def _scenario_guidance(self, forbidden: set[str]) -> str:
        available = [
            f"{item['key']}({item.get('category', 'daily')})"
            for item in self._daily_scenario_catalog()
            if item["key"] not in forbidden
        ]
        return ", ".join(available[:20]) if available else "无可用场景，应该输出 []"

    def _scenario_category_for_key(self, scenario_key: str) -> str:
        for item in self._daily_scenario_catalog():
            if item["key"] == scenario_key:
                return item.get("category", "daily")
        return "daily"

    def _activity_summary_for_event(self, event: "LifeEvent") -> str:
        key = event.scenario_key or self._infer_scenario_key(event.description)
        summary_map = {
            "commute_delay": "通勤后有些疲惫",
            "lunch_discovery": "吃到一顿让人放松的饭",
            "office_gossip": "和同事有了轻松交流",
            "delivery_mixup": "处理了一个生活小插曲",
            "dessert_queue": "下班路上买了点甜食",
            "night_walk": "晚上运动后状态回稳",
            "work_review": "处理工作反馈后有些紧绷",
            "home_repair": "解决了家里的小麻烦",
            "friend_message": "被朋友勾起一些回忆",
            "family_call": "和家里聊了会儿天",
            "rainy_day": "被天气影响了出行节奏",
            "weekend_cleanup": "把生活空间整理了一下",
            "skill_learning": "学了点新东西",
            "sleep_trouble": "睡眠让状态有些波动",
            "small_purchase": "买到一个顺手的小物件",
        }
        return summary_map.get(key, "经历了一件具体的小事")

    def _is_recent_duplicate_event(self, description: str, limit: int = 20) -> bool:
        normalized = self._normalize_event_text(description)
        if not normalized:
            return False
        current_key = self._infer_scenario_key(description)
        if self._is_daily_scenario_blocked(current_key):
            return True
        events = self.state.life_events[-limit:] if self.state.life_events else []
        for event in events:
            old_desc = getattr(event, "description", "")
            old_normalized = self._normalize_event_text(old_desc)
            if not old_normalized:
                continue

            if normalized == old_normalized:
                return True
            old_key = getattr(event, "scenario_key", "") or self._infer_scenario_key(old_desc)
            if current_key != "unknown" and current_key == old_key:
                ratio = SequenceMatcher(None, normalized, old_normalized).ratio()
                if ratio >= 0.60:
                    return True
            if len(normalized) >= 16 and (normalized in old_normalized or old_normalized in normalized):
                return True
            ratio = SequenceMatcher(None, normalized, old_normalized).ratio()
            if ratio >= 0.82:
                return True
        return False

    def _should_check_major_for_current_date(self) -> bool:
        """人生大事概率检查按 Bot 日期去重：同一天只检查一次。"""
        current_date = self.state.current_date
        if not current_date:
            return True
        if self.state.last_major_probability_check_date == current_date:
            return False
        self.state.last_major_probability_check_date = current_date
        return True

    def _maybe_generate_probability_major_event(self) -> Optional["MajorLifeEvent"]:
        unexpected_event = self._maybe_generate_unexpected_major_event()
        if unexpected_event:
            return unexpected_event

        probability = min(1.0, max(0.0, self.config.major_event_fixed_probability))
        if probability <= 0:
            return None
        if random.random() >= probability:
            return None
        event = self._build_probability_major_event()
        if not event:
            logger.info("[LifeEngine] 固定概率触发但无可用人生大事场景，跳过")
            return None
        logger.info(
            "[LifeEngine] 固定概率触发生命大事: probability=%.3f, description=%s",
            probability,
            event.description,
        )
        return event

    def _maybe_generate_unexpected_major_event(self) -> Optional["MajorLifeEvent"]:
        probability = min(1.0, max(0.0, getattr(self.config, "unexpected_event_probability", 0.01)))
        if probability <= 0:
            return None
        if self._is_unexpected_event_on_cooldown():
            return None
        if random.random() >= probability:
            return None

        event = self._build_unexpected_major_event()
        if event:
            logger.info(
                "[LifeEngine] 低概率意外事件触发: probability=%.4f, description=%s",
                probability,
                event.description,
            )
        return event

    def _is_unexpected_event_on_cooldown(self) -> bool:
        cooldown_days = max(0, int(getattr(self.config, "unexpected_event_cooldown_days", 365)))
        if cooldown_days <= 0:
            return False
        current_date = self.state.current_date
        last_date = self.state.last_unexpected_event_date
        if not current_date or not last_date:
            return False
        try:
            current = datetime.strptime(current_date, "%Y-%m-%d").date()
            last = datetime.strptime(last_date, "%Y-%m-%d").date()
            return (current - last).days < cooldown_days
        except ValueError:
            return False

    def _mark_unexpected_event_if_needed(self, event: "MajorLifeEvent"):
        if event.source == "unexpected_probability" or str(event.scenario_key).startswith("unexpected_"):
            self.state.last_unexpected_event_date = self.state.current_date

    def _build_unexpected_major_event(self) -> Optional["MajorLifeEvent"]:
        from .life_state import MajorLifeEvent

        available = [
            item for item in self._unexpected_major_scenario_catalog()
            if not self._is_major_scenario_blocked(item["key"])
        ]
        if not available:
            return None

        selected = random.choice(available)
        description = self._render_major_scenario_description(selected)
        return MajorLifeEvent(
            description=description,
            mood_before=self.state.bot_mood or "平静",
            mood_after=selected["mood_after"],
            importance=selected.get("importance", 9.2),
            shareable=selected.get("shareable", True),
            topic_prompt=selected.get("topic_prompt", f"最近发生了一件很突然的事：{description}"),
            mood_tags=selected["tags"] + ["低概率意外"],
            related_to_user=False,
            context_bits=len(description),
            scenario_key=selected["key"],
            scenario_category="unexpected",
            source="unexpected_probability",
        )

    def _build_probability_major_event(self) -> Optional["MajorLifeEvent"]:
        from .life_state import MajorLifeEvent

        mood_before = self.state.bot_mood or "平静"
        available = [
            item for item in self._major_scenario_catalog()
            if not self._is_major_scenario_blocked(item["key"])
        ]
        if not available:
            return None
        selected = random.choice(available)
        description = self._render_major_scenario_description(selected)
        return MajorLifeEvent(
            description=description,
            mood_before=mood_before,
            mood_after=selected["mood_after"],
            importance=selected.get("importance", 8.6),
            shareable=True,
            topic_prompt=selected.get("topic_prompt", f"最近发生了一件挺重要的事：{description}"),
            mood_tags=selected["tags"] + ["固定概率触发"],
            related_to_user=False,
            context_bits=len(description),
            scenario_key=selected["key"],
            scenario_category="major",
            source="fixed_probability",
        )

    def _major_scenario_catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "key": "career_offer_signed",
                "templates": [
                    "{date} 晚上收到{company_team}发来的正式邮件，确认下月转到{occupation}相关的新项目组，合同附件里写明了新的职责和试用目标。",
                    "{date} 和直属负责人谈完后，正式签下{company_team}的内部转岗确认单，接下来三个月要独立负责{project_name}。",
                ],
                "mood_after": "坚定",
                "tags": ["职业", "转岗", "合同"],
                "topic_prompt": "我最近工作上真的定下来一件大事。",
            },
            {
                "key": "portfolio_project_launched",
                "templates": [
                    "{date} 主导的{project_name}终于上线，数据看板第一小时就有真实用户反馈，她把复盘文档命名为“从0到1的第一场硬仗”。",
                    "{date} 把拖了半年的作品集项目正式发布到公开主页，第一封合作邀请邮件在晚上十一点进了邮箱。",
                ],
                "mood_after": "有成就感",
                "tags": ["作品", "上线", "成就"],
                "topic_prompt": "我做了很久的东西终于上线了。",
            },
            {
                "key": "promotion_or_role_change",
                "templates": [
                    "{date} 在周会上被任命为{project_name}的设计负责人，之后要带两名新人推进版本评审。",
                    "{date} 负责人把季度关键项目交到她手里，并在会议纪要里明确写下“由她主导最终设计决策”。",
                ],
                "mood_after": "紧张但兴奋",
                "tags": ["职责", "晋升", "项目"],
                "topic_prompt": "我突然多了一份真正要扛起来的责任。",
            },
            {
                "key": "major_project_failure",
                "templates": [
                    "{date} 下午的评审会上，准备三周的{project_name}方案被负责人当场否决，她会后和导师复盘到晚上十点，决定重做信息架构。",
                    "{date} 客户把{project_name}的第一版方案退回，邮件里逐条标出十七处问题，她第一次认真写下失败复盘清单。",
                ],
                "mood_after": "清醒",
                "tags": ["失败", "复盘", "成长"],
                "topic_prompt": "今天有个项目被打回来，但我觉得这次挺关键的。",
            },
            {
                "key": "moving_home_decision",
                "templates": [
                    "{date} 傍晚签下离公司三站地铁的新租约，拿到钥匙后决定周末搬家，把通勤时间压到半小时以内。",
                    "{date} 看完第五套房后终于交了押金，新住处有一扇朝南的窗，她当晚列了第一张搬家清单。",
                ],
                "mood_after": "安定",
                "tags": ["搬家", "独立", "生活"],
                "topic_prompt": "我可能要换一个新的生活节奏了。",
            },
            {
                "key": "health_turning_point",
                "templates": [
                    "{date} 体检报告提示睡眠和胃部指标异常，她预约了周五复查，并把连续熬夜的项目节奏正式叫停。",
                    "{date} 在医院复查完后，医生把作息问题讲得很直接，她回家就删掉了三个深夜加班提醒。",
                ],
                "mood_after": "警醒",
                "tags": ["健康", "体检", "调整"],
                "topic_prompt": "我这次真的要认真管一下身体了。",
            },
            {
                "key": "family_responsibility",
                "templates": [
                    "{date} 家里来电话说父亲复查需要人陪，她订了周末高铁票，开始重新安排工作和家庭责任。",
                    "{date} 陪母亲在医院等检查结果等到傍晚，她第一次认真把家里的保险单和紧急联系人整理成表格。",
                ],
                "mood_after": "沉静",
                "tags": ["家人", "责任", "医院"],
                "topic_prompt": "家里发生了一件让我突然成熟一点的事。",
            },
            {
                "key": "public_recognition",
                "templates": [
                    "{date} 在公司内部分享会上讲完{project_name}复盘，设计总监当场邀请她把方法沉淀成团队规范。",
                    "{date} 她的{project_name}复盘被放进部门周报首页，下午连续收到三个同事来约时间请教。",
                ],
                "mood_after": "被看见",
                "tags": ["认可", "公开分享", "职业"],
                "topic_prompt": "今天有种努力终于被看见的感觉。",
            },
            {
                "key": "financial_independence",
                "templates": [
                    "{date} 发工资后第一次把六个月生活费单独存进备用账户，决定以后不再为了房租和家里支出临时透支。",
                    "{date} 和银行客服确认完自动转存计划后，她给自己建了第一份年度预算表，把旅行、学习和家庭支出分开管理。",
                ],
                "mood_after": "踏实",
                "tags": ["财务", "独立", "规划"],
                "topic_prompt": "我今天做了一个跟安全感有关的决定。",
            },
            {
                "key": "relationship_boundary_shift",
                "templates": [
                    "{date} 和一位消耗很久的朋友当面谈清边界，对方道歉后约定减少情绪倾倒，她回家后删掉了那段反复修改的长消息。",
                    "{date} 在咖啡店和老朋友把误会摊开说清，最后互相道歉，并约定以后不再用冷处理解决问题。",
                ],
                "mood_after": "平静",
                "tags": ["关系", "边界", "和解"],
                "topic_prompt": "我今天把一段关系里的话说清楚了。",
            },
        ]

    def _unexpected_major_scenario_catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "key": "unexpected_self_accident",
                "templates": [
                    "{date} 下班路上在地铁口台阶踩空扭伤脚踝，急诊拍片后确认没有骨折，但医生要求她一周后复查并暂停所有晚间运动。",
                    "{date} 骑车去办事时被突然打开的车门吓到摔倒，膝盖包着绷带回家，第二天还要去社区医院换药。",
                ],
                "mood_after": "后怕",
                "tags": ["意外", "受伤", "复查"],
                "topic_prompt": "我这两天遇到一点意外，整个人都有点后怕。",
                "importance": 9.0,
            },
            {
                "key": "unexpected_family_accident",
                "templates": [
                    "{date} 家里电话打来说{family_member}在楼下摔倒需要急诊，她临时改签高铁回去，整晚守在医院等检查结果。",
                    "{date} {family_member}突发不适被送到医院住院观察，她第一次在护士站签下陪护登记表，并开始重新安排接下来一周的工作。",
                ],
                "mood_after": "担心",
                "tags": ["家人", "意外", "医院"],
                "topic_prompt": "家里突然出了点事，我这几天心里一直绷着。",
                "importance": 9.5,
            },
            {
                "key": "unexpected_natural_disaster",
                "templates": [
                    "{date} 傍晚暴雨把小区地下车库淹了，物业临时通知断电排水，她和邻居一起把重要证件和电脑搬到高处。",
                    "{date} 台风预警升级后，公司通知远程办公，她半夜听着窗外警报声，把应急包、充电宝和家里人的联系方式重新整理了一遍。",
                ],
                "mood_after": "紧张",
                "tags": ["天灾", "应急", "生活中断"],
                "topic_prompt": "这次天气突发状况让我有点被吓到。",
                "importance": 9.2,
            },
            {
                "key": "unexpected_public_incident",
                "templates": [
                    "{date} 公司楼下商铺突发火警，消防车封住路口，她跟同事在警戒线外等了两个小时才被允许回去取电脑。",
                    "{date} 通勤地铁临时封站疏散，站台广播一直重复安全提示，她错过上午评审，只能在路边用手机临时开会。",
                ],
                "mood_after": "混乱",
                "tags": ["突发事件", "疏散", "通勤"],
                "topic_prompt": "今天路上发生了很突然的公共事件。",
                "importance": 8.8,
            },
            {
                "key": "unexpected_document_loss",
                "templates": [
                    "{date} 去办手续时发现身份证和银行卡都不见了，她在派出所挂失到晚上九点，回家后把所有自动扣费账户重新核对了一遍。",
                    "{date} 出差前一天丢了证件袋，里面有身份证和门禁卡，她跑完派出所和物业补办流程后，第一次认真做了证件备份清单。",
                ],
                "mood_after": "懊恼",
                "tags": ["证件", "挂失", "风险"],
                "topic_prompt": "我今天因为证件的事情折腾到很晚。",
                "importance": 8.7,
            },
            {
                "key": "unexpected_home_emergency",
                "templates": [
                    "{date} 半夜厨房水管突然漏水，物业和维修师傅赶到时地板已经泡了一片，她一直拖到凌晨才把插座和电器检查完。",
                    "{date} 家里突然断电，电工检查后发现是老旧线路问题，她当天就决定更换电箱并临时住到朋友家。",
                ],
                "mood_after": "疲惫",
                "tags": ["居住", "抢修", "意外"],
                "topic_prompt": "家里突然出问题，折腾得我有点缓不过来。",
                "importance": 8.9,
            },
            {
                "key": "unexpected_travel_disruption",
                "templates": [
                    "{date} 去外地参加重要面试的高铁因暴雨停运，她在候车厅改签到凌晨，最后只能把面试改成临时视频会议。",
                    "{date} 航班临时取消导致她错过第二天上午的项目汇报，她在机场酒店写完补救方案并给团队发了长邮件。",
                ],
                "mood_after": "焦灼",
                "tags": ["出行", "延误", "补救"],
                "topic_prompt": "今天出行完全被突发情况打乱了。",
                "importance": 8.8,
            },
            {
                "key": "unexpected_scam_near_miss",
                "templates": [
                    "{date} 接到冒充平台客服的诈骗电话，差点按对方要求转账，反应过来后立刻报警并冻结银行卡到第二天早上。",
                    "{date} 一个伪装成快递理赔的链接套走了部分信息，她在派出所做完记录后，把所有账号密码和支付限额重新改了一遍。",
                ],
                "mood_after": "警惕",
                "tags": ["人祸", "诈骗", "报警"],
                "topic_prompt": "我今天差点被诈骗，后怕得不行。",
                "importance": 9.0,
            },
        ]

    def _render_major_scenario_description(self, scenario: dict[str, Any]) -> str:
        template = random.choice(scenario.get("templates") or ["{date} 发生了一件具体的人生大事。"])
        values = {
            "date": self.state.current_date or "近期",
            "bot_name": getattr(self, "bot_name", self.bot_id),
            "occupation": getattr(self, "occupation", "工作"),
            "age": self._calc_real_age(),
            "life_stage": self._calc_life_stage(self._calc_real_age()),
            "company_team": random.choice(["增长产品组", "核心体验组", "商业化团队", "用户研究小组"]),
            "project_name": random.choice(["新版 onboarding", "会员中心改版", "数据可视化工具", "移动端工作台"]),
            "family_member": random.choice(["父亲", "母亲", "外婆", "哥哥"]),
        }
        return template.format_map(_SafeFormatDict(values))

    async def _apply_major_event(self, event: "MajorLifeEvent"):
        """应用人生大事：更新 persona 文件"""
        updater = PersonaUpdater(self)
        await updater.update_all(event)

    def prune_events(self):
        """清理低重要性事件"""
        self.state.prune_events(self.config.max_events, self.config.max_context_bits)

    def get_status(self) -> dict:
        """获取当前状态"""
        life_events = self.state.life_events
        major_events = self.state.major_life_events
        real_age = self._calc_real_age()
        return {
            "bot_mood": self.state.bot_mood,
            "bot_current_activity": self.state.bot_current_activity,
            "bot_age_days": self.state.bot_age_days,
            "bot_real_age": real_age,
            "initial_age": self.state.initial_age,
            "birth_date": self.state.birth_date,
            "current_season": self.state.current_season,
            "current_month": self.state.current_month,
            "current_date": self.state.current_date,
            "day_of_week": self.state.day_of_week,
            "year": self.state.year,
            "is_weekend": self.state.is_weekend,
            "life_stage": self._calc_life_stage(real_age),
            "life_events_count": len(life_events),
            "major_events_count": len(major_events),
            "recent_life_events": [self._event_status_item(e) for e in life_events[-5:]],
            "recent_major_life_events": [self._event_status_item(e) for e in major_events[-5:]],
            "last_daily_tick": self.state.last_daily_tick.isoformat() if self.state.last_daily_tick else None,
            "last_major_tick": self.state.last_major_tick.isoformat() if self.state.last_major_tick else None,
        }

    def _event_status_item(self, event: "LifeEvent") -> dict:
        return {
            "timestamp": event.timestamp,
            "description": event.description,
            "importance": event.importance,
            "scenario_key": event.scenario_key,
            "source": event.source,
        }
