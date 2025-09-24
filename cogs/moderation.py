"""
Moderation Commands Cog for Tilt-bot

This cog provides moderation functionality including message clearing
and other administrative tools for server management.

Author: TiltedBl0ck
Version: 2.0.0
"""

import logging
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


class Moderation(commands.Cog):
    """
    Moderation commands cog providing administrative tools for server management.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="clear", description="Clear recent messages")
    @app_commands.describe(count="Number of messages to delete (1–100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, count: int):
        """
        Clear a specified number of messages from the current channel.

        Args:
            interaction (discord.Interaction): The interaction object
            count (int): Number of messages to delete (1-100)
        """
        if not 1 <= count <= 100:
            return await interaction.response.send_message(
                "❌ Count must be between 1 and 100.", 
                ephemeral=True
            )

        try:
            # Acknowledge the command first
            await interaction.response.defer(ephemeral=True)

            # Purge messages
            deleted = await interaction.channel.purge(limit=count)

            # Send confirmation
            await interaction.followup.send(
                f"✅ Deleted {len(deleted)} messages.", 
                ephemeral=True
            )

            logger.info(f"User {interaction.user} cleared {len(deleted)} messages in {interaction.guild}")

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I do not have the `Manage Messages` permission to do this.", 
                ephemeral=True
            )
            logger.warning(f"Missing permissions for clear command in {interaction.guild}")

        except discord.HTTPException as e:
            logger.error(f"Error during message purge: {e}")
            await interaction.followup.send(
                "❌ An error occurred while trying to clear messages. They might be too old.", 
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Unexpected error in clear command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An unexpected error occurred.", 
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
