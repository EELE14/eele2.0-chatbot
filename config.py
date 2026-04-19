# Copyright (c) 2026 eele14. All Rights Reserved.
import os
from dotenv import dotenv_values


class Config:
    def __init__(self, env_file: str = ".env"):
        values = {**dotenv_values(env_file), **os.environ}

        self.discord_token: str = values["DISCORD_TOKEN"]
        self.allowed_guild_id: int = int(values.get("ALLOWED_GUILD_ID", "1389386451761893458"))

        # LLM backend: "ollama" (default) or "lmstudio"
        self.llm_backend: str = values.get("LLM_BACKEND", "ollama").lower()

        self.ollama_url: str = values.get("OLLAMA_URL", "http://localhost:11434")
        self.ollama_model: str = values.get("OLLAMA_MODEL", "llama3.1:8b")

        lmstudio_host: str = values.get("LMSTUDIO_HOST", "127.0.0.1")
        lmstudio_port: int = int(values.get("LMSTUDIO_PORT", "1234"))
        self.lmstudio_url: str = f"http://{lmstudio_host}:{lmstudio_port}/v1/chat/completions"
        self.lmstudio_model: str = values.get("LMSTUDIO_MODEL", "local-model")

        self.max_history: int = int(values.get("MAX_HISTORY", "20"))
        self.system_prompt_file: str = values.get("SYSTEM_PROMPT_FILE", "system_prompt.txt")

        self.random_convo_channels: list[int] = [
            int(x.strip())
            for x in values.get("RANDOM_CONVO_CHANNELS", "1389427108824088736,1389558958192201738").split(",")
            if x.strip()
        ]
        self.random_convo_interval: int = int(values.get("RANDOM_CONVO_INTERVAL", "10"))

        self.debounce_seconds: float = float(values.get("DEBOUNCE_SECONDS", "3.0"))
        self.context_window_seconds: float = float(values.get("CONTEXT_WINDOW_SECONDS", "120"))

        # Chance (0–100) to randomly reply to any message in the guild
        self.random_reply_chance: int = int(values.get("RANDOM_REPLY_CHANCE", "8"))
        # Minimum seconds between random replies in the same channel
        self.random_reply_cooldown: int = int(values.get("RANDOM_REPLY_COOLDOWN", "180"))
