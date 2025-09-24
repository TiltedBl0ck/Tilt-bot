"""
Tilt-bot - Main Bot File
A comprehensive Discord bot with moderation, utility, AI, and management features.

Author: TiltedBl0ck
Version: 2.0.0
"""

import asyncio
import logging
import os
import sqlite3
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

def init_db():
    """Initializes the database schema if it doesn't exist and adds new columns."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Create the main guild configuration table if it's not there
    cur.execute("""
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
    table_info = cur.execute("PRAGMA table_info(guild_config)").fetchall()
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
            cur.execute(f"ALTER TABLE guild_config ADD COLUMN {col_name} {col_type}")

    conn.commit()
    conn.close()
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

        # Load cogs
        cogs_to_load = [
            'cogs.help',        # New professional help cog
            'cogs.moderation',  # Moderation commands
            'cogs.utility',     # Utility commands (without old help command)
            'cogs.management',  # Server management and setup
            'cogs.gemini',      # AI chat functionality
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

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Global error handler for prefix commands."""
        logger.error(f"Command error in '{ctx.command}': {error}", exc_info=True)

    async def on_app_command_error(
        self, 
        interaction: discord.Interaction, 
        error: discord.app_commands.AppCommandError
    ) -> None:
        """Global error handler for slash commands."""
        logger.error(f"App command error in '{interaction.command.name}': {error}", exc_info=True)

        error_message = "❌ An unexpected error occurred while processing this command. The developers have been notified."
        
        # Give more specific feedback for common errors
        if isinstance(error, discord.app_commands.MissingPermissions):
            error_message = "❌ You don't have the required permissions to use this command."
        elif isinstance(error, discord.app_commands.CommandOnCooldown):
            error_message = f"🕒 This command is on cooldown. Please try again in {error.retry_after:.2f} seconds."

        if interaction.response.is_done():
            await interaction.followup.send(error_message, ephemeral=True)
        else:
            await interaction.response.send_message(error_message, ephemeral=True)


async def main() -> None:
    """Main function to start the bot."""
    # IMPORTANT: Load environment variables from the .env file
    load_dotenv()
    
    # Run the database initializer
    init_db()

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
