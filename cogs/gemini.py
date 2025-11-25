import logging
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import os
from collections import defaultdict
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

# Try importing the web search, pass if missing so code still runs
try:
    from cogs.utils.web_search import get_latest_info
except ImportError:
    def get_latest_info(*args): return "" 

logger = logging.getLogger(__name__)

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY not found. Gemini AI features will not work.")
else:
    genai.configure(api_key=GEMINI_API_KEY)


class Gemini(commands.Cog):
    """AI chat with web search, conversation memory, and Google Gemini model fallback."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conversation_history = defaultdict(list)
        self.max_history = 15
        
        # UPDATED MODEL LIST (Latest as of 2025)
        # Note: Gemini 3.0 and 2.5 are not released yet. 
        # We prioritize 2.0 Flash (Newest), then 1.5 Pro (Smartest), then 1.5 Flash (Most Stable).
        self.model_list = [
            "gemini-2.0-flash",          # The actual "new" model (formerly exp)
            "gemini-2.0-flash-exp",      # Experimental version of 2.0
            "gemini-1.5-pro",            # High intelligence fallback
            "gemini-1.5-flash",          # High speed/stability fallback
            "gemini-1.5-flash-8b"        # Ultra-fast fallback
        ]
        
        self.model_status = {model: "available" for model in self.model_list}
        
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
        
        system_msg = "You are a helpful Discord bot. Provide accurate, helpful responses."
        
        if memory_cog:
            memory = memory_cog.memory
            if memory.get('system_prompt'):
                system_msg = memory.get('system_prompt')
            else:
                lines = [
                    f"You are {memory.get('bot_name', 'Bot')}.",
                    f"Description: {memory.get('bot_description', 'A helpful AI')}",
                ]
                system_msg = "\n".join(lines)
        
        if guild and serverinfo_cog:
            try:
                guild_info = serverinfo_cog.get_guild_context(guild)
                system_msg += f"\n\nContext about the current server:\n{guild_info}"
            except Exception:
                pass
        
        return system_msg

    def format_history_for_gemini(self, history: list) -> list:
        contents = []
        for msg in history:
            role = "user" if msg["role"] == "user" else "model"
            # Ensure content is never empty string, Gemini hates that
            text_content = msg["content"] if msg["content"] else "." 
            contents.append({"role": role, "parts": [text_content]})
        return contents

    async def get_gemini_response(self, channel_id: int, user_message: str, web_context: str = "", guild: discord.Guild = None) -> str:
        if not GEMINI_API_KEY:
            return "❌ Gemini API Key is missing."

        system_instruction = self.build_system_message(guild)
        history = self.conversation_history[channel_id]
        formatted_history = self.format_history_for_gemini(history)

        final_prompt = user_message
        if web_context:
            final_prompt = f"**Information from web search:**\n{web_context}\n\n**User Query:** {user_message}"

        attempted_models = []
        
        for model_name in self.model_list:
            try:
                # Setup Model
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=system_instruction,
                    safety_settings=self.safety_settings
                )
                
                chat = model.start_chat(history=formatted_history)
                
                # Execute in thread to prevent blocking Discord
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: chat.send_message(final_prompt)
                )
                
                self.model_status[model_name] = "available"
                return response.text

            except Exception as e:
                error_str = str(e).lower()
                
                # Specific handling for Rate Limits
                if "429" in error_str or "quota" in error_str or "exhausted" in error_str:
                    self.model_status[model_name] = "quota_exceeded"
                    attempted_models.append(f"{model_name} (quota)")
                
                # Specific handling for "Model not found" (Old library or bad region)
                elif "404" in error_str or "not found" in error_str:
                    self.model_status[model_name] = "not_found"
                    attempted_models.append(f"{model_name} (not found)")
                
                else:
                    logger.error(f"Error with {model_name}: {e}")
                    self.model_status[model_name] = "error"
                    attempted_models.append(f"{model_name} (error)")
                
                # Short backoff before trying next model
                await asyncio.sleep(1)
                continue

        # If we reach here, all models failed
        status_report = "\n".join(attempted_models)
        return f"⚠️ **AI Unavailable.**\n\nDebug Info:\n{status_report}\n\n*Tip: Run `pip install -U google-generativeai` to fix 'not found' errors.*"

    def update_history(self, channel_id: int, user_message: str, ai_response: str):
        history = self.conversation_history[channel_id]
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": ai_response})
        if len(history) > self.max_history * 2:
            self.conversation_history[channel_id] = history[-(self.max_history * 2):]

    @app_commands.command(name="chat", description="Chat with Gemini AI")
    @app_commands.describe(prompt="Your question")
    async def chat(self, interaction: discord.Interaction, prompt: str):
        await interaction.response.defer(thinking=True)
        try:
            web_context = ""
            if len(prompt) > 5:
                try:
                    if hasattr(get_latest_info, '__call__'):
                        web_context = await get_latest_info(prompt)
                except Exception as e:
                    logger.warning(f"Search error: {e}")

            response_text = await self.get_gemini_response(
                interaction.channel_id, prompt, web_context, interaction.guild
            )
            self.update_history(interaction.channel_id, prompt, response_text)

            if len(response_text) > 1900:
                chunks = [response_text[i:i+1900] for i in range(0, len(response_text), 1900)]
                await interaction.followup.send(f"**You:** {prompt}\n\n{chunks[0]}")
                for chunk in chunks[1:]:
                    await interaction.followup.send(chunk)
            else:
                await interaction.followup.send(f"**You:** {prompt}\n\n{response_text}")

        except Exception as e:
            await interaction.followup.send(f"Critical Error: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not self.bot.user.mentioned_in(message):
            return
        if message.mention_everyone:
            return

        async with message.channel.typing():
            prompt = message.content.replace(f'<@!{self.bot.user.id}>', '').replace(f'<@{self.bot.user.id}>', '').strip()
            
            if not prompt:
                await message.channel.send("Hi! I'm Gemini 2.0. How can I help?", reference=message)
                return

            web_context = ""
            try:
                if len(prompt.split()) > 3 and hasattr(get_latest_info, '__call__'):
                    web_context = await get_latest_info(prompt)
            except Exception:
                pass

            response_text = await self.get_gemini_response(
                message.channel.id, prompt, web_context, message.guild
            )
            self.update_history(message.channel.id, prompt, response_text)

            if len(response_text) > 2000:
                chunks = [response_text[i:i+1900] for i in range(0, len(response_text), 1900)]
                for chunk in chunks:
                    await message.channel.send(chunk, reference=message)
            else:
                await message.channel.send(response_text, reference=message)

    @app_commands.command(name="model-status", description="Check status")
    async def model_status(self, interaction: discord.Interaction):
        status_msg = "🤖 **Gemini Model Status:**\n"
        for i, model in enumerate(self.model_list, 1):
            status = self.model_status.get(model, "unknown")
            emoji = "✅" if status == "available" else "⚠️" if "quota" in status else "❌"
            status_msg += f"{emoji} `{model}`: {status}\n"
        await interaction.response.send_message(status_msg, ephemeral=True)

    @app_commands.command(name="clear-chat", description="Clear memory")
    async def clear_chat(self, interaction: discord.Interaction):
        if interaction.channel_id in self.conversation_history:
            del self.conversation_history[interaction.channel_id]
            await interaction.response.send_message("✅ Memory wiped.", ephemeral=True)
        else:
            await interaction.response.send_message("Nothing to clear.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Gemini(bot))