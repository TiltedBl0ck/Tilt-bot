import discord
from discord import app_commands
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)

class ErrorHandler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.tree.error(self.on_app_command_error)

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        # Log the detailed error
        logger.error(f"Error in command '{interaction.command.name if interaction.command else 'Unknown'}': {error}", exc_info=True)
        
        # Check if the interaction has expired. If so, we can't respond.
        if interaction.is_expired():
            logger.warning(f"Could not respond to an expired interaction for command '{interaction.command.name if interaction.command else 'Unknown'}'.")
            return

        # Prepare a user-friendly message
        if isinstance(error, app_commands.errors.MissingPermissions):
            message = "❌ You do not have the required permissions to run this command."
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            message = f"🕒 This command is on cooldown. Please try again in {error.retry_after:.2f} seconds."
        else:
            message = "❌ An unexpected error occurred while processing your command."

        # Try to respond to the user
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.errors.InteractionResponded:
            # If we already responded, try to send a followup instead
            await interaction.followup.send(message, ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(ErrorHandler(bot))
