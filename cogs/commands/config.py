import discord
from discord import app_commands
from discord.ext import commands
from cogs.utils.db import get_db_connection

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

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(ConfigCommands(bot))

