import logging
import discord
from discord import app_commands
from discord.ext import commands


logger = logging.getLogger(__name__)


class ClearCommand(commands.Cog):
    """A command for bulk-deleting messages in a channel."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def count_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[int]]:
        """Autocomplete for the count parameter."""
        choices = [
            app_commands.Choice(name="5 messages", value=5),
            app_commands.Choice(name="10 messages", value=10),
            app_commands.Choice(name="25 messages", value=25),
            app_commands.Choice(name="50 messages", value=50),
            app_commands.Choice(name="100 messages", value=100),
        ]
        
        return [choice for choice in choices if str(choice.value) in current or current in choice.name.lower()]

    @app_commands.autocomplete(count=count_autocomplete)
    @app_commands.command(name="clear", description="Clear a specified number of recent messages.")
    @app_commands.describe(count="Number of messages to delete (between 1 and 100).")
    async def clear(self, interaction: discord.Interaction, count: int) -> None:
        """Deletes only bot messages after performing checks."""
        if interaction.guild:
            # This is a server channel
            if not interaction.user.guild_permissions.manage_messages:
                await interaction.response.send_message(
                    "❌ You don't have the `Manage Messages` permission to do this.",
                    ephemeral=True
                )
                return

            if not 1 <= count <= 100:
                await interaction.response.send_message(
                    "❌ Count must be between 1 and 100.",
                    ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=True)
            try:
                deleted = await interaction.channel.purge(
                    limit=count,
                    check=lambda message: message.author == self.bot.user
                )
                await interaction.followup.send(
                    f"✅ Successfully deleted {len(deleted)} of my messages.",
                    ephemeral=True
                )
                logger.info(
                    f"{interaction.user} cleared {len(deleted)} bot messages in "
                    f"#{interaction.channel} ({interaction.guild.name})."
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    "❌ I don't have the `Manage Messages` permission to do this.",
                    ephemeral=True
                )
            except discord.HTTPException as e:
                # Fix: Handle messages older than 14 days error (Error Code 50034)
                if e.code == 50034:
                     await interaction.followup.send("❌ I can't bulk delete messages older than 14 days due to Discord limitations.", ephemeral=True)
                else:
                     logger.error(f"API Error in clear command: {e}")
                     await interaction.followup.send("❌ An API error occurred.", ephemeral=True)
            except Exception as e:
                logger.error(f"Error in clear command: {e}")
                await interaction.followup.send(
                    "❌ An error occurred while trying to clear messages.",
                    ephemeral=True
                )
        else:
            # This is a DM
            await interaction.response.defer(ephemeral=True)
            try:
                deleted_count = 0
                async for message in interaction.channel.history(limit=None):
                    if message.author == self.bot.user:
                        try:
                            await message.delete()
                            deleted_count += 1
                        except discord.NotFound:
                            continue

                await interaction.followup.send(
                    f"✅ Successfully deleted {deleted_count} of my messages in this DM.",
                    ephemeral=True
                )
                logger.info(
                    f"{interaction.user} cleared {deleted_count} of the bot's messages in a DM."
                )
            except Exception as e:
                logger.error(f"Error in clear command (DM): {e}")
                await interaction.followup.send(
                    "❌ An error occurred while trying to clear messages in this DM.",
                    ephemeral=True
                )


async def setup(bot: commands.Bot) -> None:
    """The setup function to add this cog to the bot."""
    await bot.add_cog(ClearCommand(bot))