"""
语义记忆：SQLite，存储用户事实画像
CRUD + LLM 抽取新事实，支持字数限制和会话隔离
"""

import aiosqlite
import asyncio
import json
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SemanticStore:
    """
    语义记忆存储

    表结构：
    - user_facts: 用户事实 (key, value, updated_at, session_id)

    抽取策略：
    每次回复后异步调用 LLM，判断是否有新事实透露。
    有则写入/更新，无则跳过。

    会话隔离：
    - session_id 不为空时写入该会话的记忆
    - 跨会话召回时读全部会话的事实
    - 私密信息可按 session_id 删除
    """

    # 抽取用户事实的 prompt
    EXTRACT_PROMPT = """对话：
用户：{user_input}
助手：{bot_output}

请判断这段对话是否透露了用户的新事实（如职业、爱好、年龄、姓名、城市、性格偏好等）。
有则输出 JSON：{{"key": "事实key", "value": "事实value"}}
无则输出：NO_FACT
只输出 JSON 或 NO_FACT，不要解释。"""

    # 抽取关系变化的 prompt（识别对话中用户与bot关系是否有进展）
    # 抽取关系的 prompt（结合最近 3 轮上下文判断整体氛围）
    EXTRACT_RELATION_PROMPT = """【最近几轮对话上下文】
{conversation_context}

【当前这轮对话】
用户：{user_input}
助手：{bot_output}

请结合上下文，判断这段对话是否让 bot（苏晴/阿月）对用户的感情/关系发生了变化。
判断依据：
- 需要结合上下文：如果用户连续几轮都在调侃/撩 bot，可能关系已升级
- 如果本轮是吵架后和解，或用户连续几轮关心 → 关系可能升级
- 如果本轮是单方面的，用户一直在吐槽/冷漠 → 关系可能降级
- 如果前后语气反差大（如用户先撩后冷）→ 需要综合判断

可能的情感变化：
- "朋友" → "暧昧中" → "恋人"（逐步升级）
- "恋人" → "朋友"（分手/吵架导致）
- "暧昧中" → "朋友"（关系倒退）

有变化则输出 JSON：{{"key": "relationship_to_user", "value": "新关系"}}
无变化或无判断把握则输出：NO_CHANGE
只输出 JSON 或 NO_CHANGE，不要解释。"""

    # 抽取态度变化的 prompt（结合最近 3 轮上下文判断整体语气）
    # attitude_score 范围 -10（极度厌恶）到 +10（非常喜欢），初始约 0
    # LLM 输出本轮变化量（-5 到 +5），而非绝对值
    EXTRACT_ATTITUDE_PROMPT = """对话上下文：
{conversation_context}

当前这轮：
用户：{user_input}
助手：{bot_output}

请输出一个数字（-5 到 +5），表示本轮对话后 bot 对用户好感度的变化：
-5 大幅下降（恶语相向、严重伤害）
-3 有所下降（冷淡、敷衍）
-1 略微下降（略显不耐烦）
0 持平（普通闲聊）
+1 略微上升（有一点小感动）
+3 有所上升（被关心、被安慰）
+5 大幅上升（被告白、重大感动）

只输出数字，不要任何解释。"""

    # 抽取是否值得写入 key_moments 的 prompt（结合最近 3 轮上下文）
    EXTRACT_KEY_MOMENT_PROMPT = """【最近几轮对话上下文】
{conversation_context}

【当前这轮对话】
用户：{user_input}
助手：{bot_output}

这是一段对话情景。请判断这是否是一个值得永久记住的关键时刻：
- 两人吵架/和解
- bot 向用户敞开心扉
- 用户做了让 bot 特别感动的事
- 两人关系发生质变（确认恋爱、分手等）
- 第一次一起做某事（旅行、送礼等）

注意：需要结合上下文判断整体氛围：
- 用户连续几轮都在损 bot，突然本轮语气稍好 → 可能只是缓和，不是关键进展
- 用户表白后 bot 接受了，即使本轮只是简单回应 → 本身是关键进展
- 吵架后用户道歉+bot原谅 → 整体是关键进展（和好）

是关键时刻则输出 JSON：{{"key": "key_moment", "value": "关键时刻描述（30-60字）"}}
不是特别重要则输出：NO_MOMENT
只输出 JSON 或 NO_MOMENT，不要解释。"""

    def __init__(self, db_path: str, max_chars: int = 4400,
                 persona_backstory_path: str = None):
        self.db_path = db_path
        self.max_chars = max_chars  # 单条事实的最大字符数（可配置）
        self._summarizer: Optional[object] = None
        self._persona_backstory_path = persona_backstory_path

    def set_summarizer(self, summarizer):
        """注入 LLM 适配器（用于事实抽取）"""
        self._summarizer = summarizer

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_facts (
                    key TEXT,
                    session_id TEXT,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (key, session_id)
                )
            """)
            # 迁移旧数据库：若无 session_id 列则添加
            cursor = await db.execute("PRAGMA table_info(user_facts)")
            columns = [row[1] async for row in cursor]
            if "session_id" not in columns:
                await db.execute("ALTER TABLE user_facts ADD COLUMN session_id TEXT")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_facts_session ON user_facts(session_id)")
            await db.commit()

    def _trim_value(self, value: str) -> str:
        """超长 value 截断，超出 max_chars 直接丢弃（占位）"""
        if len(value) > self.max_chars:
            # 保留前缀 + 省略号
            return value[:self.max_chars - 3] + "..."
        return value

    async def set_fact(self, key: str, value: str,
                       session_id: Optional[str] = None):
        """
        写入/更新单个事实（自动截断超长 value）。

        注意：SQLite 中 NULL 不等于 NULL，因此 session_id=None 的多条记录会共存。
        对于 attitude_score 等跨会话共享的事实，写入时应确保先删除旧记录。
        """
        value = self._trim_value(value)
        async with aiosqlite.connect(self.db_path) as db:
            # SQLite 中 NULL 不等于 NULL，INSERT OR REPLACE 会创建多条 NULL 记录
            # 因此对于 session_id=None 的写入，先删除旧记录再插入
            if session_id is None:
                await db.execute(
                    "DELETE FROM user_facts WHERE key = ? AND session_id IS NULL",
                    (key,)
                )
            await db.execute("""
                INSERT OR REPLACE INTO user_facts (key, value, updated_at, session_id)
                VALUES (?, ?, ?, ?)
            """, (key, value, datetime.now().isoformat(), session_id))
            await db.commit()

    async def get_fact(self, key: str, session_id: Optional[str] = None) -> Optional[str]:
        """读取单个事实"""
        async with aiosqlite.connect(self.db_path) as db:
            if session_id:
                cursor = await db.execute(
                    "SELECT value FROM user_facts WHERE key = ? AND session_id = ?",
                    (key, session_id)
                )
            else:
                cursor = await db.execute(
                    "SELECT value FROM user_facts WHERE key = ?", (key,)
                )
            row = await cursor.fetchone()
            return row[0] if row else None

    async def get_all_facts(self, session_id: Optional[str] = None) -> dict[str, str]:
        """
        读取全部或指定会话的事实。
        不传 session_id 时读全部（跨会话聚合）。
        """
        async with aiosqlite.connect(self.db_path) as db:
            if session_id:
                cursor = await db.execute(
                    "SELECT key, value FROM user_facts WHERE session_id = ? ORDER BY updated_at DESC",
                    (session_id,)
                )
            else:
                cursor = await db.execute(
                    "SELECT key, value FROM user_facts ORDER BY updated_at DESC"
                )
            rows = await cursor.fetchall()
            result = {key: value for key, value in rows}
            logger.info(f"[Semantic]  get_all_facts(session_id={session_id!r}): {result}")
            return result

    async def delete_fact(self, key: str, session_id: Optional[str] = None):
        """删除指定事实（不传 session_id 时删除所有匹配 key 的事实）"""
        async with aiosqlite.connect(self.db_path) as db:
            if session_id:
                await db.execute(
                    "DELETE FROM user_facts WHERE key = ? AND session_id = ?",
                    (key, session_id)
                )
            else:
                await db.execute("DELETE FROM user_facts WHERE key = ?", (key,))
            await db.commit()

    async def extract_and_store(self, user_input: str, bot_output: str,
                               session_id: Optional[str] = None,
                               model: Optional[object] = None,
                               conversation_context: str = "") -> Optional[dict]:
        """
        异步抽取本轮对话中的新事实，有则写入 SQLite。
        conversation_context: 最近 3 轮对话的原始文本，用于辅助判断语气/氛围。
        返回写入的事实 {"key": ..., "value": ...} 或 None。
        """
        logger.info(f"[Semantic]  extract_and_store 开始 | ctx_len={len(conversation_context)} | user={user_input[:30]!r}")
        summarizer = model or self._summarizer
        if not summarizer:
            logger.info(f"[Semantic]  无 summarizer，跳过")
            return None

        # attitude 单独抽取（prompt 要求输出纯数字，不再走 JSON 解析）
        async def try_extract_attitude(prompt: str) -> Optional[dict]:
            try:
                response = await summarizer.chat(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt=None
                )
                if isinstance(response, dict):
                    content = response.get("content") or response.get("reasoning_content") or ""
                elif isinstance(response, str):
                    content = response
                else:
                    content = str(response)
                content = content.strip()
                logger.info(f"[Semantic] [attitude] LLM原始回复: {content!r}")
                # MiniMax-M2.7 的 content 包含完整推理过程，取最后一个数字才是结论
                all_nums = re.findall(r'-?\d+', content)
                if all_nums:
                    delta = int(all_nums[-1])  # 最后一个匹配是推理后的最终结论
                    delta = max(-5, min(5, delta))  # 限制在 ±5
                    logger.info(f"[Semantic] [attitude] 解析结果: delta={delta} (from {all_nums})")
                    return {"key": "attitude_score", "value": str(delta)}
                logger.info(f"[Semantic] [attitude] 解析结果: 无数字")
                return None
            except Exception as e:
                logger.info(f"[Semantic] [attitude] 抽取异常: {e}")
                return None

        # fact/relation/key_moment 用 JSON 解析
        async def try_extract_json(prompt: str, label: str) -> Optional[dict]:
            try:
                response = await summarizer.chat(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt=None
                )
                if isinstance(response, dict):
                    content = response.get("content") or response.get("reasoning_content") or ""
                elif isinstance(response, str):
                    content = response
                else:
                    content = str(response)
                content = content.strip()
                logger.info(f"[Semantic] [{label}] LLM原始回复: {content[:200]!r}")
                facts = self._parse_facts(content)
                logger.info(f"[Semantic] [{label}] 解析结果: {facts}")
                return facts[0] if facts else None
            except Exception as e:
                logger.info(f"[Semantic] [{label}] 抽取异常: {e}")
                return None

        # 并行执行所有抽取
        fact_task = try_extract_json(self.EXTRACT_PROMPT.format(
            user_input=user_input, bot_output=bot_output), "fact")
        rel_task = try_extract_json(self.EXTRACT_RELATION_PROMPT.format(
            conversation_context=conversation_context,
            user_input=user_input, bot_output=bot_output), "relation")
        att_task = try_extract_attitude(self.EXTRACT_ATTITUDE_PROMPT.format(
            conversation_context=conversation_context,
            user_input=user_input, bot_output=bot_output))
        moment_task = try_extract_json(self.EXTRACT_KEY_MOMENT_PROMPT.format(
            conversation_context=conversation_context,
            user_input=user_input, bot_output=bot_output), "key_moment")

        results = await asyncio.gather(fact_task, rel_task, att_task, moment_task)

        written = []
        for res in results:
            if res and res.get("key") and res.get("value"):
                key = res["key"]
                value = res["value"]

                # attitude_score 用增量叠加，而不是覆盖
                if key == "attitude_score":
                    delta = self._parse_attitude_delta(value)
                    if delta != 0:
                        # attitude_score 跨会话共享，不传 session_id
                        await self._apply_attitude_delta(delta, session_id=None)
                        written.append({"key": key, "value": str(delta)})
                        logger.info(f"[Semantic]  attitude_score {delta:+d}")
                    # 跳过 set_fact，由 _apply_attitude_delta 处理
                    continue

                # 其余类型直接写入
                await self.set_fact(key, str(value), session_id=session_id)
                written.append(res)
                logger.info(f"[Semantic]  写入记忆: {res}")

                # key_moment 追加到人格文件（去重后才写）
                if key == "key_moment":
                    await self._append_key_moment(value)
                # relationship_to_user 变化时更新人格文件
                elif key == "relationship_to_user":
                    await self._update_relationship(value)

        return written[0] if written else None

    def _parse_facts(self, text: str) -> list[dict]:
        """
        从 LLM 输出中解析 JSON 事实。

        支持两种格式：
        1. {"key": "事实key", "value": "事实value"}         — 单条标准格式
        2. {"姓名": "小明", "职业": "建筑师", ...}          — 平面 KV 格式

        返回所有解析到的事实列表（自动处理多行 JSON）。
        """
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*", "", text)
        text = text.strip()

        if text == "NO_FACT" or not text:
            return []

        facts = []
        seen_keys = set()  # 用于去重，同一 key 只保留第一个值

        # 按行处理，支持多行 JSON（每行一个 JSON 对象）
        for line in text.split('\n'):
            line = line.strip()
            if not line or line == "NO_FACT":
                continue

            try:
                data = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue

            # 格式 1：标准 {"key": ..., "value": ...}
            if isinstance(data, dict) and "key" in data and "value" in data:
                key = data["key"].strip()
                value = str(data["value"]).strip()
                if key and value and len(key) < 50 and len(value) < 500 and key not in seen_keys:
                    facts.append({"key": key, "value": value})
                    seen_keys.add(key)
                continue

            # 格式 2：平面 KV {"姓名": "小明", "职业": "建筑师", ...}
            if isinstance(data, dict):
                for k, v in data.items():
                    k = k.strip()
                    v = str(v).strip()
                    if k and v and len(k) < 50 and len(v) < 500 and k not in seen_keys:
                        facts.append({"key": k, "value": v})
                        seen_keys.add(k)

        return facts

    async def get_fact_count(self, session_id: Optional[str] = None) -> int:
        """返回当前事实数量"""
        async with aiosqlite.connect(self.db_path) as db:
            if session_id:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM user_facts WHERE session_id = ?", (session_id,)
                )
            else:
                cursor = await db.execute("SELECT COUNT(*) FROM user_facts")
            row = await cursor.fetchone()
            return row[0] if row else 0

    # ── 态度分增量处理 ─────────────────────────────────────────

    def _parse_attitude_delta(self, value) -> int:
        """从 LLM 输出的 attitude_score 解析出本轮变化量"""
        try:
            num = int(str(value).strip())
            return max(-5, min(5, num))  # 限制单轮最大变化 ±5
        except (ValueError, TypeError):
            return 0

    async def _apply_attitude_delta(self, delta: int, session_id: Optional[str] = None):
        """
        将变化量叠加到现有 attitude_score。

        注意：attitude_score 跨会话共享，不使用 session_id 隔离。
        这样保证用户在开启新会话后，attitude_score 仍然基于历史累计值。
        """
        # attitude_score 跨会话共享，读取时不传 session_id
        current = await self.get_fact("attitude_score", session_id=None)
        try:
            current_score = int(float(current)) if current else 0
        except (ValueError, TypeError):
            current_score = 0
        new_score = max(-10, min(10, current_score + delta))
        # 写入时也不传 session_id，确保跨会话共享
        await self.set_fact("attitude_score", str(new_score), session_id=None)
        await self._update_attitude_profile(new_score)
        logger.info(f"[Semantic]  attitude_score: {current_score} {delta:+d} -> {new_score}")

    # ── 人格文件写回 ─────────────────────────────────────────

    async def _append_key_moment(self, moment: str):
        """将关键时刻追加到人格 backst"""
        if not self._persona_backstory_path:
            return
        try:
            with open(self._persona_backstory_path) as f:
                data = json.load(f)
            moments = data.get("key_moments", [])
            if moment not in moments:
                moments.append(moment)
                data["key_moments"] = moments
                with open(self._persona_backstory_path, "w") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info(f"[Semantic]  key_moment 已写回人格文件: {moment[:30]}...")
        except Exception as e:
            logger.info(f"[Semantic]  写回 key_moment 失败: {e}")

    async def _update_relationship(self, relationship: str):
        """将关系变化更新到人格 profile.json"""
        if not self._persona_backstory_path:
            return
        try:
            import os
            # persona_backstory_path = data/bots/suqing/persona/backstory.json
            # profile.json 和 backstory.json 同一目录（persona/）
            profile_path = os.path.join(os.path.dirname(self._persona_backstory_path), "profile.json")
            with open(profile_path) as f:
                data = json.load(f)
            old_rel = data.get("relationship_to_user", "")
            if old_rel != relationship:
                data["relationship_to_user"] = relationship
                with open(profile_path, "w") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info(f"[Semantic]  relationship 已更新: {old_rel} -> {relationship}")
        except Exception as e:
            logger.info(f"[Semantic]  写回 relationship 失败: {e}")

    async def _update_attitude_profile(self, new_score: int):
        """将 attitude_score 变化更新到人格 profile.json"""
        if not self._persona_backstory_path:
            return
        try:
            import os
            profile_path = os.path.join(os.path.dirname(self._persona_backstory_path), "profile.json")
            with open(profile_path) as f:
                data = json.load(f)
            data["attitude_score"] = new_score
            with open(profile_path, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"[Semantic]  attitude_score 已写回 profile.json: {new_score}")
        except Exception as e:
            logger.info(f"[Semantic]  写回 attitude_score 失败: {e}")

    async def close(self):
        pass
