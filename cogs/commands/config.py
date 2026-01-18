import discord
from discord import app_commands
from discord.ext import commands
import cogs.utils.db as db_utils # Use alias for db utilities
import logging
from typing import Optional # For type hinting
import asyncio # Import asyncio for gather

logger = logging.getLogger(__name__)

class ConfigCommands(commands.Cog):
    """Commands for configuring server-specific bot settings."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    config_group = app_commands.Group(name="config", description="Configure bot settings for this server.")

    @config_group.command(name="welcome", description="Set the custom welcome message and image.")
    @app_commands.describe(
        message="The welcome message. Use {user.mention}, {user.name}, {server.name}, {member.count}.",
        image_url="Optional: URL for a welcome image (must start with http/https). Leave blank to remove."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def config_welcome(self, interaction: discord.Interaction, message: str, image_url: Optional[str] = None):
        """Updates the guild's welcome message configuration."""
        if image_url and not image_url.startswith(("http://", "https://")):
             await interaction.response.send_message("❌ Invalid image URL. It must start with `http://` or `https://`.", ephemeral=True)
             return

        updates = {
            "welcome_message": message,
            "welcome_image": image_url # Will store None if not provided or blank
        }
        success = await db_utils.set_guild_config_value(interaction.guild.id, updates)

        if success:
            await interaction.response.send_message("✅ Welcome configuration has been updated!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Failed to update welcome configuration in the database.", ephemeral=True)

    @config_group.command(name="goodbye", description="Set the custom goodbye message and image.")
    @app_commands.describe(
        message="The goodbye message. Use {user.name}, {server.name}, {member.count}.",
        image_url="Optional: URL for a goodbye image (must start with http/https). Leave blank to remove."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def config_goodbye(self, interaction: discord.Interaction, message: str, image_url: Optional[str] = None):
        """Updates the guild's goodbye message configuration."""
        if image_url and not image_url.startswith(("http://", "https://")):
             await interaction.response.send_message("❌ Invalid image URL. It must start with `http://` or `https://`.", ephemeral=True)
             return

        updates = {
            "goodbye_message": message,
            "goodbye_image": image_url # Will store None if not provided or blank
        }
        success = await db_utils.set_guild_config_value(interaction.guild.id, updates)

        if success:
            await interaction.response.send_message("✅ Goodbye configuration has been updated!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Failed to update goodbye configuration in the database.", ephemeral=True)

    @config_group.command(name="serverstats", description="Toggle which server statistics channels are visible.")
    @app_commands.describe(
        members="Show the member count channel.",
        bots="Show the bot count channel.",
        roles="Show the role count channel."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def config_serverstats(self, interaction: discord.Interaction, members: bool, bots: bool, roles: bool):
        """Updates the visibility of server stats channels."""
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild # Cache guild object

        # Get config from cache/DB
        config = await db_utils.get_guild_config(guild.id)

        if not config or not config.get("stats_category_id"):
            await interaction.followup.send("❌ Please run `/setup serverstats` first to create the channels.", ephemeral=True)
            return

        try:
            # Define permission overwrites based on boolean input
            # Important: Get the specific channel objects
            member_channel = guild.get_channel(config.get("member_count_channel_id", 0)) # Use get with default
            bot_channel = guild.get_channel(config.get("bot_count_channel_id", 0))
            role_channel = guild.get_channel(config.get("role_count_channel_id", 0))

            default_role = guild.default_role
            update_tasks = [] # Collect tasks to run concurrently

            # --- Member Channel ---
            if member_channel and isinstance(member_channel, discord.VoiceChannel):
                current_overwrite = member_channel.overwrites_for(default_role)
                if current_overwrite.view_channel != members:
                    current_overwrite.view_channel = members
                    # Don't change connect perms here, just view
                    update_tasks.append(member_channel.set_permissions(default_role, overwrite=current_overwrite, reason="Toggle server stats visibility"))
            elif config.get("member_count_channel_id"):
                 logger.warning(f"Member channel {config.get('member_count_channel_id')} not found or invalid in {guild.name}")


            # --- Bot Channel ---
            if bot_channel and isinstance(bot_channel, discord.VoiceChannel):
                current_overwrite = bot_channel.overwrites_for(default_role)
                if current_overwrite.view_channel != bots:
                    current_overwrite.view_channel = bots
                    update_tasks.append(bot_channel.set_permissions(default_role, overwrite=current_overwrite, reason="Toggle server stats visibility"))
            elif config.get("bot_count_channel_id"):
                logger.warning(f"Bot channel {config.get('bot_count_channel_id')} not found or invalid in {guild.name}")

            # --- Role Channel ---
            if role_channel and isinstance(role_channel, discord.VoiceChannel):
                current_overwrite = role_channel.overwrites_for(default_role)
                if current_overwrite.view_channel != roles:
                    current_overwrite.view_channel = roles
                    update_tasks.append(role_channel.set_permissions(default_role, overwrite=current_overwrite, reason="Toggle server stats visibility"))
            elif config.get("role_count_channel_id"):
                 logger.warning(f"Role channel {config.get('role_count_channel_id')} not found or invalid in {guild.name}")

            # Execute all permission updates
            if update_tasks:
                await asyncio.gather(*update_tasks, return_exceptions=True) # Use imported asyncio and handle potential errors during update
                await interaction.followup.send("✅ Server stats visibility has been updated!", ephemeral=True)
            else:
                 await interaction.followup.send("ℹ️ No visibility changes needed based on current settings.", ephemeral=True)


        except discord.Forbidden:
             await interaction.followup.send("❌ I don't have permission to edit channel permissions.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in config serverstats for guild {guild.id}: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while updating the channel visibility.", ephemeral=True)

    @config_group.command(name="wotd", description="Configure Word of the Day delivery time.")
    @app_commands.describe(
        timezone_str="Timezone offset (e.g., 'UTC+8', '-5', '8'). Default is UTC.",
        hour="Hour of the day to send (0-23). Default is 8 (8 AM)."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def config_wotd(self, interaction: discord.Interaction, timezone_str: str = "UTC", hour: int = 8):
        """Sets the timezone and hour for WOTD messages."""
        if not 0 <= hour <= 23:
             await interaction.response.send_message("❌ Hour must be between 0 and 23.", ephemeral=True)
             return
        
        # Simple normalization for storage
        normalized_tz = timezone_str.upper().replace(" ", "")
        
        updates = {
            "wotd_timezone": normalized_tz,
            "wotd_hour": hour
        }
        success = await db_utils.set_guild_config_value(interaction.guild.id, updates)
        
        if success:
             await interaction.response.send_message(f"✅ WOTD configuration updated! I will post at **{hour}:00** in **{normalized_tz}**.", ephemeral=True)
        else:
             await interaction.response.send_message("❌ Failed to update configuration.", ephemeral=True)

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(ConfigCommands(bot))