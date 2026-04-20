# Copyright (c) 2026 eele14. All Rights Reserved.
import array
import logging
import math
import time
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)


def _encode_embedding(embedding: list[float]) -> bytes:
    return array.array("f", embedding).tobytes()


def _decode_embedding(blob: bytes) -> list[float]:
    arr = array.array("f")
    arr.frombytes(blob)
    return arr.tolist()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class UserMemory:
    def __init__(self, db_path: str):
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_facts (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      INTEGER NOT NULL,
                    display_name TEXT    NOT NULL,
                    fact         TEXT    NOT NULL,
                    source       TEXT    NOT NULL DEFAULT 'auto',
                    embedding    BLOB,
                    created_at   REAL    NOT NULL
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_facts_user_id ON user_facts(user_id)"
            )
            # Migration: add embedding column to existing databases
            cursor = await db.execute("PRAGMA table_info(user_facts)")
            cols = {row[1] for row in await cursor.fetchall()}
            if "embedding" not in cols:
                await db.execute("ALTER TABLE user_facts ADD COLUMN embedding BLOB")
                logger.info("Migrated user_facts table: added embedding column")
            await db.commit()
        logger.info("Memory DB initialised at %s", self._db_path)

    async def add_fact(
        self,
        user_id: int,
        display_name: str,
        fact: str,
        source: str = "auto",
        embedding: list[float] | None = None,
    ) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT id FROM user_facts WHERE user_id = ? AND fact = ?",
                (user_id, fact),
            )
            if await cursor.fetchone():
                logger.debug("Fact already stored for %s (%s), skipping: %r", display_name, user_id, fact)
                return
            blob = _encode_embedding(embedding) if embedding is not None else None
            await db.execute(
                "INSERT INTO user_facts (user_id, display_name, fact, source, embedding, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, display_name, fact, source, blob, time.time()),
            )
            await db.commit()
        embedded = "with embedding" if embedding is not None else "no embedding"
        logger.info("Stored [%s/%s] fact for %s (%s): %r", source, embedded, display_name, user_id, fact)

    async def get_relevant_facts(
        self,
        user_id: int,
        query_vector: list[float] | None,
        top_k: int = 5,
    ) -> list[str]:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT fact, source, embedding FROM user_facts WHERE user_id = ? ORDER BY created_at ASC",
                (user_id,),
            )
            rows = await cursor.fetchall()

        if not rows:
            logger.info("No facts stored for user %s", user_id)
            return []

        if query_vector is None:
            facts = [row[0] for row in rows]
            logger.info("No query vector — returning all %d fact(s) for user %s", len(facts), user_id)
            return facts

        scored: list[tuple[float, str]] = []
        always_include: list[str] = []

        for fact, source, blob in rows:
            if blob is None:
                # Manual facts without embeddings are always included (curated, important).
                # Auto facts without embeddings are stale pre-migration noise — skip them.
                if source == "manual":
                    always_include.append(fact)
            else:
                vec = _decode_embedding(blob)
                score = _cosine_similarity(query_vector, vec)
                scored.append((score, fact))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_facts = [fact for _, fact in scored[:top_k]]
        result = top_facts + always_include

        top_score = scored[0][0] if scored else 0.0
        logger.info(
            "Retrieved %d relevant fact(s) from %d total for user %s (top similarity: %.3f)",
            len(result), len(rows), user_id, top_score,
        )
        return result

    async def get_facts(self, user_id: int) -> list[str]:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT fact FROM user_facts WHERE user_id = ? ORDER BY created_at ASC",
                (user_id,),
            )
            rows = await cursor.fetchall()
        facts = [row[0] for row in rows]
        logger.info("Loaded %d fact(s) for user %s", len(facts), user_id)
        return facts

    async def clear_facts(self, user_id: int) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM user_facts WHERE user_id = ?", (user_id,)
            )
            await db.commit()
            count = cursor.rowcount
        logger.info("Cleared %d fact(s) for user %s", count, user_id)
        return count
