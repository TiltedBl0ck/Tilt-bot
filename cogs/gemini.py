import logging
import discord
from discord import app_commands
from discord.ext import commands
import requests
import json
import asyncio
import os  # For env var access

logger = logging.getLogger(__name__)

# --- Google Gemini API Setup ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is required for Gemini API.")
model = "gemini-2.5-flash"  # Updated to current stable free model (replaces deprecated gemini-1.5-flash)
base_url = "https://generativelanguage.googleapis.com/v1beta"
logger.info(f"Successfully configured Google Gemini with '{model}' model.")


class Gemini(commands.Cog):
    """AI chat commands providing conversation functionality through the Google Gemini API."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conversations = {}

    def build_contents(self, user_id: int, prompt: str) -> list:
        """Builds multi-turn contents from conversation history for better context."""
        if user_id not in self.conversations:
            return [{"role": "user", "parts": [{"text": prompt}]}]

        history = self.conversations[user_id]
        # Limit to last 10 exchanges to avoid token limits
        recent_history = history[-10:] if len(history) > 10 else history
        contents = []
        for msg in recent_history:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        # Add the new user prompt
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        return contents

    async def get_gemini_response(self, user_id: int, prompt: str) -> str:
        """Sends a prompt to the Google Gemini API and gets a response."""
        try:
            contents = self.build_contents(user_id, prompt)

            url = f"{base_url}/models/{model}:generateContent?key={GEMINI_API_KEY}"
            headers = {
                "Content-Type": "application/json",
            }
            data = {
                "contents": contents,
                "generationConfig": {
                    "temperature": 0.7,
                    "topK": 40,
                    "topP": 0.95,
                    "maxOutputTokens": 1024,
                },
                # Optional: Add safety settings if needed
                "safetySettings": [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                ],
            }

            # Retry loop for rate limits (429)
            for attempt in range(3):
                response = await self.bot.loop.run_in_executor(
                    None,
                    lambda: requests.post(url, headers=headers, data=json.dumps(data), timeout=30)
                )

                if response.status_code == 200:
                    response_json = response.json()
                    if "candidates" in response_json and len(response_json["candidates"]) > 0:
                        content = response_json["candidates"][0]["content"]["parts"][0]["text"]
                        # Update history
                        if user_id not in self.conversations:
                            self.conversations[user_id] = []
                        self.conversations[user_id].append({"role": "user", "content": prompt})
                        self.conversations[user_id].append({"role": "assistant", "content": content})
                        logger.info(f"Successful Gemini response for user {user_id} (length: {len(content)})")
                        return content
                    else:
                        raise ValueError("No candidates in Gemini response")
                elif response.status_code == 429:
                    logger.warning(f"Gemini API rate limit (attempt {attempt + 1}): {response.text}")
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                    continue
                else:
                    logger.error(f"Gemini API error: {response.status_code} - {response.text}")
                    self.conversations.pop(user_id, None)
                    return f"❌ API error (Status: {response.status_code}). Check your API key/quota."

            self.conversations.pop(user_id, None)
            return "❌ Rate limited. Wait 1-2 minutes and try again (free tier: 15/min)."

        except requests.exceptions.Timeout:
            logger.error("Gemini API request timed out")
            self.conversations.pop(user_id, None)
            return "❌ Request timed out. Try a shorter prompt."
        except Exception as e:
            logger.error(f"Error getting Gemini response: {e}", exc_info=True)
            self.conversations.pop(user_id, None)
            return "❌ Critical error. Check bot logs."

    @app_commands.command(name="chat", description="Have a conversation with Tilt-bot's AI.")
    @app_commands.describe(prompt="What do you want to talk about?")
    async def chat(self, interaction: discord.Interaction, prompt: str):
        """Handles the AI chat command logic."""
        await interaction.response.defer(thinking=True)
        response_text = await self.get_gemini_response(interaction.user.id, prompt)
        if len(response_text) > 1900:
            response_text = response_text[:1900] + "... *(truncated)*"
        await interaction.followup.send(f"> **You:** {prompt}\n\n**AI:** {response_text}")
        logger.info(f"Chat command used by {interaction.user} in {interaction.guild}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle mentions of the bot for AI conversations."""
        if message.author.bot or not self.bot.user.mentioned_in(message):
            return

        async with message.channel.typing():
            prompt = message.content.replace(f'<@!{self.bot.user.id}>', '').replace(f'<@{self.bot.user.id}>', '').strip()
            if not prompt:
                await message.channel.send("Hello! How can I help you today?", reference=message)
                return
            response_text = await self.get_gemini_response(message.author.id, prompt)
            if len(response_text) > 1900:
                response_text = response_text[:1900] + "... *(truncated)*"
            await message.channel.send(response_text, reference=message)
            logger.info(f"AI mention response sent to {message.author} in {message.guild}")


async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(Gemini(bot))