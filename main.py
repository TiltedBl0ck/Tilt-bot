"""
Tilt-bot - Main Bot File
A comprehensive Discord bot with moderation, utility, AI, and management features.

Author: TiltedBl0ck
Version: 2.0.0
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import List, Optional

import discord
from discord.ext import commands

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


class TiltBot(commands.Bot):
    """
    Enhanced Bot class with improved cog management and error handling.
    """

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
            'cogs.help',      # New professional help cog
            'cogs.moderation', # Moderation commands
            'cogs.utility',   # Utility commands (without old help command)
            'cogs.management', # Server management and setup
            'cogs.gemini',    # AI chat functionality
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
        logger.error(f"Command error: {error}", exc_info=True)

    async def on_app_command_error(
        self, 
        interaction: discord.Interaction, 
        error: discord.app_commands.AppCommandError
    ) -> None:
        """Global error handler for slash commands."""
        logger.error(f"App command error: {error}", exc_info=True)

        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ An error occurred while processing this command.",
                ephemeral=True
            )


async def main() -> None:
    """Main function to start the bot."""
    # Load bot token from environment variable
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.critical("DISCORD_TOKEN environment variable not set!")
        return

    # Create and start bot
    bot = TiltBot()

    try:
        await bot.start(token)
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested by user")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
    finally:
        await bot.close()


if __name__ == '__main__':
    # Run the bot
    asyncio.run(main())
