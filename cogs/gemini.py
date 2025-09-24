"""
Gemini AI Commands Cog for Tilt-bot

This cog provides AI chat functionality using Google's Gemini API,
allowing users to have conversations with the bot.

Author: TiltedBl0ck
Version: 2.0.0
"""

import os
import logging
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

# --- Gemini API Setup ---
try:
    import google.generativeai as genai

    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

    # Using a standard, safe configuration for the model
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

    # Using the latest recommended model
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash-latest",
        generation_config=generation_config,
        safety_settings=safety_settings
    )

    logger.info("Gemini model configured successfully.")

except ImportError:
    logger.warning("google-generativeai not installed. AI features will be disabled.")
    model = None
except Exception as e:
    logger.error(f"Error configuring Gemini model: {e}")
    model = None


class Gemini(commands.Cog):
    """
    AI chat commands cog providing conversation functionality through Google Gemini.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # A dictionary to hold ongoing conversations for each user
        self.conversations = {}

    async def get_gemini_response(self, user_id: int, prompt: str) -> str:
        """
        Sends a prompt to the Gemini API and gets a response.

        Args:
            user_id (int): The Discord user ID
            prompt (str): The user's prompt/message

        Returns:
            str: The AI's response or error message
        """
        if not model:
            return "❌ The Gemini model is not configured. Please check the API key and configuration."

        try:
            # Get the user's conversation history or start a new one
            if user_id not in self.conversations:
                self.conversations[user_id] = model.start_chat(history=[])

            # Use an executor to run the synchronous API call in an async-friendly way
            # This prevents the bot from freezing while waiting for the API
            response = await self.bot.loop.run_in_executor(
                None, self.conversations[user_id].send_message, prompt
            )

            return response.text

        except Exception as e:
            logger.error(f"An error occurred while getting a Gemini response: {e}")
            return "❌ An error occurred while processing your request. Please try again later."

    @app_commands.command(name="chat", description="Have a conversation with Tilt-bot's AI.")
    @app_commands.describe(prompt="What do you want to talk about?")
    async def chat(self, interaction: discord.Interaction, prompt: str):
        """
        Chat command that allows users to have conversations with the AI.

        Args:
            interaction (discord.Interaction): The interaction object
            prompt (str): The user's message/question
        """
        if not model:
            await interaction.response.send_message(
                "❌ AI features are not available. Please contact the bot administrator.", 
                ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)

        try:
            response_text = await self.get_gemini_response(interaction.user.id, prompt)

            # Truncate response if it's too long for Discord
            if len(response_text) > 1900:
                response_text = response_text[:1900] + "... *(response truncated)*"

            await interaction.followup.send(f"> {prompt}\n\n{response_text}")

            logger.info(f"Chat command used by {interaction.user} in {interaction.guild}")

        except Exception as e:
            logger.error(f"Error in chat command: {e}")
            await interaction.followup.send(
                "❌ An error occurred while processing your request.", 
                ephemeral=True
            )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Handle mentions of the bot for AI conversations.

        Args:
            message (discord.Message): The message object
        """
        # Ignore messages from bots (including itself)
        if message.author.bot:
            return

        # Check if the bot was mentioned in the message
        if self.bot.user.mentioned_in(message):
            if not model:
                await message.channel.send(
                    "❌ AI features are not available.", 
                    reference=message
                )
                return

            # Show a "typing..." indicator to the user
            async with message.channel.typing():
                # Clean the message content to remove the bot's mention
                prompt = message.content.replace(f'<@!{self.bot.user.id}>', '').strip()
                prompt = prompt.replace(f'<@{self.bot.user.id}>', '').strip()

                if not prompt:
                    await message.channel.send(
                        "Hello! How can I help you today?", 
                        reference=message
                    )
                    return

                try:
                    response_text = await self.get_gemini_response(message.author.id, prompt)

                    # Truncate response if it's too long for Discord
                    if len(response_text) > 1900:
                        response_text = response_text[:1900] + "... *(response truncated)*"

                    await message.channel.send(response_text, reference=message)

                    logger.info(f"AI mention response sent to {message.author} in {message.guild}")

                except Exception as e:
                    logger.error(f"Error in mention handler: {e}")
                    await message.channel.send(
                        "❌ Sorry, I encountered an error while processing your message.", 
                        reference=message
                    )


async def setup(bot: commands.Bot):
    await bot.add_cog(Gemini(bot))
