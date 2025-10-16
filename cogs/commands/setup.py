import discord
from discord import app_commands
from discord.ext import commands
from cogs.utils.db import get_db_connection
import logging

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
        async with get_db_connection() as conn:
            if action == "set":
                if channel is None:
                    await interaction.response.send_message("❌ You must specify a channel to set.", ephemeral=True)
                    return
                await conn.execute("INSERT INTO guild_config (guild_id, welcome_channel_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET welcome_channel_id=excluded.welcome_channel_id", (interaction.guild.id, channel.id))
                await interaction.response.send_message(f"✅ Welcome channel has been set to {channel.mention}.", ephemeral=True)
            else: # Unset
                await conn.execute("UPDATE guild_config SET welcome_channel_id = NULL WHERE guild_id = ?", (interaction.guild.id,))
                await interaction.response.send_message("✅ Welcome channel has been unset.", ephemeral=True)
            await conn.commit()

    @setup_group.command(name="goodbye", description="Set or remove the goodbye message channel.")
    @app_commands.describe(action="Choose to set or unset the channel.", channel="The channel for goodbye messages.")
    @app_commands.choices(action=[
        app_commands.Choice(name="Set", value="set"),
        app_commands.Choice(name="Unset", value="unset")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_goodbye(self, interaction: discord.Interaction, action: str, channel: discord.TextChannel = None):
        """Sets or unsets the goodbye channel in the database."""
        async with get_db_connection() as conn:
            if action == "set":
                if channel is None:
                    await interaction.response.send_message("❌ You must specify a channel to set.", ephemeral=True)
                    return
                await conn.execute("INSERT INTO guild_config (guild_id, goodbye_channel_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET goodbye_channel_id=excluded.goodbye_channel_id", (interaction.guild.id, channel.id))
                await interaction.response.send_message(f"✅ Goodbye channel has been set to {channel.mention}.", ephemeral=True)
            else: # Unset
                await conn.execute("UPDATE guild_config SET goodbye_channel_id = NULL WHERE guild_id = ?", (interaction.guild.id,))
                await interaction.response.send_message("✅ Goodbye channel has been unset.", ephemeral=True)
            await conn.commit()

    @setup_group.command(name="serverstats", description="Set up server statistics channels.")
    @app_commands.describe(action="Enable or disable the server stats feature.")
    @app_commands.choices(action=[
        app_commands.Choice(name="Enable", value="enable"),
        app_commands.Choice(name="Disable", value="disable")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_serverstats(self, interaction: discord.Interaction, action: str):
        """Creates or deletes the server stats channels and category."""
        await interaction.response.defer(ephemeral=True)
        try:
            async with get_db_connection() as conn:
                if action == "enable":
                    # Create category and channels
                    overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(connect=False)}
                    category = await interaction.guild.create_category("📊 Server Stats", overwrites=overwrites)
                    members = await interaction.guild.create_voice_channel(f"👥 Members: {interaction.guild.member_count}", category=category)
                    bots = await interaction.guild.create_voice_channel(f"🤖 Bots: {sum(1 for m in interaction.guild.members if m.bot)}", category=category)
                    roles = await interaction.guild.create_voice_channel(f"📜 Roles: {len(interaction.guild.roles)}", category=category)

                    # Save IDs to database
                    await conn.execute(
                        "INSERT INTO guild_config (guild_id, stats_category_id, member_count_channel_id, bot_count_channel_id, role_count_channel_id) VALUES (?, ?, ?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET stats_category_id=excluded.stats_category_id, member_count_channel_id=excluded.member_count_channel_id, bot_count_channel_id=excluded.bot_count_channel_id, role_count_channel_id=excluded.role_count_channel_id",
                        (interaction.guild.id, category.id, members.id, bots.id, roles.id)
                    )
                    await conn.commit()
                    await interaction.followup.send("✅ Server stats channels have been created!", ephemeral=True)
                else: # Disable
                    cursor = await conn.execute("SELECT stats_category_id, member_count_channel_id, bot_count_channel_id, role_count_channel_id FROM guild_config WHERE guild_id = ?", (interaction.guild.id,))
                    config = await cursor.fetchone()
                    if config:
                        for channel_id in [config["member_count_channel_id"], config["bot_count_channel_id"], config["role_count_channel_id"], config["stats_category_id"]]:
                            if channel_id:
                                channel = interaction.guild.get_channel(channel_id)
                                if channel:
                                    await channel.delete()
                    # Clear from DB
                    await conn.execute("UPDATE guild_config SET stats_category_id=NULL, member_count_channel_id=NULL, bot_count_channel_id=NULL, role_count_channel_id=NULL WHERE guild_id = ?", (interaction.guild.id,))
                    await conn.commit()
                    await interaction.followup.send("✅ Server stats channels have been deleted.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ I am missing permissions to manage channels.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in serverstats setup: {e}")
            await interaction.followup.send("❌ An error occurred.", ephemeral=True)

    @setup_group.command(name="counting", description="Set or remove the counting game channel.")
    @app_commands.describe(action="Choose to set or unset the channel.", channel="The channel for the counting game.")
    @app_commands.choices(action=[
        app_commands.Choice(name="Set", value="set"),
        app_commands.Choice(name="Unset", value="unset")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_counting(self, interaction: discord.Interaction, action: str, channel: discord.TextChannel = None):
        """Sets or unsets the counting channel and resets the count."""
        async with get_db_connection() as conn:
            if action == "set":
                if channel is None:
                    await interaction.response.send_message("❌ You must specify a channel to set.", ephemeral=True)
                    return
                # Set channel and reset count
                await conn.execute(
                    "INSERT INTO guild_config (guild_id, counting_channel_id, current_count, last_counter_id) VALUES (?, ?, 0, NULL) ON CONFLICT(guild_id) DO UPDATE SET counting_channel_id=excluded.counting_channel_id, current_count=0, last_counter_id=NULL",
                    (interaction.guild.id, channel.id)
                )
                await interaction.response.send_message(f"✅ Counting channel has been set to {channel.mention}. The count starts at 1!", ephemeral=True)
            else:  # Unset
                await conn.execute("UPDATE guild_config SET counting_channel_id = NULL, current_count = 0, last_counter_id = NULL WHERE guild_id = ?", (interaction.guild.id,))
                await interaction.response.send_message("✅ Counting channel has been unset.", ephemeral=True)
            await conn.commit()


async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(SetupCommands(bot))
