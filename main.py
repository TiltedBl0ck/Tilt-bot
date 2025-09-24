"""
Tilt-bot - Main Bot File
A comprehensive Discord bot with moderation, utility, AI, and management features.

Author: TiltedBl0ck
Version: 2.0.0
"""

import asyncio
import logging
import os
import aiosqlite  # Use aiosqlite for async database operations
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

# --- Logging Setup ---
# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Database Initialization ---
DB_PATH = Path(__file__).parent / "Database.db"

async def init_db():
    """Initializes the database schema asynchronously if it doesn't exist and adds new columns."""
    async with aiosqlite.connect(DB_PATH) as conn:
        # Create the main guild configuration table if it's not there
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS guild_config (
            guild_id                  INTEGER PRIMARY KEY,
            welcome_channel_id        INTEGER,
            goodbye_channel_id        INTEGER,
            stats_category_id         INTEGER,
            member_count_channel_id   INTEGER,
            bot_count_channel_id      INTEGER,
            role_count_channel_id     INTEGER,
            channel_count_channel_id  INTEGER,
            setup_complete            INTEGER DEFAULT 0,
            welcome_message           TEXT,
            welcome_image             TEXT,
            goodbye_message           TEXT,
            goodbye_image             TEXT
        )
        """)
        
        # Check for and add columns if they are missing to prevent errors on update
        async with conn.execute("PRAGMA table_info(guild_config)") as cursor:
            table_info = await cursor.fetchall()
        
        column_names = [info[1] for info in table_info]
        
        columns_to_add = {
            "welcome_message": "TEXT",
            "welcome_image": "TEXT",
            "goodbye_message": "TEXT",
            "goodbye_image": "TEXT"
        }

        for col_name, col_type in columns_to_add.items():
            if col_name not in column_names:
                logger.info(f"Adding missing column '{col_name}' to guild_config table.")
                await conn.execute(f"ALTER TABLE guild_config ADD COLUMN {col_name} {col_type}")

        await conn.commit()
    logger.info("Database initialized successfully.")

# --- Main Bot Class ---
class TiltBot(commands.Bot):
    """Enhanced Bot class with improved cog management and error handling."""

    def __init__(self) -> None:
        """Initialize the bot with proper intents and configuration."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix='!',  # Fallback prefix, mainly using slash commands
            intents=intents,
            help_command=None,  # Disable default help command
            case_insensitive=True
        )
        self.version = "2.0.0"

    async def setup_hook(self) -> None:
        """
        Setup hook that runs before the bot starts.
        Load all cogs and sync commands here.
        """
        logger.info("Starting bot setup...")

        # Load cogs, including the dedicated error handler
        cogs_to_load = [
            'cogs.help',
            'cogs.moderation',
            'cogs.utility',
            'cogs.management',
            'cogs.gemini',
            'cogs.error_handler' # Load the dedicated error handler
        ]

        for cog in cogs_to_load:
            try:
                await self.load_extension(cog)
                logger.info(f"Successfully loaded {cog}")
            except Exception as e:
                logger.error(f"Failed to load {cog}: {e}")

        # Sync slash commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} slash commands")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

    async def on_ready(self) -> None:
        """Event triggered when the bot is ready."""
        logger.info(f"{self.user} has connected to Discord!")
        logger.info(f"Bot is in {len(self.guilds)} guilds")

        # Set bot status
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(self.guilds)} servers | /help"
        )
        await self.change_presence(activity=activity)

    # The on_app_command_error has been removed from here as it's now handled by the ErrorHandler cog.
    
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Global error handler for prefix commands."""
        logger.error(f"Command error in '{ctx.command}': {error}", exc_info=True)


async def main() -> None:
    """Main function to start the bot."""
    # IMPORTANT: Load environment variables from the .env file
    load_dotenv()
    
    # Run the async database initializer
    await init_db()

    # Load bot token from environment variable
    token = os.getenv('BOT_TOKEN')
    if not token:
        logger.critical("BOT_TOKEN environment variable not set! Please check your .env file.")
        return

    # Create and start bot
    bot = TiltBot()

    try:
        await bot.start(token)
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested by user.")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
    finally:
        if not bot.is_closed():
            await bot.close()
        logger.info("Bot has been shut down.")


if __name__ == '__main__':
    # Run the bot
    asyncio.run(main())
