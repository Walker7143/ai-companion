"""Unified vector recall index for bot memory.

Structured stores remain the source of truth. This store is a Chroma-backed
associative index that can be rebuilt from SQLite/JSON state.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class VectorMemoryDocument:
    source_type: str
    source_id: str
    text: str
    bot_id: str = ""
    user_id: str = "default_user"
    category: str = "general"
    importance: float = 0.5
    sensitivity: str = "normal"
    created_at: str | None = None
    updated_at: str | None = None
    archived: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorMemoryStore:
    """Chroma-backed associative memory index."""

    DEFAULT_ENCODER_MODEL = "all-MiniLM-L6-v2"
    COLLECTION_NAME = "unified_memory"

    def __init__(
        self,
        chroma_dir: str | Path,
        *,
        embedding_mode: str = "local",
        encoder_model: str = DEFAULT_ENCODER_MODEL,
    ):
        self.chroma_dir = Path(chroma_dir)
        self.embedding_mode = embedding_mode
        self.encoder_model = encoder_model
        self._encoder = None
        self._chroma = None
        self._collection = None

    async def init(self):
        self.chroma_dir.mkdir(parents=True, exist_ok=True)

    def enabled(self) -> bool:
        return self.embedding_mode == "local"

    def _get_chroma(self):
        if self.embedding_mode != "local":
            return None
        if self._chroma is None:
            try:
                import chromadb
                from chromadb.config import Settings

                self._chroma = chromadb.PersistentClient(
                    path=str(self.chroma_dir),
                    settings=Settings(anonymized_telemetry=False),
                )
                self._collection = self._chroma.get_or_create_collection(self.COLLECTION_NAME)
            except Exception as exc:
                logger.info("[VectorMemory] Chroma unavailable, disabling vector recall: %s", exc)
                self.embedding_mode = "none"
                return None
        return self._collection

    def _get_encoder(self):
        if self.embedding_mode != "local":
            return None
        if self._encoder is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._encoder = SentenceTransformer(self.encoder_model)
            except Exception as exc:
                logger.info("[VectorMemory] embedding model unavailable, disabling vector recall: %s", exc)
                self.embedding_mode = "none"
                return None
        return self._encoder

    def _embed(self, text: str) -> list[float] | None:
        encoder = self._get_encoder()
        if encoder is None:
            return None
        return encoder.encode(text).tolist()

    async def upsert(self, doc: VectorMemoryDocument) -> bool:
        text = _clean_text(doc.text)
        if not text:
            return False
        collection = self._get_chroma()
        if collection is None:
            return False
        embedding = self._embed(text)
        if embedding is None:
            return False

        metadata = _clean_metadata(
            {
                **(doc.metadata or {}),
                "source_type": doc.source_type,
                "source_id": doc.source_id,
                "bot_id": doc.bot_id,
                "user_id": doc.user_id,
                "category": doc.category,
                "importance": float(doc.importance or 0),
                "sensitivity": doc.sensitivity or "normal",
                "created_at": doc.created_at or "",
                "updated_at": doc.updated_at or datetime.now().isoformat(),
                "archived": bool(doc.archived),
            }
        )
        collection.upsert(
            ids=[self.document_id(doc.source_type, doc.bot_id, doc.user_id, doc.source_id)],
            documents=[text],
            embeddings=[embedding],
            metadatas=[metadata],
        )
        return True

    async def upsert_many(self, docs: list[VectorMemoryDocument]) -> int:
        count = 0
        for doc in docs:
            if await self.upsert(doc):
                count += 1
        return count

    async def delete(
        self,
        *,
        source_type: str | None = None,
        source_id: str | None = None,
        bot_id: str = "",
        user_id: str = "default_user",
    ) -> int:
        collection = self._get_chroma()
        if collection is None:
            return 0
        where: dict[str, Any] = {}
        if source_type:
            where["source_type"] = source_type
        if source_id:
            where["source_id"] = source_id
        if bot_id is not None:
            where["bot_id"] = bot_id
        if user_id is not None:
            where["user_id"] = user_id
        if not where:
            return 0
        try:
            collection.delete(where=where)
            return 1
        except Exception as exc:
            logger.info("[VectorMemory] delete failed: %s", exc)
            return 0

    def search(
        self,
        query: str,
        *,
        bot_id: str,
        user_id: str = "default_user",
        source_types: list[str] | None = None,
        limit: int = 8,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        query = str(query or "").strip()
        if not query:
            return []
        collection = self._get_chroma()
        if collection is None:
            return []
        embedding = self._embed(query)
        if embedding is None:
            return []

        where = self._where(bot_id=bot_id, user_id=user_id, source_types=source_types, include_archived=include_archived)
        try:
            result = collection.query(
                query_embeddings=[embedding],
                n_results=max(1, int(limit or 8)),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.info("[VectorMemory] search failed: %s", exc)
            return []
        return _query_result_to_items(result)

    def count(self, *, bot_id: str | None = None, user_id: str | None = None) -> int | None:
        collection = self._get_chroma()
        if collection is None:
            return None
        where = {}
        if bot_id is not None:
            where["bot_id"] = bot_id
        if user_id is not None:
            where["user_id"] = user_id
        try:
            if where:
                return len(collection.get(where=where, include=[])["ids"])
            return int(collection.count())
        except Exception:
            return None

    def close(self):
        self._encoder = None
        self._chroma = None
        self._collection = None

    @classmethod
    def document_id(cls, source_type: str, bot_id: str, user_id: str, source_id: str) -> str:
        raw = f"{source_type}:{bot_id}:{user_id}:{source_id}"
        return re.sub(r"[^A-Za-z0-9_.:-]+", "_", raw)[:240]

    def _where(
        self,
        *,
        bot_id: str,
        user_id: str,
        source_types: list[str] | None,
        include_archived: bool,
    ) -> dict[str, Any]:
        clauses: list[dict[str, Any]] = [
            {"bot_id": bot_id},
            {"user_id": user_id},
        ]
        if not include_archived:
            clauses.append({"archived": False})
        if source_types:
            clean_types = [str(item) for item in source_types if str(item).strip()]
            if len(clean_types) == 1:
                clauses.append({"source_type": clean_types[0]})
            elif clean_types:
                clauses.append({"source_type": {"$in": clean_types}})
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}


def _clean_text(text: object) -> str:
    value = str(text or "").strip()
    return re.sub(r"\s+", " ", value)


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            result[str(key)] = value
        elif isinstance(value, list):
            result[str(key)] = ", ".join(str(item) for item in value if str(item).strip())[:500]
        else:
            result[str(key)] = str(value)[:500]
    return result


def _query_result_to_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    ids = (result.get("ids") or [[]])[0] if result else []
    documents = (result.get("documents") or [[]])[0] if result else []
    metadatas = (result.get("metadatas") or [[]])[0] if result else []
    distances = (result.get("distances") or [[]])[0] if result else []

    items: list[dict[str, Any]] = []
    for index, item_id in enumerate(ids):
        metadata = metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], dict) else {}
        distance = distances[index] if index < len(distances) else None
        score = None
        if distance is not None:
            try:
                score = 1.0 / (1.0 + float(distance))
            except (TypeError, ValueError, ZeroDivisionError):
                score = None
        items.append(
            {
                "id": item_id,
                "text": documents[index] if index < len(documents) else "",
                "metadata": metadata,
                "source_type": metadata.get("source_type"),
                "source_id": metadata.get("source_id"),
                "category": metadata.get("category"),
                "importance": metadata.get("importance"),
                "sensitivity": metadata.get("sensitivity"),
                "distance": distance,
                "retrieval_score": round(score, 4) if score is not None else None,
            }
        )
    return items
