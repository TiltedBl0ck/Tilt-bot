import discord
from discord import app_commands
from discord.ext import commands
from cogs.utils.db import get_db_connection
import logging

logger = logging.getLogger(__name__)

class ConfigCommands(commands.Cog):
    """Commands for configuring server-specific bot settings."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    config_group = app_commands.Group(name="config", description="Configure bot settings for this server.")

    @config_group.command(name="welcome", description="Set the custom welcome message and image.")
    @app_commands.describe(
        message="The welcome message. Use {user.mention} to mention the user.",
        image_url="An optional URL for a welcome image."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def config_welcome(self, interaction: discord.Interaction, message: str, image_url: str = None):
        """Updates the guild's welcome message configuration in the database."""
        conn = await get_db_connection()
        try:
            await conn.execute(
                "INSERT INTO guild_config (guild_id, welcome_message, welcome_image) VALUES (?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET welcome_message=excluded.welcome_message, welcome_image=excluded.welcome_image",
                (interaction.guild.id, message, image_url)
            )
            await conn.commit()
            await interaction.response.send_message("✅ Welcome configuration has been updated!", ephemeral=True)
        finally:
            if conn:
                await conn.close()

    @config_group.command(name="goodbye", description="Set the custom goodbye message and image.")
    @app_commands.describe(
        message="The goodbye message. Use {user.name} for the user's name.",
        image_url="An optional URL for a goodbye image."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def config_goodbye(self, interaction: discord.Interaction, message: str, image_url: str = None):
        """Updates the guild's goodbye message configuration in the database."""
        conn = await get_db_connection()
        try:
            await conn.execute(
                "INSERT INTO guild_config (guild_id, goodbye_message, goodbye_image) VALUES (?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET goodbye_message=excluded.goodbye_message, goodbye_image=excluded.goodbye_image",
                (interaction.guild.id, message, image_url)
            )
            await conn.commit()
            await interaction.response.send_message("✅ Goodbye configuration has been updated!", ephemeral=True)
        finally:
            if conn:
                await conn.close()

    @config_group.command(name="serverstats", description="Toggle which server statistics to display.")
    @app_commands.describe(
        members="Show the member count channel.",
        bots="Show the bot count channel.",
        roles="Show the role count channel."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def config_serverstats(self, interaction: discord.Interaction, members: bool, bots: bool, roles: bool):
        """Updates the visibility of server stats channels."""
        await interaction.response.defer(ephemeral=True)
        conn = await get_db_connection()
        try:
            cursor = await conn.execute("SELECT * FROM guild_config WHERE guild_id = ?", (interaction.guild.id,))
            config = await cursor.fetchone()

            if not config or not config["stats_category_id"]:
                await interaction.followup.send("❌ Please run `/setup serverstats` first to create the channels.", ephemeral=True)
                return

            # Toggle channels based on user input
            member_channel = interaction.guild.get_channel(config["member_count_channel_id"])
            if member_channel: await member_channel.edit(view_permission=members)
            
            bot_channel = interaction.guild.get_channel(config["bot_count_channel_id"])
            if bot_channel: await bot_channel.edit(view_permission=bots)
            
            role_channel = interaction.guild.get_channel(config["role_count_channel_id"])
            if role_channel: await role_channel.edit(view_permission=roles)

            await interaction.followup.send("✅ Server stats visibility has been updated!", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in config serverstats: {e}")
            await interaction.followup.send("❌ An error occurred while updating the channels.", ephemeral=True)
        finally:
            if conn:
                await conn.close()

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(ConfigCommands(bot))

