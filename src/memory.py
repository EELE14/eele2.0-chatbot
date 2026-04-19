# Copyright (c) 2026 eele14. All Rights Reserved.
import logging
import time
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)


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
                    created_at   REAL    NOT NULL
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_facts_user_id ON user_facts(user_id)"
            )
            await db.commit()
        logger.info("Memory DB initialised at %s", self._db_path)

    async def add_fact(
        self,
        user_id: int,
        display_name: str,
        fact: str,
        source: str = "auto",
    ) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT id FROM user_facts WHERE user_id = ? AND fact = ?",
                (user_id, fact),
            )
            if await cursor.fetchone():
                logger.debug("Fact already stored for %s (%s), skipping: %r", display_name, user_id, fact)
                return
            await db.execute(
                "INSERT INTO user_facts (user_id, display_name, fact, source, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, display_name, fact, source, time.time()),
            )
            await db.commit()
        logger.info("Stored [%s] fact for %s (%s): %r", source, display_name, user_id, fact)

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
