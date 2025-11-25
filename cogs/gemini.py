import logging
import discord
from discord import app_commands
from discord.ext import commands
import os
from collections import defaultdict
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from cogs.utils.web_search import get_latest_info

logger = logging.getLogger(__name__)

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY not found. AI features will not work.")
else:
    genai.configure(api_key=GEMINI_API_KEY)

class Gemini(commands.Cog):
    """AI chat with web search, conversation memory, and model fallback."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conversation_history = defaultdict(list)
        self.max_history = 15
        
        # Prioritized list of models to try
        self.model_list = [
            "gemini-2.0-flash-exp",   # Newest, fast
            "gemini-1.5-flash",       # Stable, fast, high quota
            "gemini-1.5-flash-8b",    # Extremely fast/cheap
            "gemini-1.5-pro",         # High intelligence, lower quota
            "gemini-1.0-pro"          # Legacy fallback
        ]
        
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
                    f"You are {memory.get('bot_name', 'Tilt-bot')}.",
                    f"Description: {memory.get('bot_description', 'A helpful bot')}",
                    f"Personality: {memory.get('personality', 'helpful and friendly')}",
                ]
                system_msg = "\n".join(lines)
        
        if guild and serverinfo_cog:
            try:
                guild_info = serverinfo_cog.get_guild_context(guild)
                system_msg += f"\n\nContext about the current server:\n{guild_info}"
            except Exception as e:
                logger.debug(f"Could not get guild context: {e}")
        
        return system_msg

    def format_history_for_gemini(self, history: list, system_instruction: str) -> list:
        """Convert internal dictionary history to Gemini's content format."""
        contents = []
        for msg in history:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [msg["content"]]})
        return contents

    async def get_gemini_response(self, channel_id: int, user_message: str, web_context: str = "", guild: discord.Guild = None) -> str:
        """Get response from Gemini API with fallback for rate limits."""
        if not GEMINI_API_KEY:
            return "❌ Gemini API Key is missing."

        system_instruction = self.build_system_message(guild)
        history = self.conversation_history[channel_id]
        formatted_history = self.format_history_for_gemini(history, system_instruction)
        
        final_prompt = user_message
        if web_context:
            final_prompt = f"Information from web search:\n{web_context}\n\nUser Query: {user_message}"

        # Try models in order
        for model_name in self.model_list:
            try:
                # Initialize Model
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=system_instruction,
                    safety_settings=self.safety_settings
                )

                # Start chat and generate
                chat = model.start_chat(history=formatted_history)
                response = await chat.send_message_async(final_prompt)
                
                # If we succeed, return immediately
                return response.text

            except google_exceptions.ResourceExhausted:
                logger.warning(f"Quota exceeded for {model_name}. Trying next model...")
                continue # Try next model in loop
            except Exception as e:
                # Catch 429s that might come as generic exceptions
                if "429" in str(e) or "quota" in str(e).lower():
                     logger.warning(f"Quota error (generic) for {model_name}: {e}. Trying next model...")
                     continue
                
                logger.error(f"Error with {model_name}: {e}")
                # For non-quota errors, we might want to stop or try next depending on severity.
                # Usually best to try next for robustness.
                continue

        return "⚠️ All AI models are currently overloaded or out of quota. Please try again later."

    def update_history(self, channel_id: int, user_message: str, ai_response: str):
        """Update conversation history."""
        history = self.conversation_history[channel_id]
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": ai_response})
        
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
                await message.channel.send("Hi! I'm powered by Google Gemini. How can I help?", reference=message)
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

                if len(response_text) > 2000:
                    chunks = [response_text[i:i+1900] for i in range(0, len(response_text), 1900)]
                    for chunk in chunks:
                        await message.channel.send(chunk, reference=message)
                else:
                    await message.channel.send(response_text, reference=message)
                
            except Exception as e:
                logger.error(f"Mention error: {e}")
                await message.channel.send(f"Error processing request.", reference=message)

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