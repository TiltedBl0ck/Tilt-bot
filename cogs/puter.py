import logging
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import os
from collections import defaultdict

logger = logging.getLogger(__name__)

PUTER_USERNAME = os.getenv("PUTER_USERNAME")
PUTER_PASSWORD = os.getenv("PUTER_PASSWORD")

if not PUTER_USERNAME or not PUTER_PASSWORD:
    raise ValueError("PUTER_USERNAME and PUTER_PASSWORD environment variables are required for Puter AI.")

logger.info("Successfully configured Puter AI integration.")


class Puter(commands.Cog):
    """AI chat with conversation memory and personal context awareness."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.client = None
        self.conversation_history = defaultdict(list)
        self.max_history = 10
        self.memory_cog = None

    async def get_memory_cog(self):
        """Get the Memory cog for bot context."""
        if self.memory_cog is None:
            self.memory_cog = self.bot.get_cog("Memory")
        return self.memory_cog

    async def ensure_authenticated(self):
        """Ensure Puter client is authenticated."""
        if self.client is None or not hasattr(self.client, 'is_authenticated'):
            try:
                from putergenai import PuterClient
                self.client = PuterClient()
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.client.login(PUTER_USERNAME, PUTER_PASSWORD)
                )
                logger.info("Authenticated with Puter")
            except Exception as e:
                logger.error(f"Puter authentication failed: {e}")
                raise

    def get_conversation_context(self, channel_id: int, user_message: str) -> list:
        """Build conversation context with history and memory."""
        history = self.conversation_history[channel_id]
        messages = history.copy()
        
        # Add system message with bot personality (first message only)
        if not messages:
            memory_cog = self.bot.get_cog("Memory")
            if memory_cog:
                memory_context = memory_cog.get_memory_context()
                system_message = f"""You are a Discord bot. Here is your personal context:

{memory_context}

Use this context to inform your responses and maintain consistent personality. Be helpful, friendly, and engaging."""
                messages.append({"role": "system", "content": system_message})
        
        messages.append({"role": "user", "content": user_message})
        return messages

    def update_history(self, channel_id: int, user_message: str, ai_response: str):
        """Update conversation history."""
        history = self.conversation_history[channel_id]
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": ai_response})
        
        if len(history) > self.max_history:
            self.conversation_history[channel_id] = history[-self.max_history:]

    async def get_puter_response(self, messages: list, model: str = "gpt-4o") -> str:
        """Get response from Puter AI."""
        await self.ensure_authenticated()

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.ai_chat(
                    messages=messages,
                    options={"model": model, "stream": False},
                    strict_model=False
                )
            )

            if isinstance(response, dict):
                content = response.get("response", {}).get("result", {}).get("message", {}).get("content", "")
                if not content:
                    content = response.get("message", {}).get("content", "")
                if not content:
                    content = response.get("content", "")
            else:
                content = str(response)

            return content or "No response generated"

        except Exception as e:
            logger.error(f"Puter API error: {e}")
            return f"❌ Puter API error: {str(e)}"

    @app_commands.command(name="chat", description="Chat with Puter AI (with context awareness)")
    @app_commands.describe(prompt="Your question", model="AI model (default: gpt-4o)")
    async def chat(self, interaction: discord.Interaction, prompt: str, model: str = "gpt-4o"):
        """Chat command with conversation context."""
        await interaction.response.defer(thinking=True)

        messages = self.get_conversation_context(interaction.channel_id, prompt)
        response_text = await self.get_puter_response(messages, model)
        self.update_history(interaction.channel_id, prompt, response_text)

        if len(response_text) > 1900:
            response_text = response_text[:1900] + "... *(truncated)*"

        await interaction.followup.send(f"> **You:** {prompt}\n\n**AI:** {response_text}")
        logger.info(f"Chat command used by {interaction.user} in {interaction.guild}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle mentions with context awareness."""
        if message.author.bot or not self.bot.user.mentioned_in(message):
            return

        async with message.channel.typing():
            prompt = message.content.replace(f'<@!{self.bot.user.id}>', '').replace(f'<@{self.bot.user.id}>', '').strip()
            if not prompt:
                await message.channel.send("Hello! How can I help?", reference=message)
                return

            messages = self.get_conversation_context(message.channel_id, prompt)
            response_text = await self.get_puter_response(messages)
            self.update_history(message.channel_id, prompt, response_text)

            if len(response_text) > 1900:
                response_text = response_text[:1900] + "... *(truncated)*"

            await message.channel.send(response_text, reference=message)
            logger.info(f"AI mention response sent to {message.author} in {message.guild}")

    @app_commands.command(name="clear-chat", description="Clear conversation history in this channel")
    async def clear_chat(self, interaction: discord.Interaction):
        """Clear channel conversation history."""
        channel_id = interaction.channel_id
        if channel_id in self.conversation_history:
            del self.conversation_history[channel_id]
            await interaction.response.send_message("✅ Conversation history cleared.", ephemeral=True)
        else:
            await interaction.response.send_message("No history to clear.", ephemeral=True)


async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(Puter(bot))