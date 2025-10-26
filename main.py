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
# Suppress noisy discord.http logs unless it's a warning or higher
logging.getLogger('discord.http').setLevel(logging.WARNING)
# Optionally suppress noisy asyncpg connection logs if needed
# logging.getLogger('asyncpg').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# --- Main Bot Class ---
class TiltBot(commands.Bot):
    """The main bot class, inheriting from commands.Bot."""
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True # Needed for message content processing (e.g., counting game)
        intents.members = True # Needed for welcome/goodbye messages and member count stats

        super().__init__(command_prefix='!', intents=intents) # Prefix is fallback, primarily uses slash commands

        # Load version from config.json for consistency
        self.version = "N/A" # Default version
        try:
            config_path = Path(__file__).parent / 'config.json'
            with open(config_path, 'r') as config_file:
                config = json.load(config_file)
                self.version = config.get("bot", {}).get("version", "N/A")
        except FileNotFoundError:
            logger.warning("config.json not found, bot version set to N/A.")
        except json.JSONDecodeError:
            logger.error("Error decoding config.json, bot version set to N/A.")


    async def setup_hook(self) -> None:
        """This hook is called once when the bot logs in, used for async setup."""
        logger.info("--- Starting Bot Setup ---")

        # Initialize the PostgreSQL database connection pool and schema
        try:
            await db_utils.init_db()
            # Check the 'pool' variable via the imported module namespace
            if db_utils.pool is None:
                 logger.critical("Database pool initialization failed (db_utils.pool is None after init_db). Check logs and POSTGRES_DSN.")
                 await self.close() # Shutdown if DB is essential
                 return
            logger.info("Database pool check in setup_hook passed.")
        except Exception as e:
            logger.critical(f"Database initialization failed critically: {e}", exc_info=True)
            await self.close() # Shutdown if DB init fails unexpectedly
            return

        # Load the central handler cog, which will then load all other cogs.
        try:
            await self.load_extension('cogs.handler')
            logger.info("Successfully loaded handler cog.")
        except commands.ExtensionError as e:
             logger.critical(f"Failed to load handler cog: {e}", exc_info=True)
             # Essential cog failed, consider shutting down
             await self.close()
             return

        # Sync application commands (slash commands) to Discord
        try:
            # Sync globally
            synced = await self.tree.sync()
            logger.info(f"Successfully synced {len(synced)} application commands.")
        except discord.HTTPException as e:
             logger.error(f"Failed to sync application commands due to API error: {e.status} {e.text}")
        except Exception as e:
            logger.error(f"An unexpected error occurred during command sync: {e}", exc_info=True)

    async def on_ready(self) -> None:
        """Called when the bot is fully ready and connected to Discord."""
        if not self.user: # Check if user object exists
            logger.error("Bot user object not found on ready. Login might have failed.")
            return

        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info(f'Bot version: {self.version}')
        logger.info(f'discord.py version: {discord.__version__}')
        logger.info(f'Bot is in {len(self.guilds)} guilds.')

        # Set bot presence
        activity_name = f"{len(self.guilds)} servers | /help"
        activity = discord.Activity(type=discord.ActivityType.watching, name=activity_name)
        try:
            await self.change_presence(status=discord.Status.online, activity=activity)
            logger.info(f"Presence set to: Watching {activity_name}")
        except Exception as e:
             logger.error(f"Failed to set presence: {e}")

    async def close(self):
        """Custom close method to ensure resources are cleaned up."""
        logger.info("Closing bot connection...")
        # Close the database pool before closing the bot connection
        await db_utils.close_pool() # Use module reference
        await super().close()
        logger.info("Bot connection closed.")


async def main() -> None:
    """The main entry point for running the bot."""
    # Ensure .env is in the same directory as main.py or specify path
    dotenv_path = Path(__file__).parent / '.env'
    load_dotenv(dotenv_path=dotenv_path)

    token = os.getenv('BOT_TOKEN')
    if not token:
        logger.critical("BOT_TOKEN environment variable not set! Please check your .env file.")
        return

    # Check for PostgreSQL DSN early
    dsn = os.getenv('POSTGRES_DSN')
    if not dsn:
        logger.critical("POSTGRES_DSN environment variable not set! Cannot connect to database.")
        # Exit early if DSN is missing and database is required
        return

    bot = TiltBot()
    try:
        logger.info("Starting bot...")
        # The setup_hook will handle db init before login completes
        await bot.start(token)
    except discord.LoginFailure:
        logger.critical("Failed to log in: Invalid Discord Bot Token provided.")
    except discord.PrivilegedIntentsRequired:
         logger.critical("Privileged Gateway Intents (Members or Message Content) are required but not enabled. "
                         "Please enable them in the Discord Developer Portal.")
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested via KeyboardInterrupt.")
    except Exception as e:
         # Catch potential errors during startup or runtime that aren't Discord specific
         logger.critical(f"An unexpected error occurred during bot execution: {e}", exc_info=True)
    finally:
        # Gracefully close the bot connection if it's running
        # The bot.close() method now handles closing the pool via the overridden close method
        if bot and not bot.is_closed():
            await bot.close()
        # Check the pool variable via the module namespace
        elif db_utils.pool: # If bot failed to initialize fully, ensure pool is closed if it exists
             logger.info("Bot not fully initialized or already closed, attempting pool closure directly.")
             await db_utils.close_pool() # Use module reference


        logger.info("Bot shutdown process complete.")

        # This will safely close the logging handlers
        logging.shutdown()


if __name__ == '__main__':
    try:
        # Check Python version if needed
        # import sys
        # if sys.version_info < (3, 8):
        #    print("Python 3.8+ is required.")
        #    sys.exit(1)
        asyncio.run(main())
    except RuntimeError as e:
        # Handle cases where the event loop might already be running
        if "Cannot run the event loop while another loop is running" in str(e):
             logger.warning("Event loop already running. Bot startup might behave unexpectedly in this environment.")
        else:
             logger.critical(f"RuntimeError during asyncio.run: {e}", exc_info=True)
             raise # Re-raise other RuntimeError exceptions
    except Exception as e:
         # Catch any other unexpected errors during the initial run call
         logger.critical(f"Critical error outside the main async loop: {e}", exc_info=True)

