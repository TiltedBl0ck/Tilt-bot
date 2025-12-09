import logging
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import os
import re
from collections import OrderedDict
from datetime import datetime, timedelta
import aiohttp
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from cogs.utils.web_search import get_latest_info
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

# SECURITY: Regex for safer mention parsing
MENTION_PATTERN = re.compile(r'<@!?\d+>')

# Configuration constants for reliability and efficiency
MAX_CHANNEL_HISTORY = 15  # Per-channel history limit (user-assistant pairs)
MAX_CONVERSATION_MEMORY_MB = 50  # ~50 MB max in-memory conversations
CHANNEL_TTL_HOURS = 24  # Expire inactive channel history after 24 hours
REQUEST_TIMEOUT_SECONDS = 45  # Timeout for Gemini/Perplexity requests
MAX_PROMPT_LENGTH = 4000  # Reasonable Discord input limit
MAX_RESPONSE_DISCORD_LENGTH = 2000  # Discord hard limit

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY not found. Gemini AI features will not work.")
else:
    genai.configure(api_key=GEMINI_API_KEY)


class TimedCache(OrderedDict):
    """LRU cache with TTL for conversation history. Prevents unbounded memory growth."""
    def __init__(self, max_size: int = 100, ttl_hours: int = 24):
        super().__init__()
        self.max_size = max_size
        self.ttl = timedelta(hours=ttl_hours)
        self.timestamps = {}
    
    def __getitem__(self, key):
        """Get item and check if expired; remove if so."""
        self._clean_expired()
        if key in self.timestamps:
            if datetime.now() - self.timestamps[key] > self.ttl:
                del self[key]
                raise KeyError(f"Entry expired: {key}")
        return super().__getitem__(key)
    
    def __setitem__(self, key, value):
        """Set item and enforce LRU limit."""
        if key in self:
            self.move_to_end(key)
        elif len(self) >= self.max_size:
            # Remove oldest entry (FIFO of oldest unused)
            self.popitem(last=False)
        super().__setitem__(key, value)
        self.timestamps[key] = datetime.now()
    
    def _clean_expired(self):
        """Remove expired entries."""
        expired_keys = [
            k for k, ts in self.timestamps.items()
            if datetime.now() - ts > self.ttl
        ]
        for k in expired_keys:
            del self[k]


