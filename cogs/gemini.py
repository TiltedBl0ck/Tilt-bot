import logging
import random
import re
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import os
from collections import defaultdict
from datetime import datetime, timezone
import aiohttp

try:
    from google import genai
    from google.genai import types
    from google.genai.errors import ClientError
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False
    ClientError = Exception

from cogs.utils.web_search import get_latest_info

logger = logging.getLogger(__name__)

# ── API Keys ──────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY not found. Gemini AI features will not work.")

if not HAS_GENAI:
    logger.error(
        "google-genai package is not installed. "
        "Run: pip install google-genai[aiohttp]"
    )

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_BACKOFF_SECONDS = 60
DISCORD_MSG_LIMIT = 1900

_MAX_USER_FACING_ERR_LEN = 80


def _safe_err(exc: Exception) -> str:
    """Return sanitized user-facing error string."""
    raw = str(exc)
    raw = re.sub(r"https?://\S+", "<url>", raw)
    raw = re.sub(r"[A-Za-z0-9+/=_-]{40,}", "<redacted>", raw)
    return raw[:_MAX_USER_FACING_ERR_LEN]


class Gemini(commands.Cog):
    """AI chat powered by Gemini (new google-genai SDK) with Perplexity fallback."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.conversation_history: dict[int, list] = defaultdict(list)
        self._history_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.max_history = 15

        self.raw_model_list: list[str] = [
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ]
        self.model_list: list[str] = list(self.raw_model_list)
        self.model_status: dict[str, str] = {m: "unknown" for m in self.model_list}

        self.safety_settings = [
            types.SafetySetting(
                category="HARM_CATEGORY_HARASSMENT",
                threshold="BLOCK_ONLY_HIGH",
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_HATE_SPEECH",
                threshold="BLOCK_MEDIUM_AND_ABOVE",
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                threshold="BLOCK_ONLY_HIGH",
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_DANGEROUS_CONTENT",
                threshold="BLOCK_MEDIUM_AND_ABOVE",
            ),
        ]

        if GEMINI_API_KEY and HAS_GENAI:
            self._client = genai.Client(api_key=GEMINI_API_KEY)
        else:
            self._client = None

    async def cog_load(self) -> None:
        """
        FIX: Store task reference and add error callback to prevent
        silent exception swallowing.
        """
        task = asyncio.create_task(self.validate_available_models())
        task.add_done_callback(
            lambda t: logger.error(f"Model validation task failed: {t.exception()}")
            if not t.cancelled() and t.exception()
            else None
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Model validation
    # ─────────────────────────────────────────────────────────────────────────

    async def validate_available_models(self) -> None:
        if not self._client:
            return

        logger.info("🔍 Validating available Gemini models...")
        try:
            available = [
                m.name async for m in await self._client.aio.models.list()
            ]

            validated: list[str] = []
            for preferred in self.raw_model_list:
                if any(name.endswith(preferred) for name in available):
                    validated.append(preferred)
                    self.model_status[preferred] = "available"
                else:
                    self.model_status[preferred] = "not_found"
                    logger.debug(f"⚠️ Model '{preferred}' not found in API — skipping.")

            if validated:
                self.model_list = validated
                logger.info(f"✅ Model rotation: {', '.join(self.model_list)}")
            else:
                logger.warning("❌ No preferred models found — using raw list as fallback.")
                self.model_list = list(self.raw_model_list)

        except Exception as exc:
            logger.error(f"Model validation failed: {exc}")

    # ─────────────────────────────────────────────────────────────────────────
    # System prompt builder
    # ─────────────────────────────────────────────────────────────────────────

    def build_system_message(self, guild: discord.Guild | None = None) -> str:
        memory_cog = self.bot.get_cog("Memory")
        serverinfo_cog = self.bot.get_cog("ServerInfo")

        now = datetime.now(timezone.utc)
        current_date = now.strftime("%A, %B %d, %Y")
        current_time = now.strftime("%H:%M:%S UTC")

        system_msg = (
            f"You are a helpful Discord bot. "
            f"Current date: {current_date}. Current time: {current_time}. "
            f"Provide accurate, helpful responses based on available information."
        )

        if memory_cog:
            memory = memory_cog.memory
            if memory.get("system_prompt"):
                system_msg = memory["system_prompt"]
            else:
                lines = [
                    f"You are {memory.get('bot_name', 'Tilt-bot')}.",
                    f"Description: {memory.get('bot_description', 'A helpful bot')}",
                    f"Personality: {memory.get('personality', 'helpful and friendly')}",
                    f"Current date: {current_date}",
                    f"Current time: {current_time}",
                ]
                system_msg = "\n".join(lines)

        if guild and serverinfo_cog:
            try:
                guild_info = serverinfo_cog.get_guild_context(guild)
                system_msg += f"\n\nContext about the current server:\n{guild_info}"
            except Exception as exc:
                logger.debug(f"Could not get guild context: {exc}")

        return system_msg

    # ─────────────────────────────────────────────────────────────────────────
    # History helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _format_history_for_gemini(self, history: list) -> list[dict]:
        contents = []
        for msg in history:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        return contents

    async def update_history(
        self, channel_id: int, user_message: str, ai_response: str
    ) -> None:
        async with self._history_locks[channel_id]:
            history = self.conversation_history[channel_id]
            history.append({"role": "user", "content": user_message})
            history.append({"role": "assistant", "content": ai_response})
            max_entries = self.max_history * 2
            if len(history) > max_entries:
                self.conversation_history[channel_id] = history[-max_entries:]

    # ─────────────────────────────────────────────────────────────────────────
    # Gemini API call with exponential backoff
    # ─────────────────────────────────────────────────────────────────────────

    async def _call_gemini_model(
        self,
        model_name: str,
        contents: list,
        system_instruction: str,
    ) -> str:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await self._client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        safety_settings=self.safety_settings,
                    ),
                )
                return response.text

            except ClientError as exc:
                code = getattr(exc, "status_code", None) or str(exc)
                code_str = str(code)

                if "429" in code_str or "RESOURCE_EXHAUSTED" in code_str:
                    if attempt < max_retries - 1:
                        wait = min(2 ** attempt + random.uniform(0, 1), MAX_BACKOFF_SECONDS)
                        logger.warning(
                            f"⏳ Rate-limited on {model_name} "
                            f"(attempt {attempt + 1}/{max_retries}), "
                            f"retrying in {wait:.1f}s..."
                        )
                        await asyncio.sleep(wait)
                        continue
                    raise
                raise

        raise RuntimeError(f"Max retries exceeded for {model_name}")

    # ─────────────────────────────────────────────────────────────────────────
    # Main response orchestrator
    # ─────────────────────────────────────────────────────────────────────────

    async def get_gemini_response(
        self,
        channel_id: int,
        user_message: str,
        web_context: str = "",
        guild: discord.Guild | None = None,
    ) -> str:
        if not self._client:
            return "❌ Gemini client is not initialised (missing API key or package)."

        system_instruction = self.build_system_message(guild)
        history = list(self.conversation_history.get(channel_id, []))
        formatted_history = self._format_history_for_gemini(history)

        if web_context:
            final_user_text = (
                f"**Information from web search:**\n{web_context}\n\n"
                f"**User Query:** {user_message}"
            )
        else:
            final_user_text = user_message

        contents = formatted_history + [
            {"role": "user", "parts": [{"text": final_user_text}]}
        ]

        attempted_models: list[str] = []

        for model_name in self.model_list:
            try:
                text = await self._call_gemini_model(
                    model_name, contents, system_instruction
                )
                self.model_status[model_name] = "available"
                logger.info(f"✅ Success with {model_name}")
                return text

            except ClientError as exc:
                code_str = str(getattr(exc, "status_code", exc)).lower()

                if "404" in code_str or "not found" in code_str:
                    self.model_status[model_name] = "not_found"
                    logger.warning(f"⚠️ Model not found: {model_name}")
                    attempted_models.append(f"{model_name}(404)")

                elif "429" in code_str or "resource_exhausted" in code_str or "quota" in code_str:
                    self.model_status[model_name] = "quota_exceeded"
                    logger.warning(f"⚠️ Quota exhausted for {model_name}")
                    attempted_models.append(f"{model_name}(quota)")

                elif "503" in code_str or "unavailable" in code_str:
                    self.model_status[model_name] = "unavailable"
                    logger.warning(f"⚠️ Service unavailable: {model_name}")
                    attempted_models.append(f"{model_name}(503)")

                else:
                    self.model_status[model_name] = "error"
                    logger.error(f"❌ Unhandled ClientError on {model_name}: {exc}")
                    attempted_models.append(f"{model_name}(error)")

            except Exception as exc:
                self.model_status[model_name] = "error"
                logger.error(f"❌ Unexpected error on {model_name}: {exc}", exc_info=True)
                attempted_models.append(f"{model_name}(error)")

        logger.warning(
            f"❌ All Gemini models failed ({', '.join(attempted_models)}) "
            f"— attempting Perplexity fallback..."
        )
        perplexity_response = await self.get_perplexity_response(
            user_message, history=history
        )

        if perplexity_response:
            logger.info("✅ Perplexity fallback successful")
            return f"🌐 **(Via Perplexity AI)**\n\n{perplexity_response}"

        return (
            "⚠️ **All AI services are currently unavailable.**\n\n"
            f"Gemini: All models failed — {', '.join(attempted_models)}\n"
            f"Perplexity: Failed or not configured.\n\n"
            "Please try again later."
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Perplexity fallback
    # ─────────────────────────────────────────────────────────────────────────

    async def get_perplexity_response(
        self, user_message: str, history: list | None = None
    ) -> str | None:
        if not PERPLEXITY_API_KEY:
            logger.warning("⚠️ PERPLEXITY_API_KEY not configured — cannot use fallback")
            return None

        try:
            logger.info("🔄 Falling back to Perplexity API...")

            messages: list[dict] = []
            if history:
                for msg in history[-6:]:
                    role = "user" if msg["role"] == "user" else "assistant"
                    messages.append({"role": role, "content": msg["content"]})
            messages.append({"role": "user", "content": user_message})

            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": "sonar",
                    "messages": messages,
                }

                async with session.post(
                    "https://api.perplexity.ai/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = (
                            data.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                        )
                        if content:
                            logger.info("✅ Perplexity API returned response")
                            return content
                        logger.warning("Perplexity API returned empty content")
                        return None
                    else:
                        body = await resp.text()
                        logger.error(f"Perplexity API error {resp.status}: {body[:200]}")
                        return None

        except asyncio.TimeoutError:
            logger.error("Perplexity API timeout")
            return None
        except Exception as exc:
            logger.error(f"Perplexity API error: {exc}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Utility: safe Discord chunking
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _chunk_response(text: str, header: str = "") -> list[str]:
        chunks: list[str] = []
        limit = DISCORD_MSG_LIMIT

        if header:
            first_limit = limit - len(header)
            if first_limit <= 0:
                chunks.append(header.rstrip())
                header = ""
                first_limit = limit
            chunks.append(header + text[:first_limit])
            text = text[first_limit:]

        for i in range(0, len(text), limit):
            chunks.append(text[i: i + limit])

        return [c for c in chunks if c]

    # ─────────────────────────────────────────────────────────────────────────
    # Slash command: /chat
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name="chat", description="Chat with Gemini AI (with web search)")
    @app_commands.describe(prompt="Your question")
    async def chat(self, interaction: discord.Interaction, prompt: str) -> None:
        await interaction.response.defer(thinking=True)

        try:
            web_context = ""
            if len(prompt) > 8:
                try:
                    web_context = await get_latest_info(prompt)
                except Exception as exc:
                    logger.warning(f"Web search failed: {exc}")

            response_text = await self.get_gemini_response(
                interaction.channel_id,
                prompt,
                web_context=web_context,
                guild=interaction.guild,
            )

            await self.update_history(interaction.channel_id, prompt, response_text)

            header = f"**You:** {prompt}\n\n"
            chunks = self._chunk_response(response_text, header=header)
            await interaction.followup.send(chunks[0])
            for chunk in chunks[1:]:
                await interaction.followup.send(chunk)

        except Exception as exc:
            logger.error(f"Chat command error: {exc}", exc_info=True)
            await interaction.followup.send(f"❌ An error occurred: {_safe_err(exc)}")

    # ─────────────────────────────────────────────────────────────────────────
    # Event listener: @mentions
    # ─────────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not self.bot.user.mentioned_in(message):
            return
        if message.mention_everyone:
            return

        async with message.channel.typing():
            prompt = (
                message.content
                .replace(f"<@!{self.bot.user.id}>", "")
                .replace(f"<@{self.bot.user.id}>", "")
                .strip()
            )

            if not prompt:
                await message.channel.send(
                    "Hi! I'm powered by Google Gemini with Perplexity fallback. "
                    "How can I help?",
                    reference=message,
                )
                return

            try:
                web_context = ""
                if len(prompt) > 8:
                    try:
                        web_context = await get_latest_info(prompt)
                    except Exception as exc:
                        logger.warning(f"Web search failed: {exc}")

                response_text = await self.get_gemini_response(
                    message.channel.id,
                    prompt,
                    web_context=web_context,
                    guild=message.guild,
                )

                await self.update_history(message.channel.id, prompt, response_text)

                chunks = self._chunk_response(response_text)
                for chunk in chunks:
                    await message.channel.send(chunk, reference=message)

            except Exception as exc:
                logger.error(f"Mention handler error: {exc}", exc_info=True)
                await message.channel.send(
                    "❌ Error processing request. Please try again later.",
                    reference=message,
                )

    # ─────────────────────────────────────────────────────────────────────────
    # Slash command: /model-status (RESTORED/COMPLETED)
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name="model-status", description="Check Gemini model availability")
    async def model_status_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        lines = ["🤖 **Gemini Model Status (Rotation):**\n"]

        if not self.model_list:
            lines.append("⚠️ No models in rotation! Check logs.")
        else:
            for model in self.model_list:
                status = self.model_status.get(model, "unknown")
                emoji = (
                    "✅" if status == "available"
                    else "⚠️" if status == "quota_exceeded"
                    else "❌" if status in ("not_found", "unavailable")
                    else "❓"
                )
                lines.append(f"{emoji} `{model}`: {status}")

        removed = [
            m for m in self.raw_model_list if m not in self.model_list
        ]
        if removed:
            lines.append("\n🗑️ **Removed from rotation:**")
            for m in removed:
                st = self.model_status.get(m, "unknown")
                lines.append(f"  ❌ `{m}`: {st}")

        await interaction.followup.send("\n".join(lines), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Gemini(bot))
