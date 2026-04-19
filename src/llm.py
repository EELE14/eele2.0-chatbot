# Copyright (c) 2026 eele14. All Rights Reserved.
import httpx
from pathlib import Path

from config import Config


_CONVO_STARTER_PROMPT = (
    "start a casual message in a discord server, in character. "
    "keep it short and natural like you're just typing in chat. don't address anyone specific."
)


class LLMClient:
    def __init__(self, config: Config):
        self._config = config
        self._backend = config.llm_backend
        self._system_prompt = Path(config.system_prompt_file).read_text().strip()
        self._http = httpx.AsyncClient()

        if self._backend == "lmstudio":
            self._url = config.lmstudio_url
            self._model = config.lmstudio_model
            self._headers: dict[str, str] = (
                {"Authorization": f"Bearer {config.lmstudio_api_key}"}
                if config.lmstudio_api_key
                else {}
            )
        else:
            self._url = f"{config.ollama_url}/api/chat"
            self._model = config.ollama_model
            self._headers = {}

    async def close(self) -> None:
        await self._http.aclose()

    def reload_prompt(self) -> None:
        self._system_prompt = Path(self._config.system_prompt_file).read_text().strip()

    def _build_messages(self, *turns: dict) -> list[dict]:
        return [{"role": "system", "content": self._system_prompt}, *turns]

    def _extract_content(self, data: dict) -> str:
        if "choices" in data:
            choices = data.get("choices", [])
            if not choices:
                raise ValueError("LLM returned empty choices list")
            return choices[0]["message"]["content"].strip()
        content = data.get("message", {}).get("content")
        if content is None:
            raise ValueError(f"Unexpected LLM response format: {list(data.keys())}")
        return content.strip()

    async def chat(
        self,
        history: list[dict],
        style_hint: str | None = None,
        extra_context: str | None = None,
    ) -> str:
        messages = self._build_messages(*history)
        if extra_context:
            messages.append({"role": "system", "content": extra_context})
        if style_hint:
            messages.append({
                "role": "system",
                "content": f"Mirror the writing style, tone, and approximate length of this message in your reply: \"{style_hint[:300]}\"",
            })
        return await self._call(messages, timeout=120)

    async def generate_convo_starter(self) -> str:
        return await self._call(
            self._build_messages({"role": "user", "content": _CONVO_STARTER_PROMPT}),
            timeout=60,
        )

    async def random_reply(self, message_text: str) -> str:
        return await self._call(
            self._build_messages(
                {
                    "role": "user",
                    "content": (
                        f"someone just sent this in the discord: \"{message_text}\"\n"
                        "chime in naturally with a short reaction or comment, like you just saw it while scrolling. "
                        "keep it very short."
                    ),
                }
            ),
            timeout=60,
        )

    async def gif_search_term(self, context: str) -> str:
        result = await self._call(
            [
                {
                    "role": "user",
                    "content": (
                        f"Based on this message, give me a short Tenor GIF search query (2-4 words max, no punctuation):\n\"{context}\"\n\nReply with only the search query, nothing else."
                    ),
                }
            ],
            timeout=15,
        )
        return result.strip().strip('"').strip("'")

    async def check_relevance(self, context: str, new_message: str) -> bool:
        result = await self._call(
            [
                {
                    "role": "user",
                    "content": (
                        f"previous conversation:\n{context}\n\n"
                        f"new message: {new_message}\n\n"
                        "is this new message related to the previous conversation? answer only YES or NO"
                    ),
                }
            ],
            timeout=15,
        )
        return result.strip().upper().startswith("YES")

    async def _call(self, messages: list[dict], timeout: int = 60) -> str:
        response = await self._http.post(
            self._url,
            headers=self._headers,
            json={"model": self._model, "messages": messages, "stream": False},
            timeout=timeout,
        )
        response.raise_for_status()
        return self._extract_content(response.json())
