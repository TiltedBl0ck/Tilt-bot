import discord
from discord import app_commands
from discord.ext import commands
# Import the specific helper functions needed
from cogs.utils.db import get_guild_config, set_guild_config_value
import logging

logger = logging.getLogger(__name__)

class ConfigCommands(commands.Cog):
    """Commands for configuring server-specific bot settings."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    config_group = app_commands.Group(name="config", description="Configure bot settings for this server.")

    @config_group.command(name="welcome", description="Set the custom welcome message and image.")
    @app_commands.describe(
        message="The welcome message. Use {user.mention}, {user.name}, {server.name}, {member.count}.",
        image_url="An optional URL for a welcome image."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def config_welcome(self, interaction: discord.Interaction, message: str, image_url: str = None):
        """Updates the guild's welcome message configuration in the database."""
        try:
            await set_guild_config_value(interaction.guild.id, "welcome_message", message)
            await set_guild_config_value(interaction.guild.id, "welcome_image", image_url)
            await interaction.response.send_message("✅ Welcome configuration has been updated!", ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting welcome config for guild {interaction.guild.id}: {e}", exc_info=True)
            await interaction.response.send_message("❌ An error occurred while updating welcome config.", ephemeral=True)

    @config_group.command(name="goodbye", description="Set the custom goodbye message and image.")
    @app_commands.describe(
        message="The goodbye message. Use {user.name}, {server.name}, {member.count}.",
        image_url="An optional URL for a goodbye image."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def config_goodbye(self, interaction: discord.Interaction, message: str, image_url: str = None):
        """Updates the guild's goodbye message configuration in the database."""
        try:
            await set_guild_config_value(interaction.guild.id, "goodbye_message", message)
            await set_guild_config_value(interaction.guild.id, "goodbye_image", image_url)
            await interaction.response.send_message("✅ Goodbye configuration has been updated!", ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting goodbye config for guild {interaction.guild.id}: {e}", exc_info=True)
            await interaction.response.send_message("❌ An error occurred while updating goodbye config.", ephemeral=True)

    @config_group.command(name="serverstats", description="Toggle which server statistics channels are visible.")
    @app_commands.describe(
        members="Show the member count channel.",
        bots="Show the bot count channel.",
        roles="Show the role count channel."
    )
    @app_commands.choices(members=[
        app_commands.Choice(name="Show", value=1),
        app_commands.Choice(name="Hide", value=0)
    ])
    @app_commands.choices(bots=[
        app_commands.Choice(name="Show", value=1),
        app_commands.Choice(name="Hide", value=0)
    ])
    @app_commands.choices(roles=[
        app_commands.Choice(name="Show", value=1),
        app_commands.Choice(name="Hide", value=0)
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def config_serverstats(self, interaction: discord.Interaction, members: int, bots: int, roles: int):
        """Updates the visibility of server stats channels."""
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        try:
            config = await get_guild_config(guild.id)

            if not config or not config.get("stats_category_id"):
                await interaction.followup.send("❌ Please run `/setup serverstats` first to create the channels.", ephemeral=True)
                return

            # Define permission overwrites based on integer input (1=True/Show, 0=False/Hide)
            member_overwrite = discord.PermissionOverwrite(view_channel=bool(members))
            bot_overwrite = discord.PermissionOverwrite(view_channel=bool(bots))
            role_overwrite = discord.PermissionOverwrite(view_channel=bool(roles))

            # Fetch channels (ensure they exist)
            member_channel = guild.get_channel(config.get("member_count_channel_id"))
            bot_channel = guild.get_channel(config.get("bot_count_channel_id"))
            role_channel = guild.get_channel(config.get("role_count_channel_id"))

            # Apply new permissions using set_permissions for the default role
            default_role = guild.default_role
            tasks = []
            if member_channel:
                tasks.append(member_channel.set_permissions(default_role, overwrite=member_overwrite))
            if bot_channel:
                tasks.append(bot_channel.set_permissions(default_role, overwrite=bot_overwrite))
            if role_channel:
                tasks.append(role_channel.set_permissions(default_role, overwrite=role_overwrite))

            await discord.utils.gather(*tasks, return_exceptions=True) # Run permission changes concurrently

            # Check results (optional, gather logs errors anyway)
            # for result in results:
            #    if isinstance(result, Exception):
            #        logger.error(f"Error setting permission during config_serverstats: {result}")

            await interaction.followup.send("✅ Server stats visibility has been updated!", ephemeral=True)
        except discord.Forbidden:
             await interaction.followup.send("❌ I don't have permission to edit channel permissions.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in config serverstats for guild {guild.id}: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while updating the channel visibility.", ephemeral=True)

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(ConfigCommands(bot))
