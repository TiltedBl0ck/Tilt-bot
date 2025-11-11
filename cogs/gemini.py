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
model = "gemini-2.5-flash"
base_url = "https://generativelanguage.googleapis.com/v1beta"
logger.info(f"Successfully configured Google Gemini with '{model}' model.")


class Gemini(commands.Cog):
    """AI chat commands providing conversation functionality through the Google Gemini API."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # self.conversations is removed, as we will now fetch history from the channel.

    async def build_history_from_channel(self, channel: discord.TextChannel, limit: int, before: discord.Message | discord.Interaction) -> list:
        """Builds a Gemini-compatible contents list from channel history."""
        contents = []
        
        # Determine the 'before' object for history fetching
        before_message = None
        if isinstance(before, discord.Interaction):
            before_message = before.created_at
        elif isinstance(before, discord.Message):
            before_message = before.created_at

        try:
            # Fetch last 'limit' messages before the specified message/interaction
            history_messages = [msg async for msg in channel.history(limit=limit, before=before_message)]
            history_messages.reverse()  # Order from oldest to newest

            for msg in history_messages:
                # Assign role: 'model' for bot, 'user' for anyone else
                role = "model" if msg.author == self.bot.user else "user"
                
                # Use clean_content to avoid role/user mention IDs
                prompt_text = msg.clean_content
                
                # Clean up bot mentions from user messages for the AI
                if role == "user":
                    bot_mention_str = f"@{self.bot.user.name}"
                    if prompt_text.startswith(bot_mention_str):
                         prompt_text = prompt_text[len(bot_mention_str):].lstrip()

                if prompt_text: # Don't add empty messages
                    contents.append({"role": role, "parts": [{"text": prompt_text}]})
        
        except discord.Forbidden:
            logger.warning(f"Bot missing 'Read Message History' permission in {channel.name}")
            # Return empty history, but the API call will continue with the new prompt
            return []
        except Exception as e:
            logger.error(f"Error fetching channel history: {e}")
            return [] # Return empty history

        return contents


    async def get_gemini_response(self, contents: list) -> str:
        """Sends a prompt (with history) to the Google Gemini API and gets a response."""
        try:
            # Note: The 'contents' list is now built *before* calling this function.
            
            url = f"{base_url}/models/{model}:generateContent?key={GEMINI_API_KEY}"
            headers = {
                "Content-Type": "application/json",
            }
            data = {
                "contents": contents,
                # Add a system instruction to provide context to the AI
                "systemInstruction": {
                    "parts": [
                        {"text": "You are Tilt-bot, a helpful AI assistant integrated into a Discord server. The 'contents' you are receiving are a transcript of the last 20 messages from the public channel. Users are identified as 'user' and your previous responses are 'model'. Respond as a helpful assistant based on this conversation history."}
                    ]
                },
                "generationConfig": {
                    "temperature": 0.7,
                    "topK": 40,
                    "topP": 0.95,
                    "maxOutputTokens": 1024,
                },
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
                    
                    # Robust check for content parts
                    try:
                        content = response_json["candidates"][0]["content"]["parts"][0]["text"]
                        logger.info(f"Successful Gemini response generated (length: {len(content)})")
                        return content
                    except (KeyError, IndexError):
                        # This block catches errors if 'candidates', 'content', 'parts', or 'text' are missing
                        logger.warning(f"Gemini API returned no content. Full response: {response_json}")
                        
                        # Check for a "finishReason" to explain why
                        try:
                            finish_reason = response_json.get("candidates", [{}])[0].get("finishReason")
                            if finish_reason == "SAFETY":
                                return "❌ My response was blocked due to safety settings."
                            elif finish_reason == "RECITATION":
                                return "❌ My response was blocked because it was too similar to a copyrighted source."
                            else:
                                return f"❌ The AI returned an empty response (Reason: {finish_reason}). Please try again."
                        except (IndexError, KeyError):
                             return "❌ The AI returned an invalid or empty response. Please try again."

                elif response.status_code == 429:
                    logger.warning(f"Gemini API rate limit (attempt {attempt + 1}): {response.text}")
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                    continue
                else:
                    logger.error(f"Gemini API error: {response.status_code} - {response.text}")
                    return f"❌ API error (Status: {response.status_code}). Check your API key/quota."

            return "❌ Rate limited. Wait 1-2 minutes and try again (free tier: 15/min)."

        except requests.exceptions.Timeout:
            logger.error("Gemini API request timed out")
            return "❌ Request timed out. Try a shorter prompt."
        except Exception as e:
            logger.error(f"Error getting Gemini response: {e}", exc_info=True)
            return "❌ Critical error. Check bot logs."

    @app_commands.command(name="chat", description="Have a conversation with Tilt-bot's AI.")
    @app_commands.describe(prompt="What do you want to talk about?")
    async def chat(self, interaction: discord.Interaction, prompt: str):
        """Handles the AI chat command logic."""
        await interaction.response.defer(thinking=True)
        
        # Build history from the channel's last 20 messages
        contents = await self.build_history_from_channel(interaction.channel, 20, interaction)
        
        # Add the new user prompt
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        
        response_text = await self.get_gemini_response(contents)
        
        if len(response_text) > 1900:
            response_text = response_text[:1900] + "... *(truncated)*"
            
        await interaction.followup.send(f"> **You:** {prompt}\n\n**AI:** {response_text}")
        logger.info(f"Chat command used by {interaction.user} in {interaction.guild}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle mentions of the bot for AI conversations."""
        # Ignore bots and messages without a mention
        if message.author.bot or not self.bot.user.mentioned_in(message):
            return

        async with message.channel.typing():
            # Build history from the channel's last 20 messages
            contents = await self.build_history_from_channel(message.channel, 20, message)

            # Clean the prompt
            prompt = message.content.replace(f'<@!{self.bot.user.id}>', '').replace(f'<@{self.bot.user.id}>', '').strip()
            if not prompt:
                # If no prompt (e.g., just a mention), send a greeting.
                # We don't send this to Gemini to avoid a generic "Hello!" response.
                await message.channel.send("Hello! How can I help you today?", reference=message)
                return

            # Add the new user prompt to the history
            contents.append({"role": "user", "parts": [{"text": prompt}]})

            response_text = await self.get_gemini_response(contents)
            
            if len(response_text) > 1900:
                response_text = response_text[:1900] + "... *(truncated)*"
                
            await message.channel.send(response_text, reference=message)
            logger.info(f"AI mention response sent to {message.author} in {message.guild}")


async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(Gemini(bot))

