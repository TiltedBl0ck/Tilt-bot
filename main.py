"""
Tilt-bot - Main Bot File
A comprehensive Discord bot with moderation, utility, AI, and management features.
"""
import asyncio
import logging
import os
import json 
from pathlib import Path
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Import the specific db functions (updated for PostgreSQL)
from cogs.utils.db import init_db, close_pool

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# --- Main Bot Class ---
class TiltBot(commands.Bot):
    """The main bot class, inheriting from commands.Bot."""
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(command_prefix='!', intents=intents)
        
        # Load version from config.json for consistency
        try:
            with open('config.json', 'r') as config_file:
                config = json.load(config_file)
                self.version = config.get("bot", {}).get("version", "N/A")
        except (FileNotFoundError, json.JSONDecodeError):
            self.version = "N/A"


    async def setup_hook(self) -> None:
        """This hook is called when the bot is setting up."""
        logger.info("--- Starting Bot Setup ---")
        
        # Initialize the database connection pool before loading cogs
        await init_db()

        # Load the central handler cog, which will then load all other cogs.
        await self.load_extension('cogs.handler')
        
        # Sync application commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Successfully synced {len(synced)} application commands.")
        except Exception as e:
            logger.error(f"Failed to sync application commands: {e}")

    async def on_ready(self) -> None:
        """Called when the bot is ready and connected to Discord."""
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info(f'Bot version: {self.version}')
        logger.info(f'Bot is in {len(self.guilds)} guilds.')
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} servers | /help"
            )
        )


async def main() -> None:
    """The main entry point for running the bot."""
    load_dotenv()
    token = os.getenv('BOT_TOKEN')
    if not token:
        logger.critical("BOT_TOKEN environment variable not set! Please check your .env file.")
        return

    bot = TiltBot()
    try:
        await bot.start(token)
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested by user.")
    finally:
        # Gracefully close the PostgreSQL connection pool
        await close_pool()
        
        if not bot.is_closed():
            await bot.close()
            
        logger.info("Bot has been shut down.")
        
        # This will safely close the logging handlers 
        logging.shutdown()


if __name__ == '__main__':
    # Run the bot
    asyncio.run(main())
