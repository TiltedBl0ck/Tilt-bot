import os
import logging
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash-latest")
        logger.info("Gemini AI model has been successfully configured.")
    else:
        model = None
        logger.warning("GEMINI_API_KEY not found. AI features will be disabled.")
except ImportError:
    model = None
    logger.warning("google-generativeai library not found. AI features will be disabled.")

class ChatCommand(commands.Cog):
    """A command for interacting with the Gemini AI."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conversations = {}

    @app_commands.command(name="chat", description="Have a conversation with Tilt-bot's AI.")
    @app_commands.describe(prompt="What do you want to talk about?")
    async def chat(self, interaction: discord.Interaction, prompt: str):
        """Handles the AI chat command logic."""
        if not model:
            await interaction.response.send_message("❌ AI features are currently disabled by the bot owner.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        
        try:
            if interaction.user.id not in self.conversations:
                self.conversations[interaction.user.id] = model.start_chat(history=[])
            
            chat_session = self.conversations[interaction.user.id]
            response = await self.bot.loop.run_in_executor(
                None, lambda: chat_session.send_message(prompt)
            )
            
            response_text = response.text[:1900] + "..." if len(response.text) > 1900 else response.text
            await interaction.followup.send(f"> {prompt}\n\n{response_text}")
        except Exception as e:
            logger.error(f"An error occurred during Gemini chat: {e}")
            await interaction.followup.send("❌ An error occurred while communicating with the AI.", ephemeral=True)

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(ChatCommand(bot))

