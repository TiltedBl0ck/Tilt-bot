"""
Tilt-bot - Main entry point
Discord bot with moderation, utility, AI, and management features.
"""
import asyncio, logging, os, json
from pathlib import Path
import discord
from discord.ext import commands
from dotenv import load_dotenv

import cogs.utils.db as db_utils

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('configs/bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logging.getLogger('discord.http').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class TiltBot(commands.Bot):
    """The main bot class."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(command_prefix='!', intents=intents)

        self.version = "N/A"
        config_path = Path(__file__).parent / 'configs' / 'config.json'
        try:
            with open(config_path, 'r') as f:
                self.version = json.load(f).get("bot", {}).get("version", "N/A")
        except FileNotFoundError:
            logger.warning("config.json not found - that's fine, we'll use the default version.")
        except json.JSONDecodeError:
            logger.error("Looks like config.json has some issues. Skipping version load.")

    async def setup_hook(self) -> None:
        """Run our async setup - db init, loading cogs, syncing commands."""
        logger.info("--- Setting up the bot ---")

        # Fire up the database first
        try:
            await db_utils.init_db()
            logger.info("Database ready to go.")
        except Exception as e:
            logger.critical(f"Database failed to initialize: {e}", exc_info=True)
            await self.close()
            return

        # Load the handler cog - this is where most of the command magic lives
        try:
            await self.load_extension('cogs.handler')
            logger.info("Handler cog loaded.")
        except commands.ExtensionError as e:
            logger.critical(f"Couldn't load handler cog: {e}", exc_info=True)
            await self.close()
            return

        # Sync those slash commands so they show up
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} application commands.")
        except Exception as e:
            logger.error(f"Command sync choked: {e}", exc_info=True)

    async def on_ready(self) -> None:
        """Bot's all ready - let us know."""
        if not self.user:
            return

        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        activity = f"{len(self.guilds)} servers | /help"
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(type=discord.ActivityType.watching, name=activity)
        )

    async def close(self):
        """Clean up before shutdown."""
        await db_utils.close_pool()
        await super().close()


async def main() -> None:
    """Entry point - grab the token and get this party started."""
    load_dotenv(dotenv_path=Path(__file__).parent / '.env')

    token = os.getenv('BOT_TOKEN')
    if not token:
        logger.critical("No BOT_TOKEN found in .env - can't start without one!")
        return

    bot = TiltBot()
    try:
        await bot.start(token)
    except Exception as e:
        logger.critical(f"Boop - error occurred: {e}", exc_info=True)
    finally:
        if bot and not bot.is_closed():
            await bot.close()
        logging.shutdown()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Serious trouble - critical error: {e}", exc_info=True)
