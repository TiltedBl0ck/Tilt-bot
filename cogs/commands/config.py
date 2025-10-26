import discord
from discord import app_commands
from discord.ext import commands
# Updated import: Use the new helper functions/pool from the asyncpg version
from cogs.utils.db import pool, set_guild_config_value, get_guild_config 
import logging

logger = logging.getLogger(__name__)

# --- Modals for Configuration ---
class WelcomeConfigModal(discord.ui.Modal, title='Configure Welcome Message'):
    message = discord.ui.TextInput(
        label='Welcome Message Template',
        style=discord.TextStyle.paragraph,
        placeholder='Example: Welcome {member} to {guild}! Enjoy your stay.',
        required=True,
        max_length=1000,
    )

    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        # Use the new database function
        success = await set_guild_config_value(self.guild_id, 'welcome_message', self.message.value)
        if success:
            await interaction.response.send_message(f'✅ Welcome message updated!\n\n**Preview:**\n{self.message.value.format(member=interaction.user.mention, guild=interaction.guild.name)}', ephemeral=True)
        else:
            await interaction.response.send_message('❌ Failed to update the welcome message in the database.', ephemeral=True)


class GoodbyeConfigModal(discord.ui.Modal, title='Configure Goodbye Message'):
    message = discord.ui.TextInput(
        label='Goodbye Message Template',
        style=discord.TextStyle.paragraph,
        placeholder='Example: Goodbye {member}. We hope to see you again!',
        required=True,
        max_length=1000,
    )

    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        # Use the new database function
        success = await set_guild_config_value(self.guild_id, 'goodbye_message', self.message.value)
        if success:
             await interaction.response.send_message(f'✅ Goodbye message updated!\n\n**Preview:**\n{self.message.value.format(member=interaction.user.display_name)}', ephemeral=True) # Cannot mention user who left
        else:
            await interaction.response.send_message('❌ Failed to update the goodbye message in the database.', ephemeral=True)


# --- Config Command Cog ---
class ConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    config_group = app_commands.Group(name="config", description="Configure bot settings like welcome/goodbye messages.")

    @config_group.command(name="welcome", description="Configure the welcome message.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_welcome(self, interaction: discord.Interaction):
        """Opens a modal to configure the server's welcome message."""
        if not interaction.guild_id:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
            
        # Check if welcome system is even set up
        config = await get_guild_config(interaction.guild_id)
        if not config or not config['welcome_channel_id']:
            await interaction.response.send_message("The welcome system hasn't been set up yet. Use `/setup welcome` first.", ephemeral=True)
            return

        modal = WelcomeConfigModal(interaction.guild_id)
        # Pre-fill modal if message exists
        if config and config['welcome_message']:
             modal.message.default = config['welcome_message']
             
        await interaction.response.send_modal(modal)

    @config_group.command(name="goodbye", description="Configure the goodbye message.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_goodbye(self, interaction: discord.Interaction):
        """Opens a modal to configure the server's goodbye message."""
        if not interaction.guild_id:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        # Check if goodbye system is set up
        config = await get_guild_config(interaction.guild_id)
        if not config or not config['goodbye_channel_id']:
            await interaction.response.send_message("The goodbye system hasn't been set up yet. Use `/setup goodbye` first.", ephemeral=True)
            return

        modal = GoodbyeConfigModal(interaction.guild_id)
        # Pre-fill modal if message exists
        if config and config['goodbye_message']:
             modal.message.default = config['goodbye_message']
             
        await interaction.response.send_modal(modal)

    @config_welcome.error
    @config_goodbye.error
    async def config_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("You need the `Manage Server` permission to use this command.", ephemeral=True)
        else:
            logger.error(f"Error in config command: {error}")
            await interaction.response.send_message("An unexpected error occurred.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ConfigCog(bot))
