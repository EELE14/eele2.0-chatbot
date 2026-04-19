# Copyright (c) 2026 eele14. All Rights Reserved.
import time
from collections import deque


class ConversationHistory:
    def __init__(self, max_messages: int, ttl_seconds: float = 86400.0):
        self._max = max_messages
        self._ttl = ttl_seconds
        self._store: dict[int, deque[dict]] = {}
        self._last_access: dict[int, float] = {}

    def get(self, channel_id: int) -> list[dict]:
        self._evict()
        self._last_access[channel_id] = time.monotonic()
        return list(self._store.get(channel_id, deque()))

    def append(self, channel_id: int, role: str, content: str) -> None:
        self._evict()
        if channel_id not in self._store:
            self._store[channel_id] = deque(maxlen=self._max)
        self._store[channel_id].append({"role": role, "content": content})
        self._last_access[channel_id] = time.monotonic()

    def clear(self, channel_id: int) -> None:
        self._store.pop(channel_id, None)
        self._last_access.pop(channel_id, None)

    def _evict(self) -> None:
        now = time.monotonic()
        expired = [ch for ch, t in self._last_access.items() if now - t > self._ttl]
        for ch in expired:
            self._store.pop(ch, None)
            self._last_access.pop(ch, None)
