# Copyright (c) 2026 eele14. All Rights Reserved.
import httpx
from pathlib import Path

from config import Config


_CONVO_STARTER_PROMPT = (
    "start a casual message in a discord server. share something from a recent flight in project flight, "
    "ask about an airport or route, complain about something in the game, brag about a smooth landing, "
    "anything aviation related. keep it short and natural like you're just typing in chat. don't address anyone specific."
)


class LLMClient:
    def __init__(self, config: Config):
        self._backend = config.llm_backend
        self._system_prompt = Path(config.system_prompt_file).read_text().strip()

        if self._backend == "lmstudio":
            self._url = config.lmstudio_url
            self._model = config.lmstudio_model
            self._headers: dict[str, str] | None = None
            if config.lmstudio_api_key:
                self._headers = {"Authorization": f"Bearer {config.lmstudio_api_key}"}
        else:
            self._url = f"{config.ollama_url}/api/chat"
            self._model = config.ollama_model
            self._headers = None

    async def chat(self, history: list[dict]) -> str:
        messages = [{"role": "system", "content": self._system_prompt}] + history
        return await self._call(messages, timeout=120)

    async def generate_convo_starter(self) -> str:
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": _CONVO_STARTER_PROMPT},
        ]
        return await self._call(messages, timeout=60)

    async def random_reply(self, message_text: str) -> str:
        messages = [
            {"role": "system", "content": self._system_prompt},
            {
                "role": "user",
                "content": (
                    f"someone just sent this in the discord: \"{message_text}\"\n"
                    "chime in naturally with a short reaction or comment, like you just saw it while scrolling. "
                    "keep it very short."
                ),
            },
        ]
        return await self._call(messages, timeout=60)

    async def check_relevance(self, context: str, new_message: str) -> bool:
        messages = [
            {
                "role": "user",
                "content": (
                    f"previous conversation:\n{context}\n\n"
                    f"new message: {new_message}\n\n"
                    "is this new message related to the previous conversation? answer only YES or NO"
                ),
            }
        ]
        result = await self._call(messages, timeout=15)
        return "YES" in result.upper()

    async def _call(self, messages: list[dict], timeout: int = 60) -> str:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                self._url,
                headers=self._headers,
                json={"model": self._model, "messages": messages, "stream": False},
            )
            response.raise_for_status()

        data = response.json()

        # Ollama: {"message": {"content": "..."}}
        # LM Studio (OpenAI-compatible): {"choices": [{"message": {"content": "..."}}]}
        if "choices" in data:
            return data["choices"][0]["message"]["content"].strip()
        return data["message"]["content"].strip()


# Keep old name as alias so nothing else breaks
OllamaClient = LLMClient
