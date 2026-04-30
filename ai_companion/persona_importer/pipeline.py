from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from ai_companion.model.adapters.base import ModelAdapter
from ai_companion.utils import atomic_json_write

from .chunker import chunk_sections, select_character_chunks
from .json_utils import compact_json, extract_json_object, json_dumps
from .persona_writer import normalize_persona_payload, write_persona_files
from .reader import load_book
from .review import build_review_markdown, write_json_debug
from .runtime import AsyncRateLimiter, RunLogger
from .schema import BookChunk, CharacterTarget, ImportOptions


EXTRACT_SYSTEM_PROMPT = """你是严谨的文学角色信息抽取器。
任务：只从给定片段中抽取目标角色相关信息，用于后续改写成对话 Bot persona。
规则：
- 只能依据片段内容，不要补全片段之外的剧情。
- 可以做性格推断，但必须标注 evidence_summary 和 confidence。
- 不要复制大段原文；quote 最多 40 个中文字符，可为空。
- 输出必须是严格 JSON，不要 Markdown。
"""


MERGE_SYSTEM_PROMPT = """你是角色档案编辑器。
任务：把新增抽取结果合并进一个紧凑角色档案，为 persona 生成做准备。
规则：
- 保留重要事实、经历、性格、关系、说话风格、价值观和不确定点。
- 合并重复内容，解决明显冲突；冲突不能解决时放入 uncertainties。
- evidence_index 只保留 source/chapter/summary/confidence，不要长引文。
- 输出必须是严格 JSON，不要 Markdown。
"""


PERSONA_SYSTEM_PROMPT = """你是 AI Companion 的 persona 配置作者。
任务：根据角色档案生成可审核的 Bot persona JSON。
规则：
- 输出符合本项目 profile.json、backstory.json、values.json、speaking_style.json、conversation_style_rules.json。
- 这是“基于角色经历和性格的对话 Bot 改写”，不要复刻原文台词和长表达。
- 与用户的关系需要能用于陪伴式对话；如果书中没有用户，写成自然的初始关系设定并标注需审核。
- 不确定信息不要编成绝对事实，可在 review_notes 中说明。
- 输出必须是严格 JSON，不要 Markdown。
"""


