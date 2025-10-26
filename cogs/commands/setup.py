import discord
from discord import app_commands
from discord.ext import commands
# Import the specific helper functions needed
from cogs.utils.db import get_guild_config, set_guild_config_value
import logging
import asyncio # For cleaning up channels if setup fails

logger = logging.getLogger(__name__)

class SetupCommands(commands.Cog):
    """Commands for setting up core bot features."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    setup_group = app_commands.Group(name="setup", description="Setup commands for Tilt-bot features.")

    @setup_group.command(name="welcome", description="Set or remove the welcome message channel.")
    @app_commands.describe(action="Choose to set or unset the channel.", channel="The channel for welcome messages.")
    @app_commands.choices(action=[
        app_commands.Choice(name="Set", value="set"),
        app_commands.Choice(name="Unset", value="unset")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_welcome(self, interaction: discord.Interaction, action: str, channel: discord.TextChannel = None):
        """Sets or unsets the welcome channel in the database."""
        guild_id = interaction.guild.id
        try:
            if action == "set":
                if channel is None:
                    await interaction.response.send_message("❌ You must specify a channel to set.", ephemeral=True)
                    return
                await set_guild_config_value(guild_id, "welcome_channel_id", channel.id)
                await interaction.response.send_message(f"✅ Welcome channel has been set to {channel.mention}.", ephemeral=True)
            else: # Unset
                await set_guild_config_value(guild_id, "welcome_channel_id", None)
                await interaction.response.send_message("✅ Welcome channel has been unset.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting welcome channel for guild {guild_id}: {e}", exc_info=True)
            await interaction.response.send_message("❌ An error occurred while updating the welcome channel setting.", ephemeral=True)

    @setup_group.command(name="goodbye", description="Set or remove the goodbye message channel.")
    @app_commands.describe(action="Choose to set or unset the channel.", channel="The channel for goodbye messages.")
    @app_commands.choices(action=[
        app_commands.Choice(name="Set", value="set"),
        app_commands.Choice(name="Unset", value="unset")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_goodbye(self, interaction: discord.Interaction, action: str, channel: discord.TextChannel = None):
        """Sets or unsets the goodbye channel in the database."""
        guild_id = interaction.guild.id
        try:
            if action == "set":
                if channel is None:
                    await interaction.response.send_message("❌ You must specify a channel to set.", ephemeral=True)
                    return
                await set_guild_config_value(guild_id, "goodbye_channel_id", channel.id)
                await interaction.response.send_message(f"✅ Goodbye channel has been set to {channel.mention}.", ephemeral=True)
            else: # Unset
                await set_guild_config_value(guild_id, "goodbye_channel_id", None)
                await interaction.response.send_message("✅ Goodbye channel has been unset.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting goodbye channel for guild {guild_id}: {e}", exc_info=True)
            await interaction.response.send_message("❌ An error occurred while updating the goodbye channel setting.", ephemeral=True)


    @setup_group.command(name="serverstats", description="Enable or disable server statistics channels.")
    @app_commands.describe(action="Enable or disable the server stats feature.")
    @app_commands.choices(action=[
        app_commands.Choice(name="Enable", value="enable"),
        app_commands.Choice(name="Disable", value="disable")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_serverstats(self, interaction: discord.Interaction, action: str):
        """Creates or deletes the server stats channels and category."""
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild # Cache guild object
        guild_id = guild.id

        current_config = await get_guild_config(guild_id)

        if action == "enable":
            # Check if already enabled
            if current_config and current_config.get("stats_category_id"):
                # Verify channels still exist, recreate if necessary? Or just inform user.
                cat_id = current_config.get("stats_category_id")
                mem_id = current_config.get("member_count_channel_id")
                bot_id = current_config.get("bot_count_channel_id")
                rol_id = current_config.get("role_count_channel_id")
                if guild.get_channel(cat_id) and guild.get_channel(mem_id) and guild.get_channel(bot_id) and guild.get_channel(rol_id):
                    await interaction.followup.send("⚠️ Server stats seem to be already enabled and channels exist.", ephemeral=True)
                    return
                else:
                    logger.warning(f"Server stats enabled in DB for {guild.id} but channels missing. Attempting recreation.")
                    # Fall through to recreate

            category, members, bots, roles = None, None, None, None # Define before try block for cleanup
            try:
                # Create category and channels
                overwrites = {guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True)} # Ensure viewable, prevent connect
                category = await guild.create_category("📊 Server Stats", overwrites=overwrites, reason="Tilt-bot Server Stats Setup")

                # Calculate initial counts
                member_count = guild.member_count
                # Fetch members if needed, or rely on cached count if intents allow
                # member_count = len([m for m in guild.members if not m.bot]) # If you need non-bot count
                bot_count = sum(1 for m in guild.members if m.bot)
                role_count = len(guild.roles)

                # Create channels within the category
                members = await guild.create_voice_channel(f"👥 Members: {member_count}", category=category, reason="Tilt-bot Server Stats Setup")
                bots = await guild.create_voice_channel(f"🤖 Bots: {bot_count}", category=category, reason="Tilt-bot Server Stats Setup")
                roles = await guild.create_voice_channel(f"📜 Roles: {role_count}", category=category, reason="Tilt-bot Server Stats Setup")

                # Apply connect=False overwrite specifically to voice channels as well
                for vc in [members, bots, roles]:
                    await vc.set_permissions(guild.default_role, connect=False)

                # Save IDs to database using helper function
                await set_guild_config_value(guild_id, "stats_category_id", category.id)
                await set_guild_config_value(guild_id, "member_count_channel_id", members.id)
                await set_guild_config_value(guild_id, "bot_count_channel_id", bots.id)
                await set_guild_config_value(guild_id, "role_count_channel_id", roles.id)

                await interaction.followup.send("✅ Server stats channels have been created!", ephemeral=True)

            except discord.Forbidden:
                await interaction.followup.send("❌ I am missing permissions to manage channels or roles.", ephemeral=True)
                # Attempt cleanup
                if category: await category.delete(reason="Tilt-bot Setup Failed (Forbidden)")
            except Exception as e:
                logger.error(f"Error in serverstats setup (enable) for guild {guild_id}: {e}", exc_info=True)
                # Attempt to clean up partially created channels
                cleanup_tasks = []
                if members: cleanup_tasks.append(members.delete(reason="Tilt-bot Setup Failed Cleanup"))
                if bots: cleanup_tasks.append(bots.delete(reason="Tilt-bot Setup Failed Cleanup"))
                if roles: cleanup_tasks.append(roles.delete(reason="Tilt-bot Setup Failed Cleanup"))
                if category: cleanup_tasks.append(category.delete(reason="Tilt-bot Setup Failed Cleanup")) # Delete category last
                if cleanup_tasks:
                    try:
                        await discord.utils.gather(*cleanup_tasks, return_exceptions=True)
                        logger.info(f"Cleaned up partially created stats channels for guild {guild_id}")
                    except Exception as cleanup_e:
                        logger.error(f"Error during serverstats cleanup for guild {guild_id}: {cleanup_e}")
                await interaction.followup.send("❌ An error occurred during setup.", ephemeral=True)

        else: # Disable action
            if not current_config or not current_config.get("stats_category_id"):
                await interaction.followup.send("⚠️ Server stats are not currently enabled.", ephemeral=True)
                return

            try:
                channel_ids_to_delete = [
                    current_config.get("member_count_channel_id"),
                    current_config.get("bot_count_channel_id"),
                    current_config.get("role_count_channel_id"),
                    current_config.get("stats_category_id") # Delete category last
                ]
                deleted_count = 0
                delete_tasks = []

                for channel_id in filter(None, channel_ids_to_delete): # Filter out None values
                    channel = guild.get_channel(channel_id)
                    if channel:
                        delete_tasks.append(channel.delete(reason="Tilt-bot Server Stats Disable"))

                if delete_tasks:
                    results = await discord.utils.gather(*delete_tasks, return_exceptions=True)
                    for i, result in enumerate(results):
                        ch_id = channel_ids_to_delete[i] # Rough mapping, assumes order preserved
                        if isinstance(result, discord.NotFound):
                             logger.warning(f"Channel {ch_id} not found during serverstats disable for guild {guild_id}.")
                        elif isinstance(result, discord.Forbidden):
                             logger.error(f"Missing permissions to delete channel {ch_id} during serverstats disable for guild {guild_id}.")
                             # Send specific error if possible, maybe aggregate errors
                        elif isinstance(result, Exception):
                             logger.error(f"Error deleting channel {ch_id} during serverstats disable for guild {guild_id}: {result}")
                        else:
                            deleted_count += 1
                else:
                    logger.info(f"No valid channel IDs found to delete for server stats disable in guild {guild_id}.")


                # Clear relevant DB entries regardless of deletion success/failure
                await set_guild_config_value(guild_id, "stats_category_id", None)
                await set_guild_config_value(guild_id, "member_count_channel_id", None)
                await set_guild_config_value(guild_id, "bot_count_channel_id", None)
                await set_guild_config_value(guild_id, "role_count_channel_id", None)

                await interaction.followup.send(f"✅ Server stats channels disabled. Successfully deleted {deleted_count} channels/category.", ephemeral=True)

            except discord.Forbidden:
                 await interaction.followup.send("❌ I seem to be missing initial permissions to fetch channels or final permissions to delete.", ephemeral=True)
            except Exception as e:
                logger.error(f"Error in serverstats setup (disable) for guild {guild_id}: {e}", exc_info=True)
                await interaction.followup.send("❌ An error occurred while disabling server stats.", ephemeral=True)


    @setup_group.command(name="counting", description="Set or remove the counting game channel.")
    @app_commands.describe(action="Choose to set or unset the channel.", channel="The channel for the counting game.")
    @app_commands.choices(action=[
        app_commands.Choice(name="Set", value="set"),
        app_commands.Choice(name="Unset", value="unset")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_counting(self, interaction: discord.Interaction, action: str, channel: discord.TextChannel = None):
        """Sets or unsets the counting channel and resets the count."""
        guild_id = interaction.guild.id
        try:
            if action == "set":
                if channel is None:
                    await interaction.response.send_message("❌ You must specify a channel to set.", ephemeral=True)
                    return
                # Set channel and reset count/last counter using helper
                await set_guild_config_value(guild_id, "counting_channel_id", channel.id)
                await set_guild_config_value(guild_id, "current_count", 0)
                await set_guild_config_value(guild_id, "last_counter_id", None)
                await interaction.response.send_message(f"✅ Counting channel has been set to {channel.mention}. The count starts at 1!", ephemeral=True)
            else:  # Unset
                # Unset channel and reset count/last counter using helper
                await set_guild_config_value(guild_id, "counting_channel_id", None)
                await set_guild_config_value(guild_id, "current_count", 0)
                await set_guild_config_value(guild_id, "last_counter_id", None)
                await interaction.response.send_message("✅ Counting channel has been unset.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting counting channel for guild {guild_id}: {e}", exc_info=True)
            await interaction.response.send_message("❌ An error occurred while updating the counting channel setting.", ephemeral=True)


async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(SetupCommands(bot))
