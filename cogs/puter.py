import logging
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import os
from collections import defaultdict
import time
from cogs.utils.web_search import search_and_summarize, get_latest_info

logger = logging.getLogger(__name__)

# Load Puter credentials - one password, multiple usernames
PUTER_PASSWORD = os.getenv("PUTER_PASSWORD")
PUTER_USERNAMES_STR = os.getenv("PUTER_USERNAMES", "")  # Comma-separated list

# Parse usernames from comma-separated string
PUTER_ACCOUNTS = []
if PUTER_PASSWORD and PUTER_USERNAMES_STR:
    usernames = [u.strip() for u in PUTER_USERNAMES_STR.split(",") if u.strip()]
    for i, username in enumerate(usernames, 1):
        PUTER_ACCOUNTS.append({"username": username, "password": PUTER_PASSWORD, "index": i})

if not PUTER_ACCOUNTS:
    logger.warning("No Puter credentials found. Bot will use web search only.")
else:
    logger.info(f"Found {len(PUTER_ACCOUNTS)} Puter account(s): {', '.join([a['username'] for a in PUTER_ACCOUNTS])}")


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
        self.puter_available = True  # Track if Puter is working
        self.current_account_index = 0  # Track which account we're using
        self.failed_accounts = set()  # Track which accounts have failed
        
        # Available models on Puter API
        self.available_models = [
            "gpt-4o",
            "gpt-4o-mini",
            "claude-3-5-sonnet-20241022",
            "meta-llama/Llama-3.3-70B-Instruct-Turbo"
        ]

    def get_next_account(self):
        """Get the next available Puter account."""
        if not PUTER_ACCOUNTS:
            return None
        
        # Find first account that hasn't failed
        for i, account in enumerate(PUTER_ACCOUNTS):
            if account["index"] not in self.failed_accounts:
                self.current_account_index = i
                logger.info(f"Using Puter account {account['index']}: {account['username']}")
                return account
        
        # If all failed, reset and try first again
        if len(self.failed_accounts) == len(PUTER_ACCOUNTS):
            logger.warning("All Puter accounts have failed. Resetting...")
            self.failed_accounts.clear()
            self.current_account_index = 0
            return PUTER_ACCOUNTS[0]
        
        return None

    async def ensure_authenticated(self):
        """Ensure Puter client is authenticated (with fallback accounts)."""
        if not PUTER_ACCOUNTS:
            logger.warning("No Puter credentials available")
            self.puter_available = False
            return
        
        current_time = time.time()
        
        # If client exists and recent login, reuse it
        if self.client is not None and (current_time - self.last_login_time) < self.login_cooldown:
            logger.debug("Reusing cached Puter client")
            return
        
        try:
            from putergenai import PuterClient
            
            account = self.get_next_account()
            if not account:
                logger.error("No available Puter accounts")
                self.puter_available = False
                return
            
            self.client = PuterClient()
            
            # Run login in executor to avoid blocking
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.login(account["username"], account["password"])
            )
            
            self.last_login_time = current_time
            self.puter_available = True
            logger.info(f"✅ Authenticated with Puter account {account['index']}: {account['username']}")
            
        except Exception as e:
            error_msg = str(e).lower()
            account = PUTER_ACCOUNTS[self.current_account_index] if self.current_account_index < len(PUTER_ACCOUNTS) else None
            
            if "permission" in error_msg or "error 400" in error_msg:
                logger.error(f"❌ Account {account['index']}: {account['username']} Permission denied - marking as failed")
                if account:
                    self.failed_accounts.add(account["index"])
            
            logger.error(f"Puter auth failed: {e}")
            self.client = None
            self.puter_available = False

    def build_system_message(self, guild: discord.Guild = None) -> str:
        """Build system message from memory and server context."""
        memory_cog = self.bot.get_cog("Memory")
        serverinfo_cog = self.bot.get_cog("ServerInfo")
        
        if not memory_cog:
            return "You are a helpful Discord bot. Provide accurate, helpful responses based on available information."
        
        memory = memory_cog.memory
        
        if memory.get('system_prompt'):
            system_msg = memory.get('system_prompt')
        else:
            lines = [
                f"You are {memory.get('bot_name', 'a Discord bot')}.",
                f"Description: {memory.get('bot_description', 'A helpful bot')}",
                f"Personality: {memory.get('personality', 'helpful and friendly')}",
            ]
            system_msg = "\n".join(lines)
        
        if guild and serverinfo_cog:
            try:
                guild_info = serverinfo_cog.get_guild_context(guild)
                system_msg += f"\n\nServer: {guild_info}"
            except Exception as e:
                logger.debug(f"Could not get guild context: {e}")
        
        return system_msg

    def get_conversation_context(self, channel_id: int, user_message: str, web_context: str = "", guild: discord.Guild = None) -> list:
        """Build conversation context."""
        history = self.conversation_history[channel_id]
        system_msg = self.build_system_message(guild)
        
        if web_context and web_context.strip():
            system_msg += f"\n\n**Current Information:**\n{web_context}"
        
        messages = [{"role": "system", "content": system_msg}]
        
        for msg in history:
            if msg.get("role") != "system":
                messages.append(msg)
        
        messages.append({"role": "user", "content": user_message})
        return messages

    def update_history(self, channel_id: int, user_message: str, ai_response: str):
        """Update conversation history."""
        history = self.conversation_history[channel_id]
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": ai_response})
        
        if len(history) > self.max_history:
            self.conversation_history[channel_id] = history[-self.max_history:]

    async def get_puter_response(self, messages: list, model: str = "gpt-4o", attempt: int = 0) -> str:
        """Get response from Puter AI with account fallback."""
        try:
            await self.ensure_authenticated()
            
            if not self.puter_available or self.client is None:
                return None

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
                timeout=30.0
            )

            if isinstance(response, dict):
                content = response.get("response", {}).get("result", {}).get("message", {}).get("content", "")
                if not content:
                    content = response.get("message", {}).get("content", "")
                if not content:
                    content = response.get("content", "")
            else:
                content = str(response)

            return content or None

        except Exception as e:
            error_msg = str(e).lower()
            logger.error(f"Puter error: {e}")
            
            # Permission denied - try next account
            if "permission" in error_msg or "error 400" in error_msg:
                logger.warning(f"Permission denied - trying fallback account...")
                account = PUTER_ACCOUNTS[self.current_account_index] if self.current_account_index < len(PUTER_ACCOUNTS) else None
                if account:
                    self.failed_accounts.add(account["index"])
                
                # Reset client and try next account
                self.client = None
                self.puter_available = False
                
                # Try next account
                if len(self.failed_accounts) < len(PUTER_ACCOUNTS):
                    await self.ensure_authenticated()
                    if self.puter_available and self.client:
                        return await self.get_puter_response(messages, model, attempt)
                
                return None
            
            # Model error - try fallback model
            if "moderation" in error_msg and attempt < len(self.available_models):
                fallback_model = self.available_models[attempt]
                return await self.get_puter_response(messages, fallback_model, attempt + 1)
            
            return None

    @app_commands.command(name="chat", description="Chat with AI (with web search)")
    @app_commands.describe(prompt="Your question")
    async def chat(self, interaction: discord.Interaction, prompt: str):
        """Chat command with web search."""
        await interaction.response.defer(thinking=True)

        try:
            web_context = ""
            try:
                logger.info(f"Searching for: {prompt}")
                web_context = await get_latest_info(prompt)
            except Exception as e:
                logger.warning(f"Web search failed: {e}")
            
            messages = self.get_conversation_context(
                interaction.channel_id, 
                prompt,
                web_context=web_context,
                guild=interaction.guild
            )
            
            response_text = await self.get_puter_response(messages)
            
            if response_text is None:
                if web_context:
                    response_text = f"📚 Here's what I found:\n\n{web_context}"
                else:
                    response_text = "Sorry, I'm having trouble processing that right now. Please try again."
            
            self.update_history(interaction.channel_id, prompt, response_text)

            if len(response_text) > 1900:
                response_text = response_text[:1900] + "..."

            await interaction.followup.send(f"**You:** {prompt}\n\n{response_text}")
            
        except Exception as e:
            logger.error(f"Chat error: {e}")
            await interaction.followup.send(f"Error: {str(e)[:100]}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle mentions."""
        if message.author.bot or not self.bot.user.mentioned_in(message):
            return

        async with message.channel.typing():
            prompt = message.content.replace(f'<@!{self.bot.user.id}>', '').replace(f'<@{self.bot.user.id}>', '').strip()
            if not prompt:
                await message.channel.send("Hi! How can I help?", reference=message)
                return

            try:
                web_context = ""
                try:
                    web_context = await get_latest_info(prompt)
                except Exception as e:
                    logger.warning(f"Web search failed: {e}")
                
                messages = self.get_conversation_context(
                    message.channel.id, 
                    prompt,
                    web_context=web_context,
                    guild=message.guild
                )
                
                response_text = await self.get_puter_response(messages)
                
                if response_text is None:
                    if web_context:
                        response_text = f"📚 Here's what I found:\n\n{web_context}"
                    else:
                        response_text = "Sorry, I'm unable to process that right now."
                
                self.update_history(message.channel.id, prompt, response_text)

                if len(response_text) > 1900:
                    response_text = response_text[:1900] + "..."

                await message.channel.send(response_text, reference=message)
                
            except Exception as e:
                logger.error(f"Mention error: {e}")
                await message.channel.send(f"Error: {str(e)[:100]}", reference=message)

    @app_commands.command(name="clear-chat", description="Clear conversation history")
    async def clear_chat(self, interaction: discord.Interaction):
        """Clear chat history."""
        channel_id = interaction.channel_id
        if channel_id in self.conversation_history:
            del self.conversation_history[channel_id]
            await interaction.response.send_message("✅ History cleared.", ephemeral=True)
        else:
            await interaction.response.send_message("No history to clear.", ephemeral=True)

    @app_commands.command(name="account-status", description="Check Puter account status")
    async def account_status(self, interaction: discord.Interaction):
        """Check which accounts are available."""
        await interaction.response.defer(ephemeral=True)
        
        if not PUTER_ACCOUNTS:
            await interaction.followup.send("❌ No Puter accounts configured")
            return
        
        status_msg = "📊 **Puter Account Status:**\n\n"
        for account in PUTER_ACCOUNTS:
            status = "❌ Failed" if account["index"] in self.failed_accounts else "✅ Available"
            status_msg += f"Account {account['index']}: {account['username']} - {status}\n"
        
        status_msg += f"\n**Currently using:** Account {PUTER_ACCOUNTS[self.current_account_index]['index']}: {PUTER_ACCOUNTS[self.current_account_index]['username']}"
        await interaction.followup.send(status_msg)


async def setup(bot: commands.Bot):
    """Setup cog."""
    await bot.add_cog(Puter(bot))