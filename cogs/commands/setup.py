import discord
from discord import app_commands
from discord.ext import commands
from cogs.utils.db import get_db_connection

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
        conn = await get_db_connection()
        try:
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
        finally:
            if conn:
                await conn.close()

    @setup_group.command(name="goodbye", description="Set or remove the goodbye message channel.")
    @app_commands.describe(action="Choose to set or unset the channel.", channel="The channel for goodbye messages.")
    @app_commands.choices(action=[
        app_commands.Choice(name="Set", value="set"),
        app_commands.Choice(name="Unset", value="unset")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_goodbye(self, interaction: discord.Interaction, action: str, channel: discord.TextChannel = None):
        """Sets or unsets the goodbye channel in the database."""
        conn = await get_db_connection()
        try:
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
        finally:
            if conn:
                await conn.close()

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(SetupCommands(bot))

