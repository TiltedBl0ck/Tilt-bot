import logging
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import os

logger = logging.getLogger(__name__)

# --- Puter AI Setup ---
PUTER_USERNAME = os.getenv("PUTER_USERNAME")
PUTER_PASSWORD = os.getenv("PUTER_PASSWORD")

if not PUTER_USERNAME or not PUTER_PASSWORD:
    raise ValueError("PUTER_USERNAME and PUTER_PASSWORD environment variables are required for Puter AI.")

logger.info("Successfully configured Puter AI integration.")


class Puter(commands.Cog):
    """AI chat commands providing conversation functionality through Puter's multi-model AI."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.client = None
        self._login_task = None

    async def ensure_authenticated(self):
        """Ensure Puter client is authenticated."""
        if self.client is None or not hasattr(self.client, 'is_authenticated'):
            try:
                from putergenai import PuterClient
                self.client = PuterClient()
                # Run login in executor to avoid blocking
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.client.login(PUTER_USERNAME, PUTER_PASSWORD)
                )
                logger.info("Authenticated with Puter")
            except Exception as e:
                logger.error(f"Puter authentication failed: {e}")
                raise

    async def get_puter_response(self, messages: list, model: str = "gpt-4o") -> str:
        """Get response from Puter AI."""
        await self.ensure_authenticated()

        try:
            # Run in executor to prevent blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.ai_chat(
                    messages=messages,
                    options={"model": model, "stream": False},
                    strict_model=False
                )
            )

            # Extract text from response - handle different response structures
            if isinstance(response, dict):
                content = response.get("response", {}).get("result", {}).get("message", {}).get("content", "")
                if not content:
                    # Try alternative structure
                    content = response.get("message", {}).get("content", "")
                if not content:
                    content = response.get("content", "")
            else:
                content = str(response)

            return content or "No response generated"

        except Exception as e:
            logger.error(f"Puter API error: {e}")
            return f"❌ Puter API error: {str(e)}"

    @app_commands.command(name="chat", description="Chat with Puter AI (supports 500+ models)")
    @app_commands.describe(prompt="Your question", model="AI model (default: gpt-4o)")
    async def chat(self, interaction: discord.Interaction, prompt: str, model: str = "gpt-4o"):
        """Handles chat command with Puter backend."""
        await interaction.response.defer(thinking=True)

        messages = [{"role": "user", "content": prompt}]
        response_text = await self.get_puter_response(messages, model)

        if len(response_text) > 1900:
            response_text = response_text[:1900] + "... *(truncated)*"

        await interaction.followup.send(f"> **You:** {prompt}\n\n**AI:** {response_text}")
        logger.info(f"Chat command used by {interaction.user} in {interaction.guild}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle mentions for AI conversation."""
        if message.author.bot or not self.bot.user.mentioned_in(message):
            return

        async with message.channel.typing():
            prompt = message.content.replace(f'<@!{self.bot.user.id}>', '').replace(f'<@{self.bot.user.id}>', '').strip()
            if not prompt:
                await message.channel.send("Hello! How can I help?", reference=message)
                return

            messages = [{"role": "user", "content": prompt}]
            response_text = await self.get_puter_response(messages)

            if len(response_text) > 1900:
                response_text = response_text[:1900] + "... *(truncated)*"

            await message.channel.send(response_text, reference=message)
            logger.info(f"AI mention response sent to {message.author} in {message.guild}")


async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(Puter(bot))