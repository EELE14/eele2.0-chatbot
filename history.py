# Copyright (c) 2026 eele14. All Rights Reserved.
from collections import defaultdict


class ConversationHistory:
    def __init__(self, max_messages: int):
        self._max = max_messages
        self._store: dict[int, list[dict]] = defaultdict(list)

    def get(self, channel_id: int) -> list[dict]:
        return list(self._store[channel_id])

    def append(self, channel_id: int, role: str, content: str) -> None:
        self._store[channel_id].append({"role": role, "content": content})
        if len(self._store[channel_id]) > self._max:
            self._store[channel_id] = self._store[channel_id][-self._max:]

    def clear(self, channel_id: int) -> None:
        self._store.pop(channel_id, None)
