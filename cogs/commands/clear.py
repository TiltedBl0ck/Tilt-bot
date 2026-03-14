import asyncio
import logging
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

MAX_CLEAR = 100


class Clear(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="clear", description="Delete recent messages in this channel")
    @app_commands.describe(
        count="How many recent messages to check/delete (1-100)",
        user="Optional: only delete messages from this user"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(
        self,
        interaction: discord.Interaction,
        count: app_commands.Range[int, 1, MAX_CLEAR],
        user: discord.Member | None = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)

        channel = interaction.channel
        if channel is None:
            await interaction.followup.send("❌ Channel not found.", ephemeral=True)
            return

        # DM behavior: bot can only delete its own messages in DMs
        if interaction.guild is None:
            deleted = 0
            checked = 0

            async for message in channel.history(limit=count):
                checked += 1
                if message.author.id == self.bot.user.id:
                    try:
                        await message.delete()
                        deleted += 1
                        await asyncio.sleep(0.3)
                    except discord.HTTPException:
                        continue

            await interaction.followup.send(
                f"✅ Deleted {deleted} bot message(s) from this DM out of {checked} checked.\n"
                f"ℹ️ Discord does not allow bots to delete other users' DM messages.",
                ephemeral=True,
            )
            return

        me = interaction.guild.me
        if me is None:
            await interaction.followup.send("❌ Could not verify bot permissions.", ephemeral=True)
            return

        perms = channel.permissions_for(me)
        if not perms.manage_messages or not perms.read_message_history:
            await interaction.followup.send(
                "❌ I need both **Manage Messages** and **Read Message History** in this channel.",
                ephemeral=True,
            )
            return

        def check(message: discord.Message) -> bool:
            if user is None:
                return True
            return message.author.id == user.id

        try:
            # +1 so the slash-command invocation context isn't relevant, but the scan is a bit more forgiving
            deleted_messages = await channel.purge(limit=count, check=check)
            deleted_count = len(deleted_messages)

            if user is None:
                await interaction.followup.send(
                    f"✅ Deleted {deleted_count} message(s) from this channel.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"✅ Deleted {deleted_count} message(s) from {user.mention}.",
                    ephemeral=True,
                )

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to delete messages here.",
                ephemeral=True,
            )
        except discord.HTTPException as exc:
            logger.error(f"Clear command failed: {exc}", exc_info=True)
            await interaction.followup.send(
                "❌ Failed to delete messages. Discord may reject some older messages from bulk deletion.",
                ephemeral=True,
            )

    @clear.error
    async def clear_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            if interaction.response.is_done():
                await interaction.followup.send(
                    "❌ You need **Manage Messages** to use this command.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "❌ You need **Manage Messages** to use this command.",
                    ephemeral=True,
                )
            return

        logger.error(f"Unhandled clear command error: {error}", exc_info=True)
        if interaction.response.is_done():
            await interaction.followup.send("❌ An unexpected error occurred.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Clear(bot))
