import logging
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import os
from collections import defaultdict
import time
from cogs.utils.web_search import web_search, search_and_summarize

logger = logging.getLogger(__name__)

PUTER_USERNAME = os.getenv("PUTER_USERNAME")
PUTER_PASSWORD = os.getenv("PUTER_PASSWORD")

if not PUTER_USERNAME or not PUTER_PASSWORD:
    raise ValueError("PUTER_USERNAME and PUTER_PASSWORD environment variables are required for Puter AI.")

logger.info("Successfully configured Puter AI integration.")


class Puter(commands.Cog):
    """AI chat with web search, conversation memory, personal context, and server awareness."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.client = None
        self.conversation_history = defaultdict(list)
        self.max_history = 10
        self.memory_cog = None
        self.serverinfo_cog = None
        self.last_login_time = 0
        self.login_cooldown = 3600  # 1 hour cooldown between logins
        
        # Available models on Puter API
        self.available_models = [
            "gpt-4o",                    # Default - best quality
            "gpt-4o-mini",               # Lightweight, fast
            "claude-3-5-sonnet-20241022", # Alternative
            "meta-llama/Llama-3.3-70B-Instruct-Turbo"  # Open source
        ]

    async def ensure_authenticated(self):
        """Ensure Puter client is authenticated (with caching)."""
        current_time = time.time()
        
        # If client exists and recent login, reuse it
        if self.client is not None and (current_time - self.last_login_time) < self.login_cooldown:
            logger.debug("Reusing cached Puter client")
            return
        
        try:
            from putergenai import PuterClient
            self.client = PuterClient()
            
            # Run login in executor to avoid blocking
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.login(PUTER_USERNAME, PUTER_PASSWORD)
            )
            
            self.last_login_time = current_time
            logger.info("Authenticated with Puter (new token cached)")
            
        except Exception as e:
            logger.error(f"Puter authentication failed: {e}")
            self.client = None
            self.last_login_time = 0
            raise

    def build_system_message(self, guild: discord.Guild = None) -> str:
        """Build complete system message from memory and server context."""
        memory_cog = self.bot.get_cog("Memory")
        serverinfo_cog = self.bot.get_cog("ServerInfo")
        
        if not memory_cog:
            return "You are a helpful Discord bot assistant with access to web search data."
        
        memory = memory_cog.memory
        
        # Start with memory-based prompt
        if memory.get('system_prompt'):
            system_msg = memory.get('system_prompt')
        else:
            lines = [
                f"You are {memory.get('bot_name', 'a Discord bot')}.",
                f"Description: {memory.get('bot_description', 'A helpful bot')}",
                f"Personality: {memory.get('personality', 'helpful and friendly')}",
                f"Creator: {memory.get('owner', 'Unknown')}",
            ]
            
            facts = memory.get('custom_facts', [])
            if facts:
                lines.append("\nAbout yourself:")
                for fact in facts:
                    lines.append(f"- {fact}")
            
            system_msg = "\n".join(lines)
        
        # Add server context if available
        if guild and serverinfo_cog:
            try:
                guild_info = serverinfo_cog.get_guild_context(guild)
                system_msg += f"\n\nServer Context:\n{guild_info}"
                system_msg += "\n\nYou can reference channels, roles, and members of this server in your responses."
            except Exception as e:
                logger.debug(f"Could not get guild context: {e}")
        
        system_msg += "\n\nYou have access to web search data. Use it to provide up-to-date information when available. Always stay in character and respond helpfully to server members."
        
        return system_msg

    def get_conversation_context(self, channel_id: int, user_message: str, web_context: str = "", guild: discord.Guild = None) -> list:
        """Build conversation context with history, memory, server data, and web search results."""
        history = self.conversation_history[channel_id]
        
        # ALWAYS include system message first (with guild context)
        system_msg = self.build_system_message(guild)
        
        # Add web search context if available
        if web_context:
            system_msg += f"\n\nRecent Web Search Results:\n{web_context}"
        
        messages = [{"role": "system", "content": system_msg}]
        
        # Add conversation history (without system message)
        for msg in history:
            if msg.get("role") != "system":
                messages.append(msg)
        
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        return messages

    def update_history(self, channel_id: int, user_message: str, ai_response: str):
        """Update conversation history."""
        history = self.conversation_history[channel_id]
        
        # Don't store system messages in history, only user/assistant
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": ai_response})
        
        if len(history) > self.max_history:
            self.conversation_history[channel_id] = history[-self.max_history:]

    async def get_puter_response(self, messages: list, model: str = "gpt-4o", attempt: int = 0) -> str:
        """Get response from Puter AI with fallback support."""
        try:
            await self.ensure_authenticated()
            
            if self.client is None:
                return "❌ Failed to authenticate with Puter. Please check your credentials."

            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: self.client.ai_chat(
                        messages=messages,
                        options={"model": model, "stream": False},
                        strict_model=False
                    )
                ),
                timeout=30.0  # 30 second timeout
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
            error_msg = str(e).lower()
            
            # Content moderation error - try next model
            if "content moderation failed" in error_msg or "moderation" in error_msg:
                logger.warning(f"Content moderation failed on model {model}, attempting fallback")
                
                if attempt < len(self.available_models):
                    fallback_model = self.available_models[attempt]
                    logger.info(f"Retrying with fallback model: {fallback_model}")
                    return await self.get_puter_response(messages, fallback_model, attempt + 1)
                else:
                    return "⚠️ Your message was flagged by content moderation. Please try rephrasing it and avoiding sensitive language."
            
            # Model not available - try next one
            if "invalid" in error_msg or "not found" in error_msg or "not available" in error_msg:
                logger.warning(f"Model {model} invalid, attempting fallback")
                
                if attempt < len(self.available_models):
                    fallback_model = self.available_models[attempt]
                    logger.info(f"Trying fallback model: {fallback_model}")
                    return await self.get_puter_response(messages, fallback_model, attempt + 1)
                else:
                    return "❌ All available models failed. Please check Puter API."
            
            # Timeout error
            if "timeout" in error_msg:
                logger.error("Puter API timeout")
                return "❌ Puter API took too long to respond. Please try again."
            
            # Other errors
            logger.error(f"Puter API error: {e}")
            return f"❌ Puter API error: {str(e)[:100]}"

    @app_commands.command(name="chat", description="Chat with Puter AI (with web search)")
    @app_commands.describe(prompt="Your question", model="AI model (gpt-4o, gpt-4o-mini, claude, llama)", search="Search the web for info (yes/no)")
    async def chat(self, interaction: discord.Interaction, prompt: str, model: str = "gpt-4o", search: str = "yes"):
        """Chat command with context, server awareness, and web search."""
        await interaction.response.defer(thinking=True)

        try:
            # Validate model
            if model not in self.available_models and not any(m in model for m in ["gpt", "claude", "llama"]):
                model = "gpt-4o"  # Default
            
            # Perform web search if requested
            web_context = ""
            if search.lower() in ["yes", "y", "true", "1"]:
                try:
                    logger.info(f"Searching web for: {prompt}")
                    web_context = await search_and_summarize(prompt)
                except Exception as e:
                    logger.warning(f"Web search failed: {e}")
                    web_context = ""
            
            messages = self.get_conversation_context(
                interaction.channel_id, 
                prompt,
                web_context=web_context,
                guild=interaction.guild
            )
            response_text = await self.get_puter_response(messages, model)
            self.update_history(interaction.channel_id, prompt, response_text)

            if len(response_text) > 1900:
                response_text = response_text[:1900] + "... *(truncated)*"

            await interaction.followup.send(f"> **You:** {prompt}\n\n**AI:** {response_text}")
            logger.info(f"Chat command used by {interaction.user} in {interaction.guild}")
        except Exception as e:
            logger.error(f"Chat command error: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle mentions with context, server awareness, and web search."""
        if message.author.bot or not self.bot.user.mentioned_in(message):
            return

        async with message.channel.typing():
            prompt = message.content.replace(f'<@!{self.bot.user.id}>', '').replace(f'<@{self.bot.user.id}>', '').strip()
            if not prompt:
                await message.channel.send("Hello! How can I help?", reference=message)
                return

            try:
                # Search web for mentions
                try:
                    web_context = await search_and_summarize(prompt)
                except Exception as e:
                    logger.warning(f"Web search failed: {e}")
                    web_context = ""
                
                messages = self.get_conversation_context(
                    message.channel.id, 
                    prompt,
                    web_context=web_context,
                    guild=message.guild
                )
                response_text = await self.get_puter_response(messages, "gpt-4o")
                self.update_history(message.channel.id, prompt, response_text)

                if len(response_text) > 1900:
                    response_text = response_text[:1900] + "... *(truncated)*"

                await message.channel.send(response_text, reference=message)
                logger.info(f"AI mention response sent to {message.author} in {message.guild}")
            except Exception as e:
                logger.error(f"Mention response error: {e}")
                await message.channel.send(f"❌ Error: {str(e)}", reference=message)

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
