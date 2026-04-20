# Copyright (c) 2026 eele14. All Rights Reserved.
import asyncio
import datetime
import logging
import random
import re
import time
from dataclasses import dataclass, field

import discord

from config import Config
from llm import LLMClient
from history import ConversationHistory
from memory import UserMemory
from search import duckduckgo_search, is_search_error
from giphy import search_gif

logger = logging.getLogger(__name__)

_SEARCH_RE     = re.compile(r'\[SEARCH:\s*(.+?)\]',  re.IGNORECASE)
_TIMEOUT_RE    = re.compile(r'\[TIMEOUT:\s*(\d+)\]', re.IGNORECASE)
_GIF_RE        = re.compile(r'\[GIF:\s*(.+?)\]',     re.IGNORECASE)
_REACT_RE      = re.compile(r'\[REACT:\s*(.+?)\]',   re.IGNORECASE)
_GIF_INTENT_RE = re.compile(r'\bgif\b', re.IGNORECASE)

_SEARCH_PHRASES = [
    "lemme google that real quick",
    "hold on lemme look that up",
    "one sec lemme check",
    "brb googling",
    "lemme search that up",
]


def _clean(text: str) -> str:
    text = _SEARCH_RE.sub("", text)
    text = _TIMEOUT_RE.sub("", text)
    text = _GIF_RE.sub("", text)
    text = _REACT_RE.sub("", text)
    return text.strip()


@dataclass
class _Pending:
    parts: list[str] = field(default_factory=list)
    first_message: discord.Message | None = None
    task: asyncio.Task | None = None
    is_trigger: bool = False


_OWNER_ID = 1263756486660587543


def _is_authorized(interaction: discord.Interaction) -> bool:
    if interaction.user.id == _OWNER_ID:
        return True
    if isinstance(interaction.user, discord.Member):
        return interaction.user.guild_permissions.administrator
    return False


