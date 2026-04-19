# Copyright (c) 2026 eele14. All Rights Reserved.
import time
from pathlib import Path

import aiosqlite


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
                return
            await db.execute(
                "INSERT INTO user_facts (user_id, display_name, fact, source, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, display_name, fact, source, time.time()),
            )
            await db.commit()

    async def get_facts(self, user_id: int) -> list[str]:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT fact FROM user_facts WHERE user_id = ? ORDER BY created_at ASC",
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def clear_facts(self, user_id: int) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM user_facts WHERE user_id = ?", (user_id,)
            )
            await db.commit()
            return cursor.rowcount
