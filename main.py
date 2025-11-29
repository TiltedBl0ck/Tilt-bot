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

# Import the db utility module itself
import cogs.utils.db as db_utils

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logging.getLogger('discord.http').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# --- Main Bot Class ---
class TiltBot(commands.Bot):
    """The main bot class, inheriting from commands.Bot."""
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True 
        intents.members = True 

        super().__init__(command_prefix='!', intents=intents) 

        self.version = "N/A"
        try:
            config_path = Path(__file__).parent / 'configs' / 'config.json'
            with open(config_path, 'r') as config_file:
                config = json.load(config_file)
                self.version = config.get("bot", {}).get("version", "N/A")
        except FileNotFoundError:
            logger.warning(f"config.json not found.")
        except json.JSONDecodeError:
            logger.error("Error decoding config.json.")


    async def setup_hook(self) -> None:
        """Async setup hook."""
        logger.info("--- Starting Bot Setup ---")

        # Initialize the database (Now SQLite)
        try:
            await db_utils.init_db()
            logger.info("Database initialized.")
        except Exception as e:
            logger.critical(f"Database initialization failed: {e}", exc_info=True)
            await self.close()
            return

        # Load handler
        try:
            await self.load_extension('cogs.handler')
            logger.info("Successfully loaded handler cog.")
        except commands.ExtensionError as e:
             logger.critical(f"Failed to load handler cog: {e}", exc_info=True)
             await self.close()
             return

        # Sync commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Successfully synced {len(synced)} application commands.")
        except Exception as e:
            logger.error(f"Error during command sync: {e}", exc_info=True)

    async def on_ready(self) -> None:
        """Called when bot is ready."""
        if not self.user: 
            return

        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        activity_name = f"{len(self.guilds)} servers | /help"
        await self.change_presence(status=discord.Status.online, activity=discord.Activity(type=discord.ActivityType.watching, name=activity_name))

    async def close(self):
        """Cleanup."""
        await db_utils.close_pool() 
        await super().close()


async def main() -> None:
    """Main entry point."""
    dotenv_path = Path(__file__).parent / '.env'
    load_dotenv(dotenv_path=dotenv_path)

    token = os.getenv('BOT_TOKEN')
    if not token:
        logger.critical("BOT_TOKEN not found!")
        return

    # Note: POSTGRES_DSN is no longer required for SQLite
    
    bot = TiltBot()
    try:
        await bot.start(token)
    except Exception as e:
         logger.critical(f"Error: {e}", exc_info=True)
    finally:
        if bot and not bot.is_closed():
            await bot.close()
        logging.shutdown()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
         logger.critical(f"Critical error: {e}", exc_info=True)