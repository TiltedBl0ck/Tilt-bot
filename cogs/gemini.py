import os
import discord
from discord import app_commands
from discord.ext import commands
import google.generativeai as genai

# --- Gemini API Setup ---
try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    # Using a standard, safe configuration for the model.
    generation_config = {
        "temperature": 0.7,
        "top_p": 1,
        "top_k": 1,
        "max_output_tokens": 2048,
    }
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    ]
    
    # --- THIS IS THE LINE WE CHANGED ---
    # We are now using the latest recommended model, gemini-1.5-flash-latest.
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash-latest",
        generation_config=generation_config,
        safety_settings=safety_settings
    )
    print("Gemini model configured successfully.")
except Exception as e:
    print(f"Error configuring Gemini model: {e}")
    model = None

class Gemini(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # A dictionary to hold ongoing conversations for each user.
        self.conversations = {}

    async def get_gemini_response(self, user_id: int, prompt: str) -> str:
        """Sends a prompt to the Gemini API and gets a response."""
        if not model:
            return "❌ The Gemini model is not configured. Please check the API key and configuration."

        try:
            # Get the user's conversation history or start a new one.
            if user_id not in self.conversations:
                self.conversations[user_id] = model.start_chat(history=[])
            
            # Use an executor to run the synchronous API call in an async-friendly way.
            # This prevents the bot from freezing while waiting for the API.
            response = await self.bot.loop.run_in_executor(
                None, self.conversations[user_id].send_message, prompt
            )
            return response.text
        except Exception as e:
            print(f"An error occurred while getting a Gemini response: {e}")
            return "❌ An error occurred while processing your request. Please try again later."

    @app_commands.command(name="chat", description="Have a conversation with Tilt-bot's AI.")
    @app_commands.describe(prompt="What do you want to talk about?")
    async def chat(self, interaction: discord.Interaction, prompt: str):
        await interaction.response.defer(thinking=True)
        response_text = await self.get_gemini_response(interaction.user.id, prompt)
        await interaction.followup.send(f"> {prompt}\n\n{response_text}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore messages from bots (including itself).
        if message.author.bot:
            return

        # Check if the bot was mentioned in the message.
        if self.bot.user.mentioned_in(message):
            # Show a "typing..." indicator to the user.
            async with message.channel.typing():
                # Clean the message content to remove the bot's mention.
                prompt = message.content.replace(f'<@!{self.bot.user.id}>', '').strip()
                prompt = message.content.replace(f'<@{self.bot.user.id}>', '').strip()

                if not prompt:
                    await message.channel.send("Hello! How can I help you today?", reference=message)
                    return

                response_text = await self.get_gemini_response(message.author.id, prompt)
                await message.channel.send(response_text, reference=message)

async def setup(bot: commands.Bot):
    await bot.add_cog(Gemini(bot))