class PersonaImportPipeline:
    def __init__(self, model: ModelAdapter | None, options: ImportOptions):
        self.model = model
        self.options = options
        self.warnings: list[str] = []
        self.logger = RunLogger(self.options.output_dir / "run.log")
        self.rate_limiter = AsyncRateLimiter(self.options.requests_per_minute)

    async def run(self) -> dict[str, Any]:
        document = load_book(self.options.book_path)
        self.logger.log(
            "import_start",
            book=str(self.options.book_path),
            output_dir=str(self.options.output_dir),
            plan_only=self.options.plan_only,
            characters=[target.to_dict() for target in self.options.characters],
        )
        chunks = chunk_sections(
            document.sections,
            chunk_chars=self.options.chunk_chars,
            overlap_chars=self.options.overlap_chars,
        )
        selected = select_character_chunks(
            chunks,
            self.options.characters,
            include_neighbors=self.options.include_neighbor_chunks,
            skip_alias_filter=self.options.skip_alias_filter,
        )
        if self.options.max_chunks is not None:
            selected = selected[: self.options.max_chunks]

        manifest = {
            "schema_version": 1,
            "draft_dir": str(self.options.output_dir),
            "created_at": self.options.created_at,
            "book": document.to_dict(),
            "characters": [target.to_dict() for target in self.options.characters],
            "chunks": {
                "total": len(chunks),
                "selected": len(selected),
                "chunk_chars": self.options.chunk_chars,
                "overlap_chars": self.options.overlap_chars,
                "include_neighbor_chunks": self.options.include_neighbor_chunks,
                "skip_alias_filter": self.options.skip_alias_filter,
                "resume": self.options.resume,
                "requests_per_minute": self.options.requests_per_minute,
                "retry_attempts": self.options.retry_attempts,
            },
            "status": "plan" if self.options.plan_only else "draft",
            "warnings": self.warnings,
        }

        self.options.output_dir.mkdir(parents=True, exist_ok=True)
        atomic_json_write(self.options.output_dir / "manifest.json", manifest)
        atomic_json_write(
            self.options.output_dir / "chunk_plan.json",
            {
                "book": document.to_dict(),
                "chunks_total": len(chunks),
                "selected_chunks": [
                    {
                        **chunk.to_dict(),
                        "targets": [target.bot_id for target in targets],
                    }
                    for chunk, targets in selected
                ],
            },
        )

        if self.options.plan_only:
            self.logger.log("plan_complete", chunks_total=len(chunks), chunks_selected=len(selected))
            return manifest
        if self.model is None:
            raise ValueError("import-book 需要可用模型；如果只想查看分块计划，请使用 --plan-only")
        if not selected:
            self.warnings.append("没有任何分块命中目标角色别名；可增加 alias 或使用 --skip-alias-filter。")
            manifest["warnings"] = self.warnings
            atomic_json_write(self.options.output_dir / "manifest.json", manifest)
            review_md = build_review_markdown(manifest, [], self.warnings)
            (self.options.output_dir / "review.md").write_text(review_md + "\n", encoding="utf-8")
            self.logger.log("import_complete", status="no_selected_chunks", warnings=self.warnings)
            return manifest

        extractions = await self._extract_all(selected)
        grouped = self._group_extractions_by_character(extractions)
        character_payloads: list[dict[str, Any]] = []

        for target in self.options.characters:
            payloads = grouped.get(target.bot_id, [])
            if not payloads:
                self.warnings.append(f"{target.name} 没有可用抽取结果。")
                self.logger.log("character_no_payloads", bot_id=target.bot_id, name=target.name)
                continue

            dossier = await self._merge_character_dossier(target, payloads)
            persona_raw = await self._generate_persona(target, dossier)
            persona = normalize_persona_payload(persona_raw, target)

            character_dir = self.options.output_dir / "characters" / target.bot_id
            persona_dir = character_dir / "persona"
            write_persona_files(persona_dir, persona)
            write_json_debug(character_dir / "dossier.json", dossier)
            write_json_debug(character_dir / "persona_raw.json", persona_raw)

            character_payloads.append({
                "target": target.to_dict(),
                "persona_dir": str(persona_dir),
                "dossier": dossier,
                "persona": persona,
            })

        manifest["warnings"] = self.warnings
        manifest["characters"] = [
            {
                **target.to_dict(),
                "draft_persona_dir": str(self.options.output_dir / "characters" / target.bot_id / "persona"),
            }
            for target in self.options.characters
        ]
        atomic_json_write(self.options.output_dir / "manifest.json", manifest)
        review_md = build_review_markdown(manifest, character_payloads, self.warnings)
        (self.options.output_dir / "review.md").write_text(review_md + "\n", encoding="utf-8")
        self.logger.log(
            "import_complete",
            status="draft",
            characters=len(character_payloads),
            warnings=self.warnings,
        )
        return manifest

    async def _extract_all(
        self,
        selected: list[tuple[BookChunk, list[CharacterTarget]]],
    ) -> list[dict[str, Any]]:
        semaphore = asyncio.Semaphore(max(1, self.options.max_concurrency))
        write_lock = asyncio.Lock()
        jsonl_path = self.options.output_dir / "extractions.jsonl"
        existing = _load_existing_extractions(jsonl_path) if self.options.resume else {}
        if jsonl_path.exists() and not self.options.resume:
            jsonl_path.unlink()
        if existing:
            await self.logger.alog("resume_loaded", completed_chunks=len(existing), path=str(jsonl_path))

        async def run_one(chunk: BookChunk, targets: list[CharacterTarget]) -> dict[str, Any]:
            if self.options.resume and chunk.chunk_id in existing:
                await self.logger.alog("chunk_skip_completed", chunk_id=chunk.chunk_id)
                return existing[chunk.chunk_id]
            async with semaphore:
                await self.logger.alog(
                    "chunk_extract_start",
                    chunk_id=chunk.chunk_id,
                    section_title=chunk.section_title,
                    targets=[target.bot_id for target in targets],
                )
                try:
                    result = await self._extract_chunk(chunk, targets)
                    await self.logger.alog("chunk_extract_success", chunk_id=chunk.chunk_id)
                except Exception as exc:
                    result = {
                        "chunk_id": chunk.chunk_id,
                        "section_title": chunk.section_title,
                        "char_range": [chunk.start_char, chunk.end_char],
                        "characters": [],
                        "error": str(exc),
                    }
                    self.warnings.append(f"{chunk.chunk_id} 抽取失败: {exc}")
                    await self.logger.alog("chunk_extract_failed", chunk_id=chunk.chunk_id, error=str(exc))
                async with write_lock:
                    with jsonl_path.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(result, ensure_ascii=False) + "\n")
                return result

        tasks = [run_one(chunk, targets) for chunk, targets in selected]
        return await asyncio.gather(*tasks)

    async def _extract_chunk(self, chunk: BookChunk, targets: list[CharacterTarget]) -> dict[str, Any]:
        target_payload = [target.to_dict() for target in targets]
        user_prompt = f"""目标角色：
{json_dumps(target_payload)}

片段元信息：
{chunk.to_prompt_header()}

片段文本：
{chunk.text}

请输出 JSON，格式：
{{
  "chunk_id": "{chunk.chunk_id}",
  "section_title": "{chunk.section_title}",
  "characters": [
    {{
      "bot_id": "目标 bot_id",
      "name": "角色名",
      "facts": [{{"claim": "...", "evidence_summary": "...", "quote": "...", "confidence": 0.0}}],
      "events": [{{"event": "...", "stage": "童年/青年/当前/未知", "evidence_summary": "...", "confidence": 0.0}}],
      "traits": [{{"trait": "...", "reasoning": "...", "evidence_summary": "...", "confidence": 0.0}}],
      "relationships": [{{"with": "...", "description": "...", "evidence_summary": "...", "confidence": 0.0}}],
      "speaking_style": [{{"observation": "...", "evidence_summary": "...", "quote": "...", "confidence": 0.0}}],
      "values_boundaries": [{{"claim": "...", "evidence_summary": "...", "confidence": 0.0}}],
      "uncertainties": ["..."]
    }}
  ]
}}"""
        data = await self._chat_json(EXTRACT_SYSTEM_PROMPT, user_prompt, temperature=0.1, max_tokens=1800)
        if not isinstance(data, dict):
            raise ValueError(f"分块抽取返回格式错误: {chunk.chunk_id}")
        data.setdefault("chunk_id", chunk.chunk_id)
        data.setdefault("section_title", chunk.section_title)
        data.setdefault("char_range", [chunk.start_char, chunk.end_char])
        return data

    def _group_extractions_by_character(self, extractions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        valid_ids = {target.bot_id for target in self.options.characters}
        for extraction in extractions:
            chunk_id = extraction.get("chunk_id", "")
            section_title = extraction.get("section_title", "")
            for item in extraction.get("characters", []) or []:
                if not isinstance(item, dict):
                    continue
                bot_id = str(item.get("bot_id") or "").strip()
                if bot_id not in valid_ids:
                    bot_id = self._resolve_character_id(item)
                if bot_id not in valid_ids:
                    continue
                enriched = dict(item)
                enriched["_source"] = {
                    "chunk_id": chunk_id,
                    "section_title": section_title,
                    "char_range": extraction.get("char_range", []),
                }
                grouped[bot_id].append(enriched)
        return grouped

    def _resolve_character_id(self, item: dict[str, Any]) -> str:
        name = str(item.get("name") or "").strip()
        for target in self.options.characters:
            if name in target.all_names:
                return target.bot_id
        return ""

    async def _merge_character_dossier(
        self,
        target: CharacterTarget,
        payloads: list[dict[str, Any]],
    ) -> dict[str, Any]:
        dossier = _empty_dossier(target)
        for batch_index, batch in enumerate(_batch_payloads(payloads, self.options.merge_batch_chars)):
            await self.logger.alog(
                "dossier_merge_start",
                bot_id=target.bot_id,
                batch_index=batch_index,
                batch_items=len(batch),
            )
            user_prompt = f"""目标角色：
{json_dumps(target.to_dict())}

当前紧凑档案：
{json_dumps(dossier)}

新增抽取结果：
{json_dumps(batch)}

请输出更新后的紧凑档案 JSON，格式：
{{
  "name": "...",
  "bot_id": "...",
  "profile_facts": [{{"claim": "...", "evidence_refs": ["..."], "confidence": 0.0}}],
  "timeline": [{{"stage": "...", "event": "...", "evidence_refs": ["..."], "confidence": 0.0}}],
  "traits": [{{"trait": "...", "description": "...", "evidence_refs": ["..."], "confidence": 0.0}}],
  "relationships": [{{"with": "...", "description": "...", "evidence_refs": ["..."], "confidence": 0.0}}],
  "speaking_style": [{{"observation": "...", "evidence_refs": ["..."], "confidence": 0.0}}],
  "values_and_boundaries": [{{"claim": "...", "evidence_refs": ["..."], "confidence": 0.0}}],
  "evidence_index": [{{"ref": "chunk_id", "chapter": "...", "summary": "...", "confidence": 0.0}}],
  "uncertainties": ["..."]
}}"""
            data = await self._chat_json(MERGE_SYSTEM_PROMPT, user_prompt, temperature=0.1, max_tokens=2600)
            if isinstance(data, dict):
                dossier = data
                dossier.setdefault("name", target.name)
                dossier.setdefault("bot_id", target.bot_id)
                await self.logger.alog("dossier_merge_success", bot_id=target.bot_id, batch_index=batch_index)
            else:
                self.warnings.append(f"{target.name} 的合并结果不是 JSON object，已跳过一个批次。")
                await self.logger.alog("dossier_merge_bad_result", bot_id=target.bot_id, batch_index=batch_index)
        return dossier

    async def _generate_persona(self, target: CharacterTarget, dossier: dict[str, Any]) -> dict[str, Any]:
        await self.logger.alog("persona_generate_start", bot_id=target.bot_id)
        user_prompt = f"""目标角色：
{json_dumps(target.to_dict())}

紧凑角色档案：
{json_dumps(dossier)}

请输出严格 JSON：
{{
  "profile.json": {{
    "id": "{target.bot_id}",
    "name": "{target.name}",
    "age": 25,
    "birth_date": null,
    "occupation": "...",
    "gender": "female/male/non_binary/unspecified",
    "personality_tags": ["..."],
    "relationship_to_user": "...",
    "appearance": "...",
    "interests": ["..."],
    "settings": {{"tone_default": "...", "emoji_usage": "从不/偶尔/经常", "response_length": "简短/中等/较长"}}
  }},
  "backstory.json": {{
    "summary": "...",
    "childhood": "...",
    "teenage": "...",
    "university": "...",
    "career": "...",
    "now": "...",
    "meeting_user": "...",
    "relationship_history": "...",
    "key_moments": ["..."]
  }},
  "values.json": {{
    "non_negotiable": ["..."],
    "soft_boundaries": [{{"topic": "...", "attitude": "...", "reason": "..."}}],
    "triggers_jealousy": ["..."],
    "deal_breakers": ["..."],
    "personality_evolution_notes": ["..."]
  }},
  "speaking_style.json": {{
    "tone": "...",
    "口头禅": ["改写后的短句，不要照搬原文"],
    "greeting_style": "...",
    "farewell_style": "...",
    "emotion_indicators": {{"happy": "...", "sad": "...", "angry": "..."}},
    "special_expressions": ["..."]
  }},
  "conversation_style_rules.json": {{
    "reply_principles": ["..."],
    "avoid_phrases": ["作为AI"],
    "avoid_patterns": ["..."],
    "natural_patterns": ["..."],
    "intent_style": {{"emotional_support": "...", "task_request": "...", "casual_chat": "..."}}
  }},
  "review_notes": ["..."]
}}"""
        data = await self._chat_json(PERSONA_SYSTEM_PROMPT, user_prompt, temperature=0.25, max_tokens=3200)
        if not isinstance(data, dict):
            raise ValueError(f"{target.name} 的 persona 生成结果不是 JSON object")
        await self.logger.alog("persona_generate_success", bot_id=target.bot_id)
        return data

    async def _chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float,
        max_tokens: int,
    ) -> Any:
        if self.model is None:
            raise ValueError("模型未初始化")
        attempts = max(1, int(self.options.retry_attempts or 1))
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            wait_seconds = await self.rate_limiter.wait()
            start = time.monotonic()
            await self.logger.alog(
                "llm_call_start",
                attempt=attempt,
                max_attempts=attempts,
                max_tokens=max_tokens,
                temperature=temperature,
                rate_limit_wait_seconds=round(wait_seconds, 3),
            )
            try:
                text = await self.model.chat(
                    [{"role": "user", "content": user_prompt}],
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                data = extract_json_object(text)
                elapsed = time.monotonic() - start
                await self.logger.alog(
                    "llm_call_success",
                    attempt=attempt,
                    elapsed_seconds=round(elapsed, 3),
                    response_chars=len(text or ""),
                )
                return data
            except Exception as exc:
                last_error = exc
                elapsed = time.monotonic() - start
                await self.logger.alog(
                    "llm_call_error",
                    attempt=attempt,
                    elapsed_seconds=round(elapsed, 3),
                    error=repr(exc),
                )
                if attempt >= attempts:
                    break
                delay = float(self.options.retry_base_delay_seconds or 0) * (2 ** (attempt - 1))
                await self.logger.alog("llm_retry_sleep", attempt=attempt, delay_seconds=round(delay, 3))
                if delay > 0:
                    await asyncio.sleep(delay)
        raise RuntimeError(f"LLM 调用失败（已重试 {attempts} 次）: {last_error}")


def _empty_dossier(target: CharacterTarget) -> dict[str, Any]:
    return {
        "name": target.name,
        "bot_id": target.bot_id,
        "aliases": target.aliases,
        "profile_facts": [],
        "timeline": [],
        "traits": [],
        "relationships": [],
        "speaking_style": [],
        "values_and_boundaries": [],
        "evidence_index": [],
        "uncertainties": [],
    }


def _batch_payloads(payloads: list[dict[str, Any]], max_chars: int) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for payload in payloads:
        size = len(compact_json(payload))
        if current and current_chars + size > max_chars:
            batches.append(current)
            current = []
            current_chars = 0
        current.append(payload)
        current_chars += size
    if current:
        batches.append(current)
    return batches


def _load_existing_extractions(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    existing: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict) or item.get("error"):
            continue
        chunk_id = str(item.get("chunk_id") or "").strip()
        if chunk_id:
            existing[chunk_id] = item
    return existing
