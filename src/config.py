# Copyright (c) 2026 eele14. All Rights Reserved.
import os
from dotenv import dotenv_values


def _int(values: dict, key: str, default: int) -> int:
    raw = values.get(key, str(default))
    try:
        return int(raw)
    except (ValueError, TypeError):
        raise ValueError(f"Environment variable {key} must be an integer, got: {raw!r}")


def _float(values: dict, key: str, default: float) -> float:
    raw = values.get(key, str(default))
    try:
        return float(raw)
    except (ValueError, TypeError):
        raise ValueError(f"Environment variable {key} must be a number, got: {raw!r}")


def _str(values: dict, key: str, default: str) -> str:
    return (values.get(key) or default).strip()


class Config:
    def __init__(self, env_file: str = ".env"):
        values = {**dotenv_values(env_file), **os.environ}

        self.discord_token: str      = values["DISCORD_TOKEN"]
        self.allowed_guild_id: int   = _int(values, "ALLOWED_GUILD_ID", 1389386451761893458)

        self.llm_backend: str        = _str(values, "LLM_BACKEND", "ollama").lower()
        if self.llm_backend not in ("ollama", "lmstudio", "groq"):
            raise ValueError(f"LLM_BACKEND must be 'ollama', 'lmstudio', or 'groq', got: {self.llm_backend!r}")

        self.ollama_url: str         = _str(values, "OLLAMA_URL",   "http://localhost:11434")
        self.ollama_model: str       = _str(values, "OLLAMA_MODEL", "llama3.1:8b")

        lmstudio_host                = _str(values, "LMSTUDIO_HOST", "127.0.0.1")
        lmstudio_port                = _int(values, "LMSTUDIO_PORT", 1234)
        self.lmstudio_url: str       = f"http://{lmstudio_host}:{lmstudio_port}/v1/chat/completions"
        self.lmstudio_model: str     = _str(values, "LMSTUDIO_MODEL", "local-model")
        lmstudio_key                 = (values.get("LMSTUDIO_API_KEY") or "").strip()
        self.lmstudio_api_key: str | None = lmstudio_key or None

        groq_key                     = (values.get("GROQ_API_KEY") or "").strip()
        self.groq_api_key: str | None = groq_key or None
        self.groq_model: str         = _str(values, "GROQ_MODEL", "gemma2-9b-it")
        self.groq_url: str           = "https://api.groq.com/openai/v1/chat/completions"

        _embed_default               = f"http://{lmstudio_host}:{lmstudio_port}/v1/embeddings"
        self.embedding_url: str      = _str(values, "EMBEDDING_URL",   _embed_default)
        self.embedding_model: str    = _str(values, "EMBEDDING_MODEL", "jina-embeddings-v3")
        embed_key                    = (values.get("EMBEDDING_API_KEY") or "").strip()
        self.embedding_api_key: str | None = embed_key or None
        self.memory_top_k: int       = _int(values, "MEMORY_TOP_K",    5)

        self.max_history: int             = _int(values, "MAX_HISTORY", 20)
        self.history_ttl: int             = _int(values, "HISTORY_TTL", 14400)
        self.system_prompt_file: str      = _str(values, "SYSTEM_PROMPT_FILE", "prompts/system_prompt.txt")

        self.random_convo_channels: list[int] = [
            int(x.strip())
            for x in _str(values, "RANDOM_CONVO_CHANNELS", "1389427108824088736,1389558958192201738").split(",")
            if x.strip()
        ]
        self.random_convo_interval: int   = _int(values,   "RANDOM_CONVO_INTERVAL",   10)
        self.debounce_seconds: float      = _float(values, "DEBOUNCE_SECONDS",         3.0)
        self.context_window_seconds: float = _float(values, "CONTEXT_WINDOW_SECONDS",  120.0)
        self.random_reply_chance: int     = _int(values,   "RANDOM_REPLY_CHANCE",      8)
        self.random_reply_cooldown: int   = _int(values,   "RANDOM_REPLY_COOLDOWN",    180)

        self.max_search_results: int      = _int(values, "MAX_SEARCH_RESULTS", 4)

        giphy_key                         = (values.get("GIPHY_API_KEY") or "").strip()
        self.giphy_api_key: str | None    = giphy_key or None
        self.gif_cooldown: int            = _int(values, "GIF_COOLDOWN", 300)

        self.memory_db_path: str          = _str(values, "MEMORY_DB_PATH", "data/user_memory.db")
        self.llm_error_cooldown: int      = _int(values, "LLM_ERROR_COOLDOWN", 60)

        self.blocked_channels: list[int] = [
            int(x.strip())
            for x in _str(values, "BLOCKED_CHANNELS", "").split(",")
            if x.strip()
        ]

        if not 0 <= self.random_reply_chance <= 100:
            raise ValueError(f"RANDOM_REPLY_CHANCE must be 0–100, got {self.random_reply_chance}")
