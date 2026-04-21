# Copyright (c) 2026 eele14. All Rights Reserved.
import httpx
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

_CONNECT_TIMEOUT = 8.0

from config import Config

logger = logging.getLogger(__name__)


_CONVO_STARTER_PROMPT = (
    "start a casual message in a discord server, in character. "
    "keep it short and natural like you're just typing in chat. don't address anyone specific."
)

_REACTION_GUIDANCE = (
    "REACTIONS: append [REACT: emoji] to add a reaction — only alongside real text, never alone, sparingly. "
    "Use Gen-Z meanings: 💀 = i'm dead, 😭 = relatable/funny, 🤡 = clown take, 💯 = agree, 🔥 = fire, 🫡 = respect. "
    "Almost never use emojis inside your text."
)


@dataclass
class GroqKeyManager:
    keys: list[str]
    # (key, model) -> epoch timestamp when rate limit expires
    _limits: dict[tuple[str, str], float] = field(default_factory=dict, repr=False)

    def mark_limited(self, key: str, model: str, retry_after: float) -> None:
        self._limits[(key, model)] = time.time() + retry_after
        logger.warning(
            "Groq key ...%s rate-limited for %r — available again in %.0fs",
            key[-4:], model, retry_after,
        )

    def available_keys_for(self, model: str) -> list[str]:
        now = time.time()
        return [k for k in self.keys if self._limits.get((k, model), 0.0) <= now]

    def status(self, model: str) -> str:
        now = time.time()
        available = sum(1 for k in self.keys if self._limits.get((k, model), 0.0) <= now)
        return f"{available}/{len(self.keys)} keys available"


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
            self._key_mgr: GroqKeyManager | None = None
            self._fallback_model = ""
        elif self._backend == "groq":
            self._url = config.groq_url
            self._model = config.groq_model
            self._fallback_model = config.groq_fallback_model
            self._headers = {}
            self._key_mgr = GroqKeyManager(keys=config.groq_api_keys)
            logger.info(
                "Groq backend: %d key(s), primary=%r, fallback=%r",
                len(config.groq_api_keys), self._model, self._fallback_model,
            )
        else:
            self._url = f"{config.ollama_url}/api/chat"
            self._model = config.ollama_model
            self._headers = {}
            self._key_mgr = None
            self._fallback_model = ""

        self._embed_headers: dict[str, str] = (
            {"Authorization": f"Bearer {config.embedding_api_key}"}
            if config.embedding_api_key
            else self._headers
        )

    async def close(self) -> None:
        await self._http.aclose()

    def reload_prompt(self) -> None:
        self._system_prompt = Path(self._config.system_prompt_file).read_text().strip()

    def groq_key_status(self, model: str) -> str:
        if self._key_mgr is None:
            return "n/a"
        return self._key_mgr.status(model)

    _GROUP_CHAT_FRAMING = (
        "this is a group discord channel — multiple users may be talking at once. "
        "each user message is prefixed with the sender's display name in [brackets]. "
        "address the person whose name appears in the most recent user message."
    )

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

    def _static_system(self) -> str:
        return "\n\n".join([self._system_prompt, self._GROUP_CHAT_FRAMING, _REACTION_GUIDANCE])

    async def chat(
        self,
        history: list[dict],
        extra_context: str | None = None,
        user_context: str | None = None,
    ) -> str:
        turns = list(history)

        # Prepend dynamic context to the last user turn so the system message stays static/cacheable.
        if turns and (user_context or extra_context):
            prefix_parts = []
            if user_context:
                prefix_parts.append(user_context)
            if extra_context:
                prefix_parts.append(extra_context)
            last = turns[-1]
            turns[-1] = {**last, "content": "\n\n".join(prefix_parts) + "\n\n" + last["content"]}

        messages = [{"role": "system", "content": self._static_system()}, *turns]
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

    async def extract_user_facts(self, display_name: str, message_text: str) -> list[str]:
        result = await self._call(
            [{"role": "user", "content": (
                f"Message from {display_name}: \"{message_text[:500]}\"\n\n"
                "Extract only durable personal facts explicitly stated that are worth remembering long-term.\n"
                "DO NOT include: their name or username (already known from context), "
                "things that are only relevant to this single message, vague or inferred statements, "
                "or filler like greetings.\n"
                "DO include: hobbies, job or profession, location, age, life events, "
                "specific preferences, opinions on concrete topics.\n"
                "Write each fact as a short third-person statement (e.g. 'Plays guitar', "
                "'Lives in Berlin', 'Works as a nurse', 'Dislikes horror movies').\n"
                "One fact per line. If nothing worth storing, reply with exactly: NONE"
            )}],
            timeout=15,
        )
        stripped = result.strip()
        if not stripped or stripped.upper() == "NONE":
            return []
        return [
            line.lstrip("-•* ").strip()
            for line in stripped.splitlines()
            if line.strip() and line.strip().upper() != "NONE"
        ]

    async def embed(self, text: str) -> list[float]:
        response = await self._http.post(
            self._config.embedding_url,
            headers=self._embed_headers,
            json={"model": self._config.embedding_model, "input": text},
            timeout=httpx.Timeout(15.0, connect=_CONNECT_TIMEOUT),
        )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]

    async def check_relevance(self, context: str, new_message: str) -> bool:
        result = await self._call(
            [
                {
                    "role": "user",
                    "content": (
                        f"Conversation so far:\n{context}\n\n"
                        f"New message: {new_message}\n\n"
                        "Is the new message related to this conversation? Reply with YES or NO only."
                    ),
                }
            ],
            timeout=15,
        )
        return result.strip().upper().startswith("YES")

    async def _call(self, messages: list[dict], timeout: int = 60) -> str:
        if self._backend == "groq":
            return await self._groq_call(messages, timeout)

        response = await self._http.post(
            self._url,
            headers=self._headers,
            json={"model": self._model, "messages": messages, "stream": False},
            timeout=httpx.Timeout(timeout, connect=_CONNECT_TIMEOUT),
        )
        if response.is_error:
            logger.error("LLM API %s — %s", response.status_code, response.text[:500])
        response.raise_for_status()
        return self._extract_content(response.json())

    async def _groq_call(self, messages: list[dict], timeout: int) -> str:
        # Try primary model first, then fallback if all keys exhausted
        for model in dict.fromkeys([self._model, self._fallback_model]):
            if not model:
                continue
            result = await self._try_groq_model(messages, model, timeout)
            if result is not None:
                if model != self._model:
                    logger.warning("All primary keys exhausted — using fallback model %r", model)
                return result
            logger.warning("All Groq keys rate-limited for %r", model)

        raise RuntimeError(
            f"All Groq keys exhausted for primary={self._model!r} and fallback={self._fallback_model!r}"
        )

    async def _try_groq_model(self, messages: list[dict], model: str, timeout: int) -> str | None:
        """Try every available key for a given model. Returns content, or None if all keys are rate-limited."""
        assert self._key_mgr is not None
        available = self._key_mgr.available_keys_for(model)
        if not available:
            return None

        for key in available:
            response = await self._http.post(
                self._url,
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "messages": messages, "stream": False},
                timeout=httpx.Timeout(timeout, connect=_CONNECT_TIMEOUT),
            )
            if response.status_code == 429:
                retry_after = float(response.headers.get("retry-after", 60))
                self._key_mgr.mark_limited(key, model, retry_after)
                continue
            if response.is_error:
                logger.error("LLM API %s — %s", response.status_code, response.text[:500])
            response.raise_for_status()
            return self._extract_content(response.json())

        return None  # all available keys exhausted for this model
