import os
import logging
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

# --- Gemini API Setup ---
try:
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in .env file.")
    
    genai.configure(api_key=api_key)

    # Using the model name that was confirmed to be available in your logs.
    MODEL_NAME = "gemini-pro-latest"
    
    generation_config = {"temperature": 0.7, "top_p": 1, "top_k": 1, "max_output_tokens": 2048}
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    ]
    model = genai.GenerativeModel(model_name=MODEL_NAME, generation_config=generation_config, safety_settings=safety_settings)
    logger.info(f"Successfully configured Gemini with '{MODEL_NAME}' model.")

except (ImportError, ValueError, Exception) as e:
    logger.error(f"Error configuring Gemini model: {e}", exc_info=True)
    model = None


class Gemini(commands.Cog):
    """AI chat commands providing conversation functionality through Google Gemini."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conversations = {}

    async def get_gemini_response(self, user_id: int, prompt: str) -> str:
        """Sends a prompt to the Gemini API and gets a response."""
        if not model:
            return "❌ The Gemini model is not configured. Please check the bot's logs and configuration."

        try:
            if user_id not in self.conversations:
                self.conversations[user_id] = model.start_chat(history=[])
            
            response = await self.bot.loop.run_in_executor(None, self.conversations[user_id].send_message, prompt)
            return response.text
        except Exception as e:
            logger.error(f"An error occurred while getting a Gemini response: {e}", exc_info=True)
            if "API key not valid" in str(e):
                return "❌ The Gemini API key is invalid. Please check your .env file."
            return "❌ An error occurred while communicating with the AI. Please check the bot's logs for details."

    @app_commands.command(name="chat", description="Have a conversation with Tilt-bot's AI.")
    @app_commands.describe(prompt="What do you want to talk about?")
    async def chat(self, interaction: discord.Interaction, prompt: str):
        """Handles the AI chat command logic."""
        if not model:
            await interaction.response.send_message("❌ AI features are not available.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        response_text = await self.get_gemini_response(interaction.user.id, prompt)
        if len(response_text) > 1900:
            response_text = response_text[:1900] + "... *(response truncated)*"
        await interaction.followup.send(f"> {prompt}\n\n{response_text}")
        logger.info(f"Chat command used by {interaction.user} in {interaction.guild}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle mentions of the bot for AI conversations."""
        if message.author.bot or not self.bot.user.mentioned_in(message):
            return
        if not model:
            await message.channel.send("❌ AI features are not available.", reference=message)
            return

        async with message.channel.typing():
            prompt = message.content.replace(f'<@!{self.bot.user.id}>', '').replace(f'<@{self.bot.user.id}>', '').strip()
            if not prompt:
                await message.channel.send("Hello! How can I help you today?", reference=message)
                return
            response_text = await self.get_gemini_response(message.author.id, prompt)
            if len(response_text) > 1900:
                response_text = response_text[:1900] + "... *(response truncated)*"
            await message.channel.send(response_text, reference=message)
            logger.info(f"AI mention response sent to {message.author} in {message.guild}")


async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(Gemini(bot))

