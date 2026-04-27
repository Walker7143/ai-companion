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
import re
import tempfile
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, TYPE_CHECKING

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

【输出格式】
输出一个 JSON 数组，每个元素如下：
[{{"description": "事件描述", "mood_before": "之前的心情", "mood_after": "之后的心情", "importance": 1-10, "shareable": true/false, "topic_prompt": "话题切入语", "mood_tags": ["情绪标签"], "related_to_user": false}}]

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

以下情况不要标记为人生大事：
- "喝了一杯奶茶"、"看了部电影"、"加班累了"
- 日常琐事，不影响人生轨迹

【输出格式】
输出一个 JSON 对象：
{{"is_major": true或false, "reason": "判断原因"}}

如果 is_major 为 true，添加事件信息：
{{"is_major": true, "reason": "...", "event": {{"description": "事件描述", "mood_before": "之前心情", "mood_after": "之后心情", "importance": 8-10, "mood_tags": ["情绪标签"]}}}}

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
1. **分析影响范围**：这件大事可能影响哪些文件？
2. **保持一致性**：所有文件要相互一致，不能矛盾
   - 例如：如果事件让 Bot 变得更成熟，backstory 要有对应经历
3. **不要破坏格式**：输出完整的多层 JSON
4. **简洁优先**：不要过度补充细节，保持原有风格
5. **优先级**：backstory > profile > values > speaking_style