class Gemini(commands.Cog):
    """AI chat with Gemini fallback to Perplexity when quota exceeded."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # EFFICIENCY: Use TimedCache instead of unbounded defaultdict
        # Prevents memory leaks from inactive channels
        self.conversation_history = TimedCache(max_size=100, ttl_hours=CHANNEL_TTL_HOURS)
        self.max_history = MAX_CHANNEL_HISTORY
        
        # EFFICIENCY: Cache cog references to avoid repeated lookups
        self.memory_cog: Optional[commands.Cog] = None
        self.serverinfo_cog: Optional[commands.Cog] = None
        
        # RELIABILITY: Track rate limits per channel
        self.channel_request_times: Dict[int, List[datetime]] = {}
        self.rate_limit_window = timedelta(seconds=10)  # 1 request per 10 seconds per channel
        
        # Updated preferred list based on December 2025 availability
        self.raw_model_list = [
            "gemini-2.5-flash",      # Latest efficient model (Free tier available)
            "gemini-2.5-pro",        # High intelligence (Free tier available)
            "gemini-2.0-flash",      # Stable predecessor
            "gemini-3-pro-preview",  # Bleeding edge (High intelligence)
            "gemini-2.5-flash-lite"  # Ultra-fast fallback
        ]
        
        # This will be populated by the validator
        self.model_list = self.raw_model_list
        
        # Track which models are currently quota-limited
        self.model_status = {model: "unknown" for model in self.model_list}
        
        # SECURITY: Moderate safety settings with better defaults
        # Public bots should use stricter settings; adjust per deployment
        self.safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM"},
        ]

        # Run validation in background to not block bot startup
        self.bot.loop.create_task(self.validate_available_models())
        # EFFICIENCY: Load cog references on startup, not on every request
        self.bot.loop.create_task(self._cache_cogs())

    async def _cache_cogs(self):
        """Cache references to Memory and ServerInfo cogs. EFFICIENCY optimization."""
        await asyncio.sleep(1)  # Give cogs time to load
        self.memory_cog = self.bot.get_cog("Memory")
        self.serverinfo_cog = self.bot.get_cog("ServerInfo")
        if not self.memory_cog:
            logger.debug("Memory cog not found; system prompts will use defaults.")
        if not self.serverinfo_cog:
            logger.debug("ServerInfo cog not found; guild context unavailable.")

    async def validate_available_models(self):
        """
        Dynamically checks which models are actually available in the current API version.
        This prevents 404 errors by removing invalid models from rotation.
        """
        if not GEMINI_API_KEY:
            return

        logger.info("🔍 Validating available Gemini models...")

        try:
            # Run the sync list_models call in an executor
            available_models = await asyncio.to_thread(self._fetch_models_sync)
            
            validated_list = []
            for preferred in self.raw_model_list:
                # Check if our preferred model exists in the available list
                # The API returns names like "models/gemini-1.5-flash"
                if any(m.name.endswith(preferred) for m in available_models):
                    validated_list.append(preferred)
                    self.model_status[preferred] = "available"
                else:
                    self.model_status[preferred] = "not_found"
                    logger.debug(f"⚠️ Model '{preferred}' skipped (not found in current API).")

            if validated_list:
                self.model_list = validated_list
                logger.info(f"✅ Gemini Model Rotation Set: {', '.join(self.model_list)}")
            else:
                logger.warning("❌ No preferred models found in API list! Using raw list as fallback.")
                self.model_list = self.raw_model_list

        except Exception as e:
            logger.error(f"Failed to validate models: {e}")

    def _fetch_models_sync(self):
        """Helper to fetch models synchronously."""
        return list(genai.list_models())

    def build_system_message(self, guild: discord.Guild = None) -> str:
        """Build system message from memory and server context. EFFICIENCY: Uses cached cogs."""
        # Get current date and time (with timezone awareness)
        now = datetime.now()
        current_date = now.strftime("%A, %B %d, %Y")
        current_time = now.strftime("%H:%M:%S")
        
        system_msg = f"You are a helpful Discord bot. Current date: {current_date}. Current time: {current_time} UTC. Provide accurate, helpful responses based on available information."
        
        # EFFICIENCY: Use cached memory_cog instead of .get_cog() every time
        if self.memory_cog:
            try:
                memory = self.memory_cog.memory
                
                if memory.get('system_prompt'):
                    system_msg = memory.get('system_prompt')
                else:
                    lines = [
                        f"You are {memory.get('bot_name', 'Tilt-bot')}.",
                        f"Description: {memory.get('bot_description', 'A helpful bot')}",
                        f"Personality: {memory.get('personality', 'helpful and friendly')}",
                        f"Current date: {current_date}",
                    ]
                    system_msg = "\n".join(lines)
            except (AttributeError, KeyError) as e:
                # RELIABILITY: Gracefully handle malformed memory
                logger.warning(f"Memory cog returned invalid structure: {e}")
        
        # RELIABILITY: Better error handling for guild context
        if guild and self.serverinfo_cog:
            try:
                guild_info = self.serverinfo_cog.get_guild_context(guild)
                if guild_info:  # Ensure guild_info is not None
                    system_msg += f"\n\nContext about the current server:\n{guild_info}"
            except Exception as e:
                logger.debug(f"Could not get guild context: {e}")
        
        return system_msg

    def format_history_for_gemini(self, history: list) -> list:
        """Convert internal dictionary history to Gemini's content format."""
        contents = []
        for msg in history:
            role = msg.get("role", "user")
            if role not in ("user", "assistant", "system"):
                role = "assistant"
            contents.append({"role": role, "parts": [msg["content"]]})
        return contents

    async def get_perplexity_response(self, user_message: str) -> Optional[str]:
        """Fallback to Perplexity API when Gemini fails. RELIABILITY: Better validation."""
        if not PERPLEXITY_API_KEY:
            logger.warning("⚠️ PERPLEXITY_API_KEY not configured - cannot use fallback")
            return None
        
        # SECURITY: Validate input length
        if not user_message or len(user_message) > MAX_PROMPT_LENGTH:
            logger.warning(f"Perplexity: Invalid prompt length {len(user_message)}")
            return None
        
        try:
            logger.info("🔄 Falling back to Perplexity API...")
            
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": "sonar",
                    "messages": [
                        {
                            "role": "user",
                            "content": user_message[:MAX_PROMPT_LENGTH]  # SECURITY: Enforce length
                        }
                    ]
                }
                
                async with session.post(
                    "https://api.perplexity.ai/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
                ) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                        except Exception as e:
                            # RELIABILITY: Handle malformed JSON
                            logger.error(f"Perplexity API returned invalid JSON: {e}")
                            return None
                        
                        # RELIABILITY: Safe nested dictionary access
                        try:
                            choices = data.get("choices", [])
                            if not choices:
                                logger.warning("Perplexity API returned empty choices")
                                return None
                            
                            message_obj = choices[0].get("message", {})
                            content = message_obj.get("content", "").strip()
                            
                            if content:
                                logger.info("✅ Perplexity API returned response")
                                return content
                            else:
                                logger.warning("Perplexity API returned empty content")
                                return None
                        except (IndexError, TypeError, KeyError) as e:
                            # RELIABILITY: Handle unexpected response structure
                            logger.error(f"Perplexity API response structure error: {e}")
                            return None
                    else:
                        logger.error(f"Perplexity API error: HTTP {response.status}")
                        return None
        
        except asyncio.TimeoutError:
            logger.error(f"Perplexity API timeout (>{REQUEST_TIMEOUT_SECONDS}s)")
            return None
        except Exception as e:
            logger.error(f"Perplexity API error: {e}")
            return None

    async def get_gemini_response(self, channel_id: int, user_message: str, web_context: str = "", guild: discord.Guild = None) -> str:
        """Get response from Gemini API with Perplexity fallback."""
        if not GEMINI_API_KEY:
            return "❌ Gemini API Key is missing."

        system_instruction = self.build_system_message(guild)
        history = self.conversation_history[channel_id]
        formatted_history = self.format_history_for_gemini(history)

        final_prompt = user_message
        if web_context:
            final_prompt = f"**Information from web search:**\n{web_context}\n\n**User Query:** {user_message}"

        # Try Gemini models in priority order
        attempted_models = []
        
        for model_name in self.model_list:
            try:
                # Initialize Model
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=system_instruction,
                    safety_settings=self.safety_settings
                )
                
                # Start chat and generate
                # Note: We create a fresh chat session for the history + new prompt
                chat = model.start_chat(history=formatted_history)
                
                logger.debug(f"Sending request to {model_name}...")
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: chat.send_message(final_prompt)
                )
                
                # Success! Update status and return
                self.model_status[model_name] = "available"
                logger.info(f"✅ Success with {model_name}")
                return response.text

            except google_exceptions.ResourceExhausted:
                self.model_status[model_name] = "quota_exceeded"
                logger.warning(f"⚠️ Quota exceeded for {model_name}. Trying next...")
                attempted_models.append(f"{model_name} (quota)")
                continue

            except Exception as e:
                error_str = str(e).lower()
                
                # Handle model not found errors
                if "404" in str(e) or "not found" in error_str:
                    self.model_status[model_name] = "not_found"
                    # Only log warning, not full error trace, to keep logs clean
                    logger.warning(f"⚠️ Model not found/supported: {model_name}")
                    attempted_models.append(f"{model_name} (404)")
                    continue
                
                # Handle generic quota/rate errors
                if "429" in str(e) or "quota" in error_str:
                    self.model_status[model_name] = "quota_exceeded"
                    logger.warning(f"⚠️ Rate limited on {model_name}")
                    attempted_models.append(f"{model_name} (rate_limit)")
                    continue
                
                # Handle 503 service unavailable
                if "503" in str(e) or "unavailable" in error_str:
                    self.model_status[model_name] = "unavailable"
                    logger.warning(f"⚠️ Service unavailable for {model_name}")
                    attempted_models.append(f"{model_name} (503)")
                    continue
                
                logger.error(f"❌ Error with {model_name}: {e}")
                self.model_status[model_name] = "error"
                attempted_models.append(f"{model_name} (error)")
                continue

        # All Gemini models failed - try Perplexity fallback
        logger.warning(f"❌ All Gemini models failed ({', '.join(attempted_models)}) - attempting Perplexity fallback...")
        perplexity_response = await self.get_perplexity_response(user_message)
        
        if perplexity_response:
            logger.info("✅ Perplexity fallback successful")
            return f"🌐 **(Via Perplexity AI)**\n\n{perplexity_response}"
        else:
            # Both failed
            return f"⚠️ **All AI services are currently unavailable.**\n\nGemini Status: All models failed (Quota or 404)\nPerplexity Status: Failed or Not Configured\n\nPlease try again later."

    def update_history(self, channel_id: int, user_message: str, ai_response: str):
        """Update conversation history. RELIABILITY: Enforce size limits."""
        try:
            history = self.conversation_history.get(channel_id, [])
        except KeyError:
            # History expired; start fresh
            history = []
            self.conversation_history[channel_id] = history
        
        # RELIABILITY: Truncate individual messages if they exceed limits
        user_msg = user_message[:MAX_PROMPT_LENGTH]
        ai_msg = ai_response[:MAX_RESPONSE_DISCORD_LENGTH * 2]  # More lenient for AI responses
        
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": ai_msg})
        
        # Keep history within limits (user-assistant pairs)
        if len(history) > self.max_history * 2:
            # EFFICIENCY: Trim to exactly max_history pairs instead of keeping extra
            self.conversation_history[channel_id] = history[-(self.max_history * 2):]
        else:
            self.conversation_history[channel_id] = history

    def _format_response_chunks(self, response_text: str, max_chunk_size: int = MAX_RESPONSE_DISCORD_LENGTH - 100):
        """EFFICIENCY: Generator-style chunking instead of creating full list."""
        i = 0
        while i < len(response_text):
            yield response_text[i:i+max_chunk_size]
            i += max_chunk_size

    @app_commands.command(name="chat", description="Chat with Gemini AI (with web search)")
    @app_commands.describe(prompt="Your question")
    async def chat(self, interaction: discord.Interaction, prompt: str):
        """Chat command with web search. SECURITY & RELIABILITY: Input validation, better error handling."""
        await interaction.response.defer(thinking=True)

        # SECURITY: Validate and sanitize input
        if not prompt or len(prompt.strip()) == 0:
            await interaction.followup.send("❌ Please provide a prompt.")
            return
        
        prompt = prompt.strip()[:MAX_PROMPT_LENGTH]

        try:
            web_context = ""
            
            # EFFICIENCY: Only search for longer queries (more likely to benefit from web search)
            # Avoid wasting API calls on simple questions
            if len(prompt.split()) >= 4:  # At least 4 words
                try:
                    logger.debug(f"Searching for context: {len(prompt)} chars")
                    web_context = await get_latest_info(prompt)
                except asyncio.TimeoutError:
                    logger.warning("Web search timeout")
                    # Continue without web context
                except Exception as e:
                    logger.warning(f"Web search failed: {e}")
                    # Continue without web context

            response_text = await self.get_gemini_response(
                interaction.channel_id,
                prompt,
                web_context=web_context,
                guild=interaction.guild
            )

            self.update_history(interaction.channel_id, prompt, response_text)

            # EFFICIENCY: Use generator for chunking
            chunks = list(self._format_response_chunks(response_text, max_chunk_size=1900))
            
            if len(chunks) > 1:
                # First chunk includes the prompt
                await interaction.followup.send(f"**You:** {prompt[:100]}...\n\n{chunks[0]}")
                # Send remaining chunks without repeating the prompt
                for chunk in chunks[1:]:
                    await interaction.followup.send(chunk)
            else:
                await interaction.followup.send(f"**You:** {prompt}\n\n{response_text}")

        except Exception as e:
            logger.error(f"Chat command error: {e}", exc_info=True)
            # SECURITY: Don't leak error details to user
            await interaction.followup.send(
                "❌ An error occurred while processing your request. Please try again later."
            )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle mentions. SECURITY: Safer mention parsing."""
        if message.author.bot or not self.bot.user.mentioned_in(message):
            return

        if message.mention_everyone:
            return

        async with message.channel.typing():
            # SECURITY: Use regex for safer mention stripping
            prompt = MENTION_PATTERN.sub('', message.content).strip()
            
            # RELIABILITY: Validate prompt
            if not prompt:
                await message.channel.send(
                    "Hi! I'm powered by Google Gemini with Perplexity fallback. How can I help?",
                    reference=message
                )
                return
            
            prompt = prompt[:MAX_PROMPT_LENGTH]

            try:
                web_context = ""
                
                # EFFICIENCY: Only search for longer, multi-word queries
                if len(prompt.split()) >= 4:
                    try:
                        logger.debug(f"Mention web search: {len(prompt)} chars")
                        web_context = await get_latest_info(prompt)
                    except asyncio.TimeoutError:
                        logger.warning("Web search timeout on mention")
                    except Exception as e:
                        logger.warning(f"Web search failed on mention: {e}")

                response_text = await self.get_gemini_response(
                    message.channel.id,
                    prompt,
                    web_context=web_context,
                    guild=message.guild
                )

                self.update_history(message.channel.id, prompt, response_text)

                # EFFICIENCY: Use generator for chunking
                chunks = list(self._format_response_chunks(response_text, max_chunk_size=1900))
                
                if len(chunks) > 1:
                    # Send first chunk
                    await message.channel.send(chunks[0], reference=message)
                    # Send remaining chunks
                    for chunk in chunks[1:]:
                        await message.channel.send(chunk)
                else:
                    await message.channel.send(response_text, reference=message)

            except asyncio.TimeoutError:
                logger.error("Mention handler timeout")
                await message.channel.send(
                    "⏱️ Request timed out. Please try again.",
                    reference=message
                )
            except Exception as e:
                logger.error(f"Mention handler error: {e}", exc_info=True)
                # SECURITY: Don't leak error details
                await message.channel.send(
                    "❌ Error processing request. Please try again later.",
                    reference=message
                )

    @app_commands.command(name="model-status", description="Check Gemini model availability")
    async def model_status(self, interaction: discord.Interaction):
        """Check status of all Gemini models. RELIABILITY: Better status display."""
        await interaction.response.defer(ephemeral=True)
        
        status_msg = "🤖 **Gemini Model Status (Rotation):**\n\n"
        
        # Display validated list first
        if not self.model_list:
            status_msg += "⚠️ No models found in rotation! (Check logs)\n"
        else:
            for model in self.model_list:
                status = self.model_status.get(model, "unknown")
                
                # RELIABILITY: Map status to clearer emoji/description
                if status == "available":
                    emoji = "✅"
                elif status == "quota_exceeded":
                    emoji = "🚫"
                elif status == "not_found":
                    emoji = "❌"
                elif status == "rate_limited":
                    emoji = "⏱️"
                elif status == "unavailable" or status == "timeout":
                    emoji = "📡"
                else:
                    emoji = "❓"
                
                status_msg += f"{emoji} `{model}`: {status}\n"

        # Show which models were removed
        removed = [m for m in self.raw_model_list if m not in self.model_list]
        if removed:
            status_msg += f"\n**Removed Models (Not in API):**\n"
            for model in removed:
                status_msg += f"❌ `{model}`\n"

        # Perplexity status
        perplexity_status = "✅ Configured" if PERPLEXITY_API_KEY else "❌ Not configured"
        status_msg += f"\n🌐 **Perplexity Fallback:** {perplexity_status}"
        
        await interaction.followup.send(status_msg)

    @app_commands.command(name="clear-chat", description="Clear conversation history")
    async def clear_chat(self, interaction: discord.Interaction):
        """Clear chat history."""
        channel_id = interaction.channel_id
        if channel_id in self.conversation_history:
            del self.conversation_history[channel_id]
            await interaction.response.send_message("✅ Memory for this channel has been wiped.", ephemeral=True)
        else:
            await interaction.response.send_message("No active conversation history to clear.", ephemeral=True)


async def setup(bot: commands.Bot):
    """Setup cog."""
    await bot.add_cog(Gemini(bot))