import os
import logging
from discord.ext import commands

logger = logging.getLogger(__name__)

class CommandHandler(commands.Cog):
    """
    This cog uses a special event `cog_load` to asynchronously load all extensions
    from the commands, events, and utils directories.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """
        This is a special discord.py event that runs after the cog is loaded.
        It ensures all other extensions are loaded asynchronously before the
        bot proceeds with syncing commands.
        """
        logger.info("--- Loading Extensions ---")
        cog_dirs = ["commands", "events", "utils"]

        for cog_dir in cog_dirs:
            path = f"cogs/{cog_dir}"
            for filename in os.listdir(path):
                if filename.endswith(".py") and not filename.startswith("__"):
                    # db.py is a utility, not a cog, so we skip it
                    if filename == "db.py":
                        continue
                        
                    extension_name = f"cogs.{cog_dir}.{filename[:-3]}"
                    try:
                        await self.bot.load_extension(extension_name)
                        logger.info(f"Successfully loaded extension: {extension_name}")
                    except Exception as e:
                        logger.error(f"Failed to load extension {extension_name}: {e}", exc_info=True)

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(CommandHandler(bot))