【输出格式】
输出一个 JSON 对象，包含四个键：profile、backstory、values、speaking_style，
每个键对应更新后的完整 JSON 内容。不要省略任何字段。
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
        prompt = PERSONA_UPDATE_PROMPT.format(
            bot_name=getattr(self.life_engine, "bot_name", self.life_engine.bot_id),
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

            # 解析 JSON
            json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", response, re.DOTALL)
            if not json_match:
                logger.warning("[PersonaUpdater] 无法解析 LLM 返回的 JSON")
                return False

            updates = json.loads(json_match.group())

            # 原子写入所有文件
            self._write_all_files(persona_dir, updates)

            # 重新加载 persona loader
            if self.life_engine._persona_loader:
                self.life_engine._persona_loader.reload()

            logger.info(f"[PersonaUpdater] 人格文件已更新: {event.description}")
            return True

        except Exception as e:
            logger.error(f"[PersonaUpdater] 更新失败: {e}")
            return False

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


import os


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

        # 推进日期
        self._advance_date()

        # 检查生日
        await self._check_birthday()

        # 检查里程碑
        await self._check_milestones()

        # 生成事件
        event = await self.generate_daily_event()
        if event:
            self.state.add_event(event)
            self.state.prune_events(self.config.max_events, self.config.max_context_bits)
            logger.info(f"[LifeEngine] 生成日常事件: {event.description}")

        # Bot 年龄增长
        self.state.bot_age_days += 1
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

        # 生成事件
        event = await self.generate_major_event()
        if event:
            self.state.add_major_event(event)
            await self._apply_major_event(event)
            logger.info(f"[LifeEngine] 生成人生大事: {event.description}")

        self.state.last_major_tick = datetime.now()
        self.state.save()

        return event

    async def generate_daily_event(self) -> Optional["LifeEvent"]:
        """生成日常小事"""
        from .life_state import LifeEvent

        recent = self.state.life_events[-3:] if self.state.life_events else []
        recent_str = "\n".join([
            f"- {e.description}（{e.mood_before} → {e.mood_after}）"
            for e in recent
        ]) or "最近没有发生特别的事"

        # 构建完整上下文
        life_context = self._build_life_context()

        # 检查节假日和生日
        holiday_context, birthday_context = self._check_special_date()

        prompt = LIFE_DAILY_PROMPT.format(
            bot_name=getattr(self, "bot_name", self.bot_id),
            both_name=getattr(self, "bot_name", self.bot_id),
            age_years=self._calc_real_age(),
            occupation=getattr(self, "occupation", "未知"),
            personality_tags=self._personality_type,
            bot_mood=self.state.bot_mood,
            bot_current_activity=self.state.bot_current_activity,
            bot_age_days=self.state.bot_age_days,
            recent_events=recent_str,
            **life_context,
            holiday_context=holiday_context,
            birthday_context=birthday_context,
        )

        try:
            response = await self.model.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=None
            )

            # 解析 JSON
            json_match = re.search(r"\[[^\[\]]*(?:\{[^\[\]]*\}[^\[\]]*)*\]", response, re.DOTALL)
            if not json_match:
                return None

            events_data = json.loads(json_match.group())
            if not events_data or len(events_data) == 0:
                return None

            event_data = events_data[0]
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
            )

            # 更新 Bot 状态
            self.state.bot_mood = event.mood_after
            self.state.bot_current_activity = event.description[:20]

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
        """根据月份获取季节"""
        if self.config.season_hemisphere == "south":
            # 南半球季节相反
            month_offset = {12: "夏", 1: "夏", 2: "夏", 3: "冬", 4: "冬", 5: "冬",
                           6: "春", 7: "春", 8: "春", 9: "秋", 10: "秋", 11: "秋"}
            return month_offset.get(month, "春")

        for season, info in SEASONS.items():
            if month in info["months"]:
                return season
        return "春"

    def _calc_real_age(self) -> int:
        """计算 Bot 当前实际年龄（岁）"""
        initial_age = self.state.initial_age or getattr(self, "bot_age", 20)
        return initial_age + self.state.bot_age_days // 365

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

    def _advance_date(self):
        """推进当前日期（每次 tick_daily 调用）"""
        if not self.state.current_date:
            # 首次初始化：从 birth_date 或当前日期开始
            if self.state.birth_date:
                self.state.current_date = self.state.birth_date
            else:
                self.state.current_date = datetime.now().strftime("%Y-%m-%d")

        try:
            current = datetime.strptime(self.state.current_date, "%Y-%m-%d")
            # 根据 time_ratio 推进天数（time_ratio=1440 时每天推进1天）
            days_to_add = max(1, self.config.time_ratio // 1440) if self.config.time_ratio >= 1440 else 1
            current += timedelta(days=days_to_add)

            self.state.current_date = current.strftime("%Y-%m-%d")
            self.state.year = current.year
            self.state.day_of_week = WEEKDAYS[current.weekday()]
            self.state.is_weekend = current.weekday() >= 5

            # 更新季节
            self.state.current_month = current.month
            self.state.current_season = self._get_season(current.month)
        except Exception as e:
            logger.error(f"[LifeEngine] 日期推进失败: {e}")

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
        )

        self.state.add_major_event(event)
        await self._apply_major_event(event)
        logger.info(f"[LifeEngine] 里程碑事件: {milestone['event']} at age {milestone['age']}")

        return event

    async def generate_birthday_event(self) -> Optional["MajorLifeEvent"]:
        """生成生日事件"""
        from .life_state import MajorLifeEvent

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
        )

        self.state.add_major_event(event)
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

        prompt = LIFE_MAJOR_PROMPT.format(
            bot_name=getattr(self, "bot_name", self.bot_id),
            both_name=getattr(self, "bot_name", self.bot_id),
            age_years=age_years,
            occupation=getattr(self, "occupation", "未知"),
            personality_tags=self._personality_type,
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
            json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", response, re.DOTALL)
            if not json_match:
                return None

            data = json.loads(json_match.group())
            if not data.get("is_major", False):
                return None

            event_data = data.get("event", {})
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
            )

            return event

        except Exception as e:
            logger.error(f"[LifeEngine] 生成人生大事失败: {e}")
            return None

    async def _apply_major_event(self, event: "MajorLifeEvent"):
        """应用人生大事：更新 persona 文件"""
        updater = PersonaUpdater(self)
        await updater.update_all(event)

    def prune_events(self):
        """清理低重要性事件"""
        self.state.prune_events(self.config.max_events, self.config.max_context_bits)

    def get_status(self) -> dict:
        """获取当前状态"""
        return {
            "bot_mood": self.state.bot_mood,
            "bot_current_activity": self.state.bot_current_activity,
            "bot_age_days": self.state.bot_age_days,
            "bot_real_age": self._calc_real_age(),
            "current_season": self.state.current_season,
            "current_month": self.state.current_month,
            "current_date": self.state.current_date,
            "day_of_week": self.state.day_of_week,
            "year": self.state.year,
            "is_weekend": self.state.is_weekend,
            "life_stage": self._calc_life_stage(self._calc_real_age()),
            "life_events_count": len(self.state.life_events),
            "major_events_count": len(self.state.major_life_events),
            "last_daily_tick": self.state.last_daily_tick.isoformat() if self.state.last_daily_tick else None,
            "last_major_tick": self.state.last_major_tick.isoformat() if self.state.last_major_tick else None,
        }
