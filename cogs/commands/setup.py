import discord
from discord import app_commands
from discord.ext import commands
import cogs.utils.db as db_utils # Use alias for db utilities
import logging
import asyncio # For asyncio.gather

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
    @app_commands.checks.bot_has_permissions(send_messages=True, embed_links=True) # Check bot perms
    async def setup_welcome(self, interaction: discord.Interaction, action: str, channel: discord.TextChannel = None):
        """Sets or unsets the welcome channel."""
        guild_id = interaction.guild.id
        if action == "set":
            if channel is None:
                await interaction.response.send_message("❌ You must specify a channel to set.", ephemeral=True)
                return
            # Check if bot can send messages in the target channel
            if not channel.permissions_for(interaction.guild.me).send_messages or \
               not channel.permissions_for(interaction.guild.me).embed_links:
                await interaction.response.send_message(f"❌ I don't have permission to send embed messages in {channel.mention}.", ephemeral=True)
                return

            success = await db_utils.set_guild_config_value(guild_id, {"welcome_channel_id": channel.id})
            if success:
                await interaction.response.send_message(f"✅ Welcome channel has been set to {channel.mention}.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Failed to update database.", ephemeral=True)
        else: # Unset
            success = await db_utils.set_guild_config_value(guild_id, {"welcome_channel_id": None})
            if success:
                await interaction.response.send_message("✅ Welcome channel has been unset.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Failed to update database.", ephemeral=True)

    @setup_group.command(name="goodbye", description="Set or remove the goodbye message channel.")
    @app_commands.describe(action="Choose to set or unset the channel.", channel="The channel for goodbye messages.")
    @app_commands.choices(action=[
        app_commands.Choice(name="Set", value="set"),
        app_commands.Choice(name="Unset", value="unset")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.checks.bot_has_permissions(send_messages=True, embed_links=True) # Check bot perms
    async def setup_goodbye(self, interaction: discord.Interaction, action: str, channel: discord.TextChannel = None):
        """Sets or unsets the goodbye channel."""
        guild_id = interaction.guild.id
        if action == "set":
            if channel is None:
                await interaction.response.send_message("❌ You must specify a channel to set.", ephemeral=True)
                return
            # Check if bot can send messages in the target channel
            if not channel.permissions_for(interaction.guild.me).send_messages or \
               not channel.permissions_for(interaction.guild.me).embed_links:
                await interaction.response.send_message(f"❌ I don't have permission to send embed messages in {channel.mention}.", ephemeral=True)
                return

            success = await db_utils.set_guild_config_value(guild_id, {"goodbye_channel_id": channel.id})
            if success:
                await interaction.response.send_message(f"✅ Goodbye channel has been set to {channel.mention}.", ephemeral=True)
            else:
                 await interaction.response.send_message("❌ Failed to update database.", ephemeral=True)
        else: # Unset
            success = await db_utils.set_guild_config_value(guild_id, {"goodbye_channel_id": None})
            if success:
                await interaction.response.send_message("✅ Goodbye channel has been unset.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Failed to update database.", ephemeral=True)

    @setup_group.command(name="serverstats", description="Set up or remove server statistics channels.")
    @app_commands.describe(action="Enable or disable the server stats feature.")
    @app_commands.choices(action=[
        app_commands.Choice(name="Enable", value="enable"),
        app_commands.Choice(name="Disable", value="disable")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True, manage_roles=True, connect=True, view_channel=True) # Need connect/view for VCs
    async def setup_serverstats(self, interaction: discord.Interaction, action: str):
        """Creates or deletes the server stats channels and category."""
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        guild_id = guild.id

        # Get current config from cache/DB
        current_config = await db_utils.get_guild_config(guild_id)

        if action == "enable":
            # Check if already enabled
            if current_config and current_config.get("stats_category_id"):
                # Optionally verify channels still exist
                cat = guild.get_channel(current_config["stats_category_id"])
                if cat:
                    await interaction.followup.send(f"⚠️ Server stats seem to be already enabled under the '{cat.name}' category.", ephemeral=True)
                    return
                else: # Category ID exists but channel doesn't - allow re-setup
                     logger.warning(f"Stats category {current_config['stats_category_id']} not found for guild {guild_id}, allowing re-setup.")


            try:
                # --- Create Category and Channels ---
                # Permissions: Deny connect for @everyone, allow view
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True)
                }
                category = await guild.create_category("📊 Server Stats", overwrites=overwrites, reason="Tilt-bot Server Stats Setup")

                # Calculate initial counts
                member_count = guild.member_count
                bot_count = sum(1 for m in guild.members if m.bot)
                role_count = len(guild.roles) # Excludes @everyone

                # Create voice channels within the category
                members_vc = await guild.create_voice_channel(f"👥 Members: {member_count}", category=category, reason="Tilt-bot Server Stats Setup")
                bots_vc = await guild.create_voice_channel(f"🤖 Bots: {bot_count}", category=category, reason="Tilt-bot Server Stats Setup")
                roles_vc = await guild.create_voice_channel(f"📜 Roles: {role_count}", category=category, reason="Tilt-bot Server Stats Setup")

                # Apply connect=False overwrite specifically to voice channels as well (redundant but safe)
                # Overwrite objects are mutable, create new ones if needed per channel or modify existing
                vc_overwrite = discord.PermissionOverwrite(connect=False, view_channel=True)
                await members_vc.set_permissions(guild.default_role, overwrite=vc_overwrite)
                await bots_vc.set_permissions(guild.default_role, overwrite=vc_overwrite)
                await roles_vc.set_permissions(guild.default_role, overwrite=vc_overwrite)

                # --- Save IDs to Database ---
                updates = {
                    "stats_category_id": category.id,
                    "member_count_channel_id": members_vc.id,
                    "bot_count_channel_id": bots_vc.id,
                    "role_count_channel_id": roles_vc.id
                }
                success = await db_utils.set_guild_config_value(guild_id, updates)

                if success:
                    await interaction.followup.send("✅ Server stats channels have been created!", ephemeral=True)
                else:
                    # Attempt cleanup if DB write failed
                    logger.error(f"Failed to save server stats config for guild {guild_id} after creating channels.")
                    await interaction.followup.send("❌ Channels created, but failed to save configuration to database. Please try disabling and re-enabling.", ephemeral=True)
                    # Consider adding cleanup here too

            except discord.Forbidden:
                await interaction.followup.send("❌ I am missing permissions (Manage Channels, Manage Roles, Connect, View Channel) needed for server stats.", ephemeral=True)
            except discord.HTTPException as e:
                logger.error(f"HTTP error during serverstats setup (enable) for guild {guild.id}: {e.status} {e.text}", exc_info=True)
                await interaction.followup.send(f"❌ An error occurred during setup ({e.status}). Please check my permissions.", ephemeral=True)
            except Exception as e:
                logger.error(f"Error in serverstats setup (enable) for guild {guild.id}: {e}", exc_info=True)
                await interaction.followup.send("❌ An unexpected error occurred during setup.", ephemeral=True)
                # Attempt cleanup (best effort)
                try:
                    if 'category' in locals() and category: await category.delete(reason="Tilt-bot Setup Failed Cleanup")
                    if 'members_vc' in locals() and members_vc: await members_vc.delete(reason="Tilt-bot Setup Failed Cleanup")
                    if 'bots_vc' in locals() and bots_vc: await bots_vc.delete(reason="Tilt-bot Setup Failed Cleanup")
                    if 'roles_vc' in locals() and roles_vc: await roles_vc.delete(reason="Tilt-bot Setup Failed Cleanup")
                except Exception as cleanup_e:
                    logger.error(f"Error during serverstats setup cleanup for guild {guild.id}: {cleanup_e}")

        else: # Disable
            if not current_config or not current_config.get("stats_category_id"):
                await interaction.followup.send("⚠️ Server stats are not currently enabled.", ephemeral=True)
                return

            try:
                # --- Delete Channels ---
                channel_ids_to_delete = [
                    current_config.get("member_count_channel_id"),
                    current_config.get("bot_count_channel_id"),
                    current_config.get("role_count_channel_id"),
                    current_config.get("stats_category_id") # Delete category last
                ]
                delete_tasks = []
                channels_found = []

                for channel_id in filter(None, channel_ids_to_delete): # Filter out None IDs
                    channel = guild.get_channel(channel_id)
                    if channel:
                        channels_found.append(channel)
                        # Schedule deletion, category last
                        if not isinstance(channel, discord.CategoryChannel):
                             delete_tasks.append(channel.delete(reason="Tilt-bot Server Stats Disable"))

                # Schedule category deletion after other channels
                category_channel = guild.get_channel(current_config.get("stats_category_id", 0))
                if category_channel and isinstance(category_channel, discord.CategoryChannel):
                     delete_tasks.append(category_channel.delete(reason="Tilt-bot Server Stats Disable"))


                if delete_tasks:
                    results = await asyncio.gather(*delete_tasks, return_exceptions=True)
                    errors = [res for res in results if isinstance(res, Exception)]
                    deleted_count = len(results) - len(errors)

                    for error in errors:
                         if isinstance(error, discord.Forbidden):
                             await interaction.followup.send("❌ Missing permissions to delete one or more stats channels. Please delete them manually.", ephemeral=True)
                             # Don't clear DB if deletion failed due to perms
                             return
                         elif isinstance(error, discord.NotFound):
                             logger.warning(f"A stats channel was not found during deletion for guild {guild_id}.")
                         else:
                             logger.error(f"Error deleting stats channel for guild {guild_id}: {error}", exc_info=True)
                             # Continue to try and clear DB even if deletion had other errors


                else:
                    deleted_count = 0
                    logger.warning(f"No stats channels found to delete for guild {guild_id}, despite config existing.")


                # --- Clear from DB ---
                updates = {
                    "stats_category_id": None,
                    "member_count_channel_id": None,
                    "bot_count_channel_id": None,
                    "role_count_channel_id": None
                }
                success = await db_utils.set_guild_config_value(guild_id, updates)

                if success:
                    await interaction.followup.send(f"✅ Server stats channels ({deleted_count}) have been deleted and configuration cleared.", ephemeral=True)
                else:
                    await interaction.followup.send(f"⚠️ Server stats channels ({deleted_count}) deleted, but failed to clear configuration from database.", ephemeral=True)


            except discord.Forbidden: # Should be caught by individual deletes, but as fallback
                 await interaction.followup.send("❌ I seem to be missing permissions to delete channels.", ephemeral=True)
            except discord.HTTPException as e:
                logger.error(f"HTTP error during serverstats setup (disable) for guild {guild.id}: {e.status} {e.text}", exc_info=True)
                await interaction.followup.send(f"❌ An error occurred during cleanup ({e.status}).", ephemeral=True)
            except Exception as e:
                logger.error(f"Error in serverstats setup (disable) for guild {guild.id}: {e}", exc_info=True)
                await interaction.followup.send("❌ An unexpected error occurred while disabling server stats.", ephemeral=True)


    @setup_group.command(name="counting", description="Set or remove the counting game channel.")
    @app_commands.describe(action="Choose to set or unset the channel.", channel="The channel for the counting game.")
    @app_commands.choices(action=[
        app_commands.Choice(name="Set", value="set"),
        app_commands.Choice(name="Unset", value="unset")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True, add_reactions=True) # Need perms for counting game logic
    async def setup_counting(self, interaction: discord.Interaction, action: str, channel: discord.TextChannel = None):
        """Sets or unsets the counting channel and resets the count."""
        guild_id = interaction.guild.id
        if action == "set":
            if channel is None:
                await interaction.response.send_message("❌ You must specify a channel to set.", ephemeral=True)
                return

            # Check bot permissions in the target channel
            perms = channel.permissions_for(interaction.guild.me)
            if not perms.manage_messages or not perms.read_message_history or not perms.add_reactions or not perms.send_messages:
                 await interaction.response.send_message(f"❌ I'm missing permissions in {channel.mention} (Need: Send Messages, Manage Messages, Read History, Add Reactions).", ephemeral=True)
                 return

            # Set channel and reset count/last counter
            updates = {
                "counting_channel_id": channel.id,
                "current_count": 0,
                "last_counter_id": None
            }
            success = await db_utils.set_guild_config_value(guild_id, updates)
            if success:
                await interaction.response.send_message(f"✅ Counting channel has been set to {channel.mention}. The count starts at 1!", ephemeral=True)
            else:
                 await interaction.response.send_message("❌ Failed to update database.", ephemeral=True)

        else:  # Unset
            # Unset channel and reset count/last counter
            updates = {
                "counting_channel_id": None,
                "current_count": 0,
                "last_counter_id": None
            }
            success = await db_utils.set_guild_config_value(guild_id, updates)
            if success:
                 await interaction.response.send_message("✅ Counting channel has been unset.", ephemeral=True)
            else:
                 await interaction.response.send_message("❌ Failed to update database.", ephemeral=True)

    @setup_group.command(name="wotd", description="Set or remove the Word of the Day channel.")
    @app_commands.describe(action="Choose to set or unset the channel.", channel="The channel for WOTD messages.")
    @app_commands.choices(action=[
        app_commands.Choice(name="Set", value="set"),
        app_commands.Choice(name="Unset", value="unset")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.checks.bot_has_permissions(send_messages=True, embed_links=True)
    async def setup_wotd(self, interaction: discord.Interaction, action: str, channel: discord.TextChannel = None):
        """Sets or unsets the Word of the Day channel."""
        guild_id = interaction.guild.id
        if action == "set":
            if channel is None:
                await interaction.response.send_message("❌ You must specify a channel to set.", ephemeral=True)
                return
            
            # Check perms
            if not channel.permissions_for(interaction.guild.me).send_messages or \
               not channel.permissions_for(interaction.guild.me).embed_links:
                await interaction.response.send_message(f"❌ I don't have permission to send embed messages in {channel.mention}.", ephemeral=True)
                return

            success = await db_utils.set_guild_config_value(guild_id, {"wotd_channel_id": channel.id})
            if success:
                await interaction.response.send_message(f"✅ Word of the Day channel has been set to {channel.mention}.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Failed to update database.", ephemeral=True)
        else: # Unset
            success = await db_utils.set_guild_config_value(guild_id, {"wotd_channel_id": None})
            if success:
                await interaction.response.send_message("✅ Word of the Day channel has been unset.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Failed to update database.", ephemeral=True)

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(SetupCommands(bot))