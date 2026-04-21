# Copyright (c) 2026 eele14. All Rights Reserved.
import array
import logging
import math
import time

import asyncpg

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
    def __init__(self, database_url: str):
        self._database_url = database_url
        self._pool: asyncpg.Pool | None = None

    async def init(self) -> None:
        self._pool = await asyncpg.create_pool(self._database_url, min_size=1, max_size=5)
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_facts (
                    id           SERIAL PRIMARY KEY,
                    user_id      BIGINT  NOT NULL,
                    display_name TEXT    NOT NULL,
                    fact         TEXT    NOT NULL,
                    source       TEXT    NOT NULL DEFAULT 'auto',
                    embedding    BYTEA,
                    created_at   DOUBLE PRECISION NOT NULL
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_facts_user_id ON user_facts(user_id)"
            )
        logger.info("Memory DB initialised (PostgreSQL)")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def add_fact(
        self,
        user_id: int,
        display_name: str,
        fact: str,
        source: str = "auto",
        embedding: list[float] | None = None,
    ) -> None:
        blob = _encode_embedding(embedding) if embedding is not None else None
        async with self._pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id FROM user_facts WHERE user_id = $1 AND fact = $2",
                user_id, fact,
            )
            if existing:
                logger.debug("Fact already stored for %s (%s), skipping: %r", display_name, user_id, fact)
                return
            await conn.execute(
                "INSERT INTO user_facts (user_id, display_name, fact, source, embedding, created_at) "
                "VALUES ($1, $2, $3, $4, $5, $6)",
                user_id, display_name, fact, source, blob, time.time(),
            )
        embedded = "with embedding" if embedding is not None else "no embedding"
        logger.info("Stored [%s/%s] fact for %s (%s): %r", source, embedded, display_name, user_id, fact)

    async def get_relevant_facts(
        self,
        user_id: int,
        query_vector: list[float] | None,
        top_k: int = 5,
    ) -> list[str]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT fact, source, embedding FROM user_facts WHERE user_id = $1 ORDER BY created_at ASC",
                user_id,
            )

        if not rows:
            logger.info("No facts stored for user %s", user_id)
            return []

        if query_vector is None:
            facts = [row["fact"] for row in rows]
            logger.info("No query vector — returning all %d fact(s) for user %s", len(facts), user_id)
            return facts

        scored: list[tuple[float, str]] = []
        always_include: list[str] = []

        for row in rows:
            fact, source, blob = row["fact"], row["source"], row["embedding"]
            if blob is None:
                if source == "manual":
                    always_include.append(fact)
            else:
                vec = _decode_embedding(bytes(blob))
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
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT fact FROM user_facts WHERE user_id = $1 ORDER BY created_at ASC",
                user_id,
            )
        facts = [row["fact"] for row in rows]
        logger.info("Loaded %d fact(s) for user %s", len(facts), user_id)
        return facts

    async def clear_facts(self, user_id: int) -> int:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM user_facts WHERE user_id = $1", user_id
            )
        count = int(result.split()[-1])
        logger.info("Cleared %d fact(s) for user %s", count, user_id)
        return count
