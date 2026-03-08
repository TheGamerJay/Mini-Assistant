"""
Embed Brain for the Mini Assistant image system.

Provides text embeddings via nomic-embed-text and a local SQLite store for
semantic memory over past routing decisions.
"""

import asyncio
import json
import logging
import math
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# SQLite database stored next to this file so it survives across runs
_DB_PATH = Path(__file__).parent.parent / "data" / "embed_store.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS embeddings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    text        TEXT    NOT NULL,
    embedding   TEXT    NOT NULL,  -- JSON array of floats
    metadata    TEXT    NOT NULL DEFAULT '{}',  -- JSON object
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_created_at ON embeddings (created_at);
"""


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two equal-length vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


class EmbedBrain:
    """
    Local semantic memory using nomic-embed-text + SQLite.

    SQLite operations run in a thread executor to avoid blocking the event loop.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = db_path or _DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

        from ..services.ollama_client import OllamaClient
        self._ollama = OllamaClient()

    # ------------------------------------------------------------------
    # DB setup
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.executescript(_SCHEMA_SQL)
        logger.debug("EmbedBrain DB initialised at %s", self._db_path)

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def embed(self, text: str) -> List[float]:
        """
        Embed a text string using nomic-embed-text.

        Args:
            text: The text to embed.

        Returns:
            List of floats (the embedding vector).
        """
        logger.debug("Embedding text (len=%d)", len(text))
        return await self._ollama.run_embed(text)

    async def store(self, text: str, metadata: Optional[dict] = None) -> int:
        """
        Embed *text* and store it in SQLite.

        Args:
            text: Text to embed and store.
            metadata: Optional JSON-serialisable metadata dict.

        Returns:
            The new row id.
        """
        vector = await self.embed(text)
        meta_json = json.dumps(metadata or {})
        vector_json = json.dumps(vector)
        now = datetime.utcnow().isoformat()

        loop = asyncio.get_event_loop()
        row_id = await loop.run_in_executor(
            None, self._db_insert, text, vector_json, meta_json, now
        )
        logger.debug("Stored embedding id=%d text_len=%d", row_id, len(text))
        return row_id

    async def search(self, query: str, top_k: int = 5) -> List[dict]:
        """
        Find the *top_k* most similar stored embeddings to *query*.

        Args:
            query: Search query text.
            top_k: Number of results to return.

        Returns:
            List of dicts with keys: id, text, metadata, similarity, created_at.
        """
        query_vec = await self.embed(query)

        loop = asyncio.get_event_loop()
        rows = await loop.run_in_executor(None, self._db_fetch_all)

        # Score all rows and sort
        scored = []
        for row in rows:
            row_id, text, emb_json, meta_json, created_at = row
            try:
                vec = json.loads(emb_json)
                sim = _cosine_similarity(query_vec, vec)
            except Exception:
                sim = 0.0
            scored.append(
                {
                    "id": row_id,
                    "text": text,
                    "metadata": json.loads(meta_json),
                    "similarity": round(sim, 4),
                    "created_at": created_at,
                }
            )

        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:top_k]

    async def store_successful_route(
        self, user_request: str, route_result: dict, quality_score: float
    ) -> int:
        """
        Store a successful routing decision for future similarity lookups.

        Args:
            user_request: The original user message.
            route_result: The RouteResult dict used for generation.
            quality_score: Final quality score from the reviewer (0.0-1.0).

        Returns:
            The new row id.
        """
        metadata = {
            "type": "route_memory",
            "quality_score": quality_score,
            "intent": route_result.get("intent"),
            "style_family": route_result.get("style_family"),
            "anime_genre": route_result.get("anime_genre"),
            "selected_checkpoint": route_result.get("selected_checkpoint"),
            "selected_workflow": route_result.get("selected_workflow"),
            "visual_mode": route_result.get("visual_mode"),
            "confidence": route_result.get("confidence"),
        }
        logger.info(
            "Storing route memory: checkpoint=%s quality=%.2f",
            route_result.get("selected_checkpoint"), quality_score
        )
        return await self.store(user_request, metadata=metadata)

    async def find_similar_routes(self, user_request: str, top_k: int = 3) -> List[dict]:
        """
        Find past successful route decisions similar to *user_request*.

        Only returns entries with ``type == "route_memory"``.

        Args:
            user_request: The new user request to compare against.
            top_k: Number of similar routes to return.

        Returns:
            List of route memory dicts ordered by similarity.
        """
        results = await self.search(user_request, top_k=top_k * 3)
        # Filter to route_memory entries only
        route_results = [
            r for r in results if r.get("metadata", {}).get("type") == "route_memory"
        ]
        return route_results[:top_k]

    # ------------------------------------------------------------------
    # Sync SQLite helpers (run in executor)
    # ------------------------------------------------------------------

    def _db_insert(self, text: str, vector_json: str, meta_json: str, now: str) -> int:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "INSERT INTO embeddings (text, embedding, metadata, created_at) VALUES (?, ?, ?, ?)",
                (text, vector_json, meta_json, now),
            )
            return cursor.lastrowid

    def _db_fetch_all(self) -> list:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT id, text, embedding, metadata, created_at FROM embeddings"
            )
            return cursor.fetchall()