class Bot(discord.Client):
    def __init__(self, config: Config):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self._config = config
        self._llm = LLMClient(config)
        self._history = ConversationHistory(config.max_history, ttl_seconds=config.history_ttl)
        self._memory = UserMemory(config.memory_db_path)
        self._pending: dict[tuple[int, int], _Pending] = {}
        self._last_interaction: dict[tuple[int, int], float] = {}
        self._last_channel_activity: dict[int, float] = {}
        self._last_random_reply: dict[int, float] = {}
        self._last_gif: dict[int, float] = {}
        self._last_llm_error_msg: dict[int, float] = {}
        self._start_time: float = 0.0
        self.tree = discord.app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        await self._memory.init()
        guild = discord.Object(id=self._config.allowed_guild_id)

        @self.tree.command(name="wack", description="Clear the bot's memory for this channel", guild=guild)
        async def wack(interaction: discord.Interaction) -> None:
            if not _is_authorized(interaction):
                await interaction.response.send_message("nope", ephemeral=True)
                return
            self._history.clear(interaction.channel_id)
            self._last_channel_activity.pop(interaction.channel_id, None)
            logger.info("History cleared for channel %s by %s", interaction.channel_id, interaction.user)
            await interaction.response.send_message("uhh my head hurts")

        @self.tree.command(name="reload", description="Reload the system prompt without restarting", guild=guild)
        async def reload(interaction: discord.Interaction) -> None:
            if not _is_authorized(interaction):
                await interaction.response.send_message("nope", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            try:
                self._llm.reload_prompt()
                logger.info("System prompt reloaded by %s", interaction.user)
                await interaction.followup.send(f"reloaded `{self._config.system_prompt_file}` ✓", ephemeral=True)
            except FileNotFoundError:
                await interaction.followup.send(f"file not found: `{self._config.system_prompt_file}`", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"reload failed: {e}", ephemeral=True)

        @self.tree.command(name="status", description="Show bot status and configuration", guild=guild)
        async def status(interaction: discord.Interaction) -> None:
            if not _is_authorized(interaction):
                await interaction.response.send_message("nope", ephemeral=True)
                return

            uptime_secs = int(time.monotonic() - self._start_time)
            h, rem = divmod(uptime_secs, 3600)
            m, s = divmod(rem, 60)
            uptime_str = f"{h}h {m}m {s}s" if h else f"{m}m {s}s"

            backend = self._config.llm_backend
            model = self._config.lmstudio_model if backend == "lmstudio" else self._config.ollama_model

            gif_status = (
                f"enabled · cooldown {self._config.gif_cooldown}s"
                if self._config.giphy_api_key
                else "disabled (no GIPHY_API_KEY)"
            )

            blocked = (
                ", ".join(f"<#{c}>" for c in self._config.blocked_channels)
                or "none"
            )

            active = sum(
                1 for t in self._last_channel_activity.values()
                if time.monotonic() - t <= self._config.context_window_seconds
            )

            embed = discord.Embed(title="bot status", color=0x2b2d31)
            embed.add_field(name="uptime", value=uptime_str, inline=True)
            embed.add_field(name="backend", value=f"{backend} · `{model}`", inline=True)
            embed.add_field(name="system prompt", value=f"`{self._config.system_prompt_file}`", inline=False)
            embed.add_field(name="history", value=f"{self._config.max_history} msgs/channel", inline=True)
            embed.add_field(name="active channels", value=str(active), inline=True)
            embed.add_field(name="gifs", value=gif_status, inline=False)
            embed.add_field(name="random reply", value=f"{self._config.random_reply_chance}% · {self._config.random_reply_cooldown}s cooldown", inline=True)
            embed.add_field(name="random convo", value=f"every {self._config.random_convo_interval}m", inline=True)
            embed.add_field(name="blocked channels", value=blocked, inline=False)

            await interaction.response.send_message(embed=embed, ephemeral=True)

        @self.tree.command(name="remember", description="Manually add a memory for a user", guild=guild)
        @discord.app_commands.describe(user="The user to remember something about", memory="The fact to remember")
        async def remember(interaction: discord.Interaction, user: discord.Member, memory: str) -> None:
            if interaction.user.id != _OWNER_ID:
                await interaction.response.send_message("nope", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            try:
                embedding = await self._llm.embed(memory)
            except Exception as e:
                logger.warning("Failed to embed manual fact %r: %s", memory, e)
                embedding = None
            await self._memory.add_fact(user.id, user.display_name, memory, source="manual", embedding=embedding)
            logger.info("Manual memory added for %s (%s): %r", user.display_name, user.id, memory)
            await interaction.followup.send(
                f"got it, i'll remember that about {user.display_name}", ephemeral=True
            )

        await self.tree.sync(guild=guild)

    async def close(self) -> None:
        await self._llm.close()
        await super().close()

    async def on_ready(self):
        self._start_time = time.monotonic()
        logger.info("Logged in as %s (%s)", self.user, self.user.id)
        logger.info("Guild restriction: %s", self._config.allowed_guild_id)
        asyncio.create_task(self._random_convo_loop())

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return
        if not message.guild or message.guild.id != self._config.allowed_guild_id:
            return
        if message.channel.id in self._config.blocked_channels:
            return

        is_trigger = self._is_trigger(message)
        is_recent = self._is_recent_partner(message)
        is_active = self._is_active_channel(message)

        if is_trigger or is_recent or is_active:
            await self._buffer(message, is_trigger)
            return

        await self._maybe_random_reply(message)


    async def _buffer(self, message: discord.Message, is_trigger: bool):
        key = (message.channel.id, message.author.id)
        text = self._extract_content(message)

        if key in self._pending:
            self._pending[key].task.cancel()
            self._pending[key].parts.append(text)
            self._pending[key].is_trigger = self._pending[key].is_trigger or is_trigger
        else:
            self._pending[key] = _Pending(
                parts=[text],
                first_message=message,
                is_trigger=is_trigger,
            )

        self._pending[key].task = asyncio.create_task(self._flush(key))

    async def _flush(self, key: tuple[int, int]):
        await asyncio.sleep(self._config.debounce_seconds)
        pending = self._pending.pop(key, None)
        if not pending:
            return

        combined = " ".join(pending.parts)
        message = pending.first_message

        if pending.is_trigger:
            await self._respond(message, combined, is_trigger=True)
        else:
            if await self._is_relevant(message, combined):
                await self._respond(message, combined, is_trigger=False)


    async def _respond(self, message: discord.Message, text: str, is_trigger: bool = False):
        channel_id = message.channel.id
        user_id = message.author.id
        display_name = message.author.display_name
        self._last_interaction[(channel_id, user_id)] = time.monotonic()

        labeled_text = f"[{display_name}]: {text}"

        try:
            query_vector = await self._llm.embed(text)
            facts = await self._memory.get_relevant_facts(user_id, query_vector, self._config.memory_top_k)
        except Exception as e:
            logger.warning("Embedding failed, falling back to full fact list: %s", e)
            facts = await self._memory.get_facts(user_id)

        user_context: str | None = None
        if facts:
            facts_text = "\n".join(f"- {f}" for f in facts)
            user_context = (
                f"Important — you know the following about {display_name}, "
                f"the person you are currently responding to. "
                f"Use this information naturally in your reply if relevant:\n{facts_text}"
            )
            logger.info("Injecting %d memory fact(s) for %s into context", len(facts), display_name)
        else:
            logger.info("No memory facts found for %s (%s)", display_name, user_id)

        history_snapshot = self._history.get(channel_id)
        history_snapshot.append({"role": "user", "content": labeled_text})

        async with message.channel.typing():
            try:
                reply = await self._llm.chat(history_snapshot, style_hint=text, user_context=user_context)
            except Exception as e:
                logger.error("LLM error: %s", e)
                if is_trigger:
                    now = time.monotonic()
                    last = self._last_llm_error_msg.get(message.channel.id, 0)
                    if now - last >= self._config.llm_error_cooldown:
                        self._last_llm_error_msg[message.channel.id] = now
                        await message.reply("my brain's not working rn, try again in a bit", mention_author=False)
                return

        logger.info("Raw LLM reply: %r", reply)

        search_match = _SEARCH_RE.search(reply)
        if search_match:
            self._history.append(channel_id, "user", labeled_text)
            await self._handle_search(message, channel_id, search_match.group(1).strip())
            return

        timeout_match = _TIMEOUT_RE.search(reply)
        if timeout_match:
            minutes = min(int(timeout_match.group(1)), 10)
            await self._do_timeout(message, minutes)

        gif_match   = _GIF_RE.search(reply)
        react_match = _REACT_RE.search(reply)
        cleaned     = _clean(reply)

        if cleaned:
            self._history.append(channel_id, "user", labeled_text)
            self._history.append(channel_id, "assistant", cleaned)
            self._last_channel_activity[channel_id] = time.monotonic()
            await message.reply(cleaned, mention_author=False)
            if react_match:
                emoji = react_match.group(1).strip()
                try:
                    await message.add_reaction(emoji)
                    logger.info("Reacted with %r on message %s", emoji, message.id)
                except discord.HTTPException as e:
                    logger.warning("Failed to add reaction %r: %s", emoji, e)
            asyncio.create_task(self._extract_and_store_facts(user_id, display_name, text))
        elif not gif_match:
            return

        gif_query: str | None = gif_match.group(1).strip() if gif_match else None

        if gif_query is None and _GIF_INTENT_RE.search(text) and _GIF_INTENT_RE.search(cleaned):
            logger.warning("LLM verbally agreed to send a gif but omitted the marker — triggering fallback")
            try:
                gif_query = await self._llm.gif_search_term(cleaned)
                logger.info("Fallback gif search term: %r", gif_query)
            except Exception as e:
                logger.error("Failed to get gif search term: %s", e)

        if gif_query:
            await self._maybe_send_gif(message.channel, gif_query)

    async def _handle_search(self, message: discord.Message, channel_id: int, query: str):
        await message.reply(random.choice(_SEARCH_PHRASES), mention_author=False)

        result = await duckduckgo_search(query, max_results=self._config.max_search_results)
        logger.info("Search result for %r: %s", query, result[:120])

        search_context = (
            f"[search results for '{query}']:\n{result}\n\n"
            f"now actually answer using this info — keep your casual style but share what you found, don't ignore it"
        )

        async with message.channel.typing():
            try:
                reply = await self._llm.chat(self._history.get(channel_id), extra_context=search_context)
            except Exception as e:
                logger.error("LLM error after search: %s", e)
                return

        cleaned = _clean(reply)
        if not cleaned and not is_search_error(result):
            lines = result.splitlines()
            cleaned = lines[0] if lines else ""

        self._history.append(channel_id, "assistant", cleaned)
        self._last_channel_activity[channel_id] = time.monotonic()
        await message.channel.send(cleaned)

    async def _maybe_send_gif(self, channel: discord.abc.Messageable, query: str) -> None:
        if not self._config.giphy_api_key:
            logger.warning("GIF requested but TENOR_API_KEY is not configured")
            return
        channel_id = channel.id
        now = time.monotonic()
        remaining = self._config.gif_cooldown - (now - self._last_gif.get(channel_id, 0))
        if remaining > 0:
            logger.warning("GIF skipped — cooldown active for %ds more in channel %s", int(remaining), channel_id)
            return
        logger.info("Fetching GIF for query: %r", query)
        url = await search_gif(query, self._config.giphy_api_key)
        if url:
            self._last_gif[channel_id] = now
            await channel.send(url)
        else:
            logger.warning("No GIF returned for query: %r", query)

    async def _do_timeout(self, message: discord.Message, minutes: int):
        member = message.author
        if not isinstance(member, discord.Member):
            return
        duration = datetime.timedelta(minutes=minutes)
        try:
            await member.timeout(duration)
            logger.info("Timed out %s for %dm in %s", member, minutes, message.guild)
        except discord.Forbidden:
            logger.warning("Missing permission to timeout %s", member)
        except Exception as e:
            logger.error("Timeout error for %s: %s", member, e)


    async def _extract_and_store_facts(self, user_id: int, display_name: str, text: str) -> None:
        try:
            facts = await self._llm.extract_user_facts(display_name, text)
            for fact in facts:
                try:
                    embedding = await self._llm.embed(fact)
                except Exception as e:
                    logger.warning("Failed to embed fact %r: %s", fact, e)
                    embedding = None
                await self._memory.add_fact(user_id, display_name, fact, embedding=embedding)
        except Exception as e:
            logger.error("Fact extraction error for %s: %s", display_name, e)

    async def _maybe_random_reply(self, message: discord.Message):
        if not message.content:
            return

        if random.randint(1, 100) > self._config.random_reply_chance:
            return

        channel_id = message.channel.id
        last = self._last_random_reply.get(channel_id, 0)
        if (time.monotonic() - last) < self._config.random_reply_cooldown:
            return

        self._last_random_reply[channel_id] = time.monotonic()

        async with message.channel.typing():
            try:
                reply = await self._llm.random_reply(message.clean_content)
            except Exception as e:
                logger.error("Random reply error: %s", e)
                return

        gif_match = _GIF_RE.search(reply)
        cleaned = _clean(reply)
        if cleaned:
            await message.reply(cleaned, mention_author=False)
        if gif_match:
            await self._maybe_send_gif(message.channel, gif_match.group(1).strip())


    async def _random_convo_loop(self):
        await self.wait_until_ready()
        await asyncio.sleep(30)
        while not self.is_closed():
            try:
                await self._post_random_convo()
            except Exception as e:
                logger.error("Random convo error: %s", e)
            await asyncio.sleep(self._config.random_convo_interval * 60)

    async def _post_random_convo(self):
        for channel_id in self._config.random_convo_channels:
            channel = self.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.fetch_channel(channel_id)
                except Exception:
                    logger.warning("Could not fetch channel %s", channel_id)
                    continue

            staff = [
                m for m in channel.members
                if not m.bot and m != self.user
            ]

            if not staff:
                logger.warning("No members found in channel %s, skipping", channel_id)
                continue

            target = random.choice(staff)

            try:
                content = await self._llm.generate_convo_starter()
            except Exception as e:
                logger.error("Failed to generate convo starter: %s", e)
                continue

            gif_match = _GIF_RE.search(content)
            cleaned = _clean(content)
            if cleaned:
                await channel.send(f"{target.mention} {cleaned}")
            if gif_match:
                await self._maybe_send_gif(channel, gif_match.group(1).strip())


    async def _is_relevant(self, message: discord.Message, text: str) -> bool:
        history = self._history.get(message.channel.id)
        if not history:
            return False
        recent_context = " | ".join(m["content"] for m in history[-4:])
        try:
            return await self._llm.check_relevance(recent_context, text)
        except Exception:
            return False


    def _is_trigger(self, message: discord.Message) -> bool:
        if self.user in message.mentions:
            return True
        if message.reference and message.reference.resolved:
            return message.reference.resolved.author == self.user
        return False

    def _is_active_channel(self, message: discord.Message) -> bool:
        last = self._last_channel_activity.get(message.channel.id)
        if last is None:
            return False
        return (time.monotonic() - last) <= self._config.context_window_seconds

    def _is_recent_partner(self, message: discord.Message) -> bool:
        key = (message.channel.id, message.author.id)
        last = self._last_interaction.get(key)
        if last is None:
            return False
        return (time.monotonic() - last) <= self._config.context_window_seconds

    def _extract_content(self, message: discord.Message) -> str:
        text = message.clean_content
        if self.user:
            text = re.sub(rf"@{re.escape(self.user.name)}\b", "", text).strip()
        return text
