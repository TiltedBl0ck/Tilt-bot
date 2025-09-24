import os
import logging
import asyncio # BUG FIX: Added missing import for asyncio
from discord.ext import commands

logger = logging.getLogger(__name__)

class CommandHandler(commands.Cog):
    """
    This cog uses a special event `cog_load` to asynchronously load all extensions
    from the commands and events directories.
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
        # Add 'error_handler' to the list of directories to load from.
        cog_dirs = ["commands", "events", "error_handler"] 

        for cog_dir in cog_dirs:
            # Adjust path for single files like error_handler
            if os.path.isfile(f"cogs/{cog_dir}.py"):
                 path_entries = [f"{cog_dir}.py"]
                 path = "cogs"
            else:
                 path_entries = os.listdir(f"cogs/{cog_dir}")
                 path = f"cogs/{cog_dir}"
            
            for filename in path_entries:
                if filename.endswith(".py") and not filename.startswith("__"):
                    # Determine the full extension path
                    if cog_dir == "error_handler":
                        extension_name = f"cogs.{filename[:-3]}"
                    else:
                        extension_name = f"cogs.{cog_dir}.{filename[:-3]}"

                    try:
                        await self.bot.load_extension(extension_name)
                        logger.info(f"Successfully loaded extension: {extension_name}")
                    except Exception as e:
                        logger.error(f"Failed to load extension {extension_name}: {e}", exc_info=True)

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(CommandHandler(bot))

