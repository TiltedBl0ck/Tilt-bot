import logging
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

class ClearCommand(commands.Cog):
    """A command for bulk-deleting messages in a channel."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="clear", description="Clear a specified number of recent messages.")
    @app_commands.describe(count="Number of messages to delete (between 1 and 100).")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, count: int):
        """Deletes messages after performing checks."""
        if not 1 <= count <= 100:
            await interaction.response.send_message("❌ Count must be between 1 and 100.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            deleted = await interaction.channel.purge(limit=count)
            await interaction.followup.send(f"✅ Successfully deleted {len(deleted)} messages.", ephemeral=True)
            logger.info(f"{interaction.user} cleared {len(deleted)} messages in #{interaction.channel} ({interaction.guild.name}).")
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have the `Manage Messages` permission to do this.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in clear command: {e}")
            await interaction.followup.send("❌ An error occurred while trying to clear messages.", ephemeral=True)

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(ClearCommand(bot))
