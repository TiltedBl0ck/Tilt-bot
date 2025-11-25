import logging
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import os
from collections import defaultdict
from datetime import datetime
import aiohttp
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from cogs.utils.web_search import get_latest_info

logger = logging.getLogger(__name__)

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY not found. Gemini AI features will not work.")
else:
    genai.configure(api_key=GEMINI_API_KEY)


class Gemini(commands.Cog):
    """AI chat with Gemini fallback to Perplexity when quota exceeded."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conversation_history = defaultdict(list)
        self.max_history = 15
        
        # Prioritized list of Google's free models (newest first)
        self.model_list = [
            "gemini-2.0-flash-exp",      # Newest, fastest, best for free tier
            "gemini-1.5-flash",          # Stable, fast, high quota
            "gemini-1.5-flash-8b",       # Lightweight, extremely fast
            "gemini-1.5-pro",            # High intelligence, lower quota
            "gemini-1.0-pro"             # Legacy fallback
        ]
        
        # Track which models are currently quota-limited
        self.model_status = {model: "available" for model in self.model_list}
        self.current_preferred_model = 0
        
        # Safety settings (permissive for Discord bot context)
        self.safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

    def build_system_message(self, guild: discord.Guild = None) -> str:
        """Build system message from memory and server context."""
        memory_cog = self.bot.get_cog("Memory")
        serverinfo_cog = self.bot.get_cog("ServerInfo")
        
        # Get current date and time
        now = datetime.now()
        current_date = now.strftime("%A, %B %d, %Y")
        current_time = now.strftime("%H:%M:%S %Z")
        
        system_msg = f"You are a helpful Discord bot. Current date: {current_date}. Current time: {current_time}. Provide accurate, helpful responses based on available information."
        
        if memory_cog:
            memory = memory_cog.memory
            
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
        
        if guild and serverinfo_cog:
            try:
                guild_info = serverinfo_cog.get_guild_context(guild)
                system_msg += f"\n\nContext about the current server:\n{guild_info}"
            except Exception as e:
                logger.debug(f"Could not get guild context: {e}")
        
        return system_msg

    def format_history_for_gemini(self, history: list) -> list:
        """Convert internal dictionary history to Gemini's content format."""
        contents = []
        for msg in history:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [msg["content"]]})
        return contents

    async def get_perplexity_response(self, user_message: str) -> str:
        """Fallback to Perplexity API when Gemini fails."""
        if not PERPLEXITY_API_KEY:
            logger.warning("⚠️ PERPLEXITY_API_KEY not configured - cannot use fallback")
            return None
        
        try:
            logger.info(f"🔄 Falling back to Perplexity API...")
            
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
                            "content": user_message
                        }
                    ]
                }
                
                async with session.post(
                    "https://api.perplexity.ai/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        
                        if content:
                            logger.info(f"✅ Perplexity API returned response")
                            return content
                        else:
                            logger.warning("Perplexity API returned empty content")
                            return None
                    else:
                        logger.error(f"Perplexity API error: {response.status}")
                        return None
        
        except asyncio.TimeoutError:
            logger.error("Perplexity API timeout")
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
        for i, model_name in enumerate(self.model_list):
            try:
                logger.info(f"Trying Gemini model: {model_name}")
                
                # Initialize Model
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=system_instruction,
                    safety_settings=self.safety_settings
                )
                
                # Start chat and generate
                chat = model.start_chat(history=formatted_history)
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
                logger.warning(f"⚠️ Quota exceeded for {model_name}. Trying next model...")
                attempted_models.append(f"{model_name} (quota)")
                continue

            except Exception as e:
                error_str = str(e).lower()
                
                # Handle generic 429 quota errors
                if "429" in str(e) or "quota" in error_str or "rate" in error_str:
                    self.model_status[model_name] = "quota_exceeded"
                    logger.warning(f"⚠️ Rate limited on {model_name}: {e}")
                    attempted_models.append(f"{model_name} (rate_limit)")
                    continue
                
                # Handle 503 service unavailable
                if "503" in str(e) or "unavailable" in error_str:
                    self.model_status[model_name] = "unavailable"
                    logger.warning(f"⚠️ Service unavailable for {model_name}")
                    attempted_models.append(f"{model_name} (unavailable)")
                    continue
                
                logger.error(f"❌ Error with {model_name}: {e}")
                self.model_status[model_name] = "error"
                attempted_models.append(f"{model_name} (error)")
                continue

        # All Gemini models failed - try Perplexity fallback
        logger.warning(f"❌ All Gemini models failed - attempting Perplexity fallback...")
        perplexity_response = await self.get_perplexity_response(user_message)
        
        if perplexity_response:
            logger.info("✅ Perplexity fallback successful")
            return f"🌐 **(Via Perplexity AI)**\n\n{perplexity_response}"
        else:
            # Both failed
            status_report = "\n".join(attempted_models) if attempted_models else "All models failed"
            logger.error(f"❌ All AI services failed (Gemini + Perplexity)")
            return f"⚠️ **All AI services are currently unavailable.**\n\nGemini attempted:\n{status_report}\n\nPerplexity: Not available or no API key configured\n\nPlease try again in a few moments."

    def update_history(self, channel_id: int, user_message: str, ai_response: str):
        """Update conversation history."""
        history = self.conversation_history[channel_id]
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": ai_response})
        
        # Keep history within limits
        if len(history) > self.max_history * 2:
            self.conversation_history[channel_id] = history[-(self.max_history * 2):]

    @app_commands.command(name="chat", description="Chat with Gemini AI (with web search)")
    @app_commands.describe(prompt="Your question")
    async def chat(self, interaction: discord.Interaction, prompt: str):
        """Chat command with web search."""
        await interaction.response.defer(thinking=True)

        try:
            web_context = ""
            try:
                if len(prompt) > 5:
                    logger.info(f"Searching for: {prompt}")
                    web_context = await get_latest_info(prompt)
            except Exception as e:
                logger.warning(f"Web search failed: {e}")

            response_text = await self.get_gemini_response(
                interaction.channel_id,
                prompt,
                web_context=web_context,
                guild=interaction.guild
            )

            self.update_history(interaction.channel_id, prompt, response_text)

            # Split response into chunks if too long
            if len(response_text) > 1900:
                chunks = [response_text[i:i+1900] for i in range(0, len(response_text), 1900)]
                await interaction.followup.send(f"**You:** {prompt}\n\n{chunks[0]}")
                for chunk in chunks[1:]:
                    await interaction.followup.send(chunk)
            else:
                await interaction.followup.send(f"**You:** {prompt}\n\n{response_text}")

        except Exception as e:
            logger.error(f"Chat error: {e}")
            await interaction.followup.send(f"Error: {str(e)[:100]}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle mentions."""
        if message.author.bot or not self.bot.user.mentioned_in(message):
            return

        if message.mention_everyone:
            return

        async with message.channel.typing():
            prompt = message.content.replace(f'<@!{self.bot.user.id}>', '').replace(f'<@{self.bot.user.id}>', '').strip()
            
            if not prompt:
                await message.channel.send("Hi! I'm powered by Google Gemini with Perplexity fallback. How can I help?", reference=message)
                return

            try:
                web_context = ""
                try:
                    if len(prompt.split()) > 3:
                        web_context = await get_latest_info(prompt)
                except Exception as e:
                    logger.warning(f"Web search failed: {e}")

                response_text = await self.get_gemini_response(
                    message.channel.id,
                    prompt,
                    web_context=web_context,
                    guild=message.guild
                )

                self.update_history(message.channel.id, prompt, response_text)

                # Split response into chunks if too long
                if len(response_text) > 2000:
                    chunks = [response_text[i:i+1900] for i in range(0, len(response_text), 1900)]
                    for chunk in chunks:
                        await message.channel.send(chunk, reference=message)
                else:
                    await message.channel.send(response_text, reference=message)

            except Exception as e:
                logger.error(f"Mention error: {e}")
                await message.channel.send(f"Error processing request.", reference=message)

    @app_commands.command(name="model-status", description="Check Gemini model availability")
    async def model_status(self, interaction: discord.Interaction):
        """Check status of all Gemini models."""
        await interaction.response.defer(ephemeral=True)
        
        status_msg = "🤖 **Gemini Model Status:**\n\n"
        for i, model in enumerate(self.model_list, 1):
            status = self.model_status.get(model, "unknown")
            emoji = "✅" if status == "available" else "⚠️" if "quota" in status else "❌"
            status_msg += f"{emoji} {i}. `{model}` - {status}\n"
        
        status_msg += f"\n🌐 **Perplexity Fallback:** {'✅ Configured' if PERPLEXITY_API_KEY else '❌ Not configured'}"
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