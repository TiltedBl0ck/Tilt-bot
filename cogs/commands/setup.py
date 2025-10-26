import discord
from discord import app_commands
from discord.ext import commands
# Updated import
from cogs.utils.db import set_guild_config_value, get_guild_config
import logging

logger = logging.getLogger(__name__)

# --- Views for Setup ---

class FeatureSelectView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.feature = None # To store selected feature

    @discord.ui.select(
        placeholder="Choose a feature to set up...",
        options=[
            discord.SelectOption(label="Welcome Messages", value="welcome", emoji="👋", description="Set the channel for welcome messages."),
            discord.SelectOption(label="Goodbye Messages", value="goodbye", emoji="🚪", description="Set the channel for goodbye messages."),
            discord.SelectOption(label="Server Stats", value="serverstats", emoji="📊", description="Set up channels to display member/bot counts."),
            discord.SelectOption(label="Counting Game", value="counting", emoji="🔢", description="Set the channel for the counting game."),
            # Add other features here
        ]
    )
    async def select_feature(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.feature = select.values[0]
        
        # Check if user has necessary permissions based on feature
        if self.feature in ["welcome", "goodbye", "serverstats", "counting"]:
            if not interaction.user.guild_permissions.manage_guild:
                await interaction.response.send_message("You need the `Manage Server` permission to set up this feature.", ephemeral=True)
                self.stop()
                return

        # Disable the select menu after choosing
        select.disabled = True
        
        # Add the channel select dropdown
        self.add_item(ChannelSelectDropdown(self.feature))
        await interaction.response.edit_message(content=f"Okay, select the channel for **{self.feature.replace('_', ' ').title()}**:", view=self)


class ChannelSelectDropdown(discord.ui.ChannelSelect):
    def __init__(self, feature_type: str):
        self.feature_type = feature_type
        # Determine channel types based on feature
        if feature_type == "serverstats":
             channel_types = [discord.ChannelType.voice, discord.ChannelType.stage_voice]
             placeholder = "Select a Voice/Stage channel for stats"
        else: # welcome, goodbye, counting
             channel_types = [discord.ChannelType.text, discord.ChannelType.news, discord.ChannelType.private_thread, discord.ChannelType.public_thread]
             placeholder = "Select a Text/Announcement/Thread channel"

        super().__init__(
            placeholder=placeholder,
            channel_types=channel_types,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        guild_id = interaction.guild_id

        if not guild_id: # Should not happen in guild command, but good check
             await interaction.response.edit_message(content="Error: Guild ID not found.", view=None)
             return

        success = False
        db_column = None
        
        if self.feature_type == "welcome":
            db_column = "welcome_channel_id"
        elif self.feature_type == "goodbye":
            db_column = "goodbye_channel_id"
        elif self.feature_type == "counting":
            db_column = "counting_channel_id"
        elif self.feature_type == "serverstats":
             # Server stats setup needs special handling (creating/naming channels)
             await self.setup_server_stats(interaction, channel)
             return # Exit early as setup_server_stats handles the response

        # Update database for welcome/goodbye/counting
        if db_column:
             success = await set_guild_config_value(guild_id, db_column, channel.id)

        if success:
             feature_name = self.feature_type.replace('_', ' ').title()
             await interaction.response.edit_message(content=f"✅ Successfully set the {feature_name} channel to {channel.mention}!", view=None)
        else:
             await interaction.response.edit_message(content=f"❌ Failed to update the database for {self.feature_type}.", view=None)

    async def setup_server_stats(self, interaction: discord.Interaction, category_channel: discord.CategoryChannel | discord.VoiceChannel | discord.StageChannel):
        """Handles the specific logic for setting up server stats channels."""
        guild = interaction.guild
        guild_id = interaction.guild_id

        if not guild or not guild_id:
            await interaction.response.edit_message(content="Error: Could not find server information.", view=None)
            return
            
        # Determine category - if user selected voice channel, use its category
        category = None
        if isinstance(category_channel, (discord.VoiceChannel, discord.StageChannel)):
            category = category_channel.category
        elif isinstance(category_channel, discord.CategoryChannel): # Allow selecting category directly? - Let's stick to voice/stage for now
             # category = category_channel
             await interaction.response.edit_message(content="Please select a Voice or Stage channel within the desired category.", view=None)
             return
        
        if not category:
            await interaction.response.edit_message(content="Could not determine the category. Please select a voice/stage channel inside a category.", view=None)
            return

        # Check bot permissions in the category
        bot_perms = category.permissions_for(guild.me)
        if not bot_perms.manage_channels or not bot_perms.connect:
            await interaction.response.edit_message(content=f"❌ I need **Manage Channels** and **Connect** permissions in the '{category.name}' category to create and manage stat channels.", view=None)
            return
            
        await interaction.response.edit_message(content=f"⚙️ Setting up server stats in the '{category.name}' category...", view=None)

        try:
            # Create Member Count Channel
            member_count_name = f"📊 Members: {guild.member_count}"
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=False) # Deny @everyone connection
            }
            member_channel = await category.create_voice_channel(name=member_count_name, overwrites=overwrites, reason="Server Stats Setup")
            success_member = await set_guild_config_value(guild_id, "member_count_channel", member_channel.id)

            # Create Bot Count Channel (Optional, maybe ask?)
            # For simplicity, let's create both for now
            bot_count = sum(1 for member in guild.members if member.bot)
            bot_count_name = f"🤖 Bots: {bot_count}"
            bot_channel = await category.create_voice_channel(name=bot_count_name, overwrites=overwrites, reason="Server Stats Setup")
            success_bot = await set_guild_config_value(guild_id, "bot_count_channel", bot_channel.id)

            if success_member and success_bot:
                await interaction.followup.send(f"✅ Successfully created server stats channels in '{category.name}': {member_channel.mention} and {bot_channel.mention}", ephemeral=True)
            else:
                 await interaction.followup.send("❌ Created channels, but failed to save settings to the database.", ephemeral=True)

        except discord.Forbidden:
             await interaction.followup.send(f"❌ I lack permissions to create channels in the '{category.name}' category.", ephemeral=True)
        except discord.HTTPException as e:
             logger.error(f"HTTP Error creating stats channels for guild {guild_id}: {e}")
             await interaction.followup.send(f"❌ An API error occurred: {e}", ephemeral=True)
        except Exception as e:
            logger.error(f"Unexpected error setting up stats for guild {guild_id}: {e}")
            await interaction.followup.send("❌ An unexpected error occurred during setup.", ephemeral=True)


# --- Setup Command Cog ---
class SetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setup", description="Interactively set up bot features.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup(self, interaction: discord.Interaction):
        """Starts the interactive setup process for bot features."""
        if not interaction.guild_id:
             await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
             return
             
        view = FeatureSelectView(interaction.guild_id)
        await interaction.response.send_message("Select the feature you want to set up:", view=view, ephemeral=True)

    @setup.error
    async def setup_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("You need the `Manage Server` permission to use this command.", ephemeral=True)
        else:
            logger.error(f"Error in setup command: {error}")
            await interaction.response.send_message("An unexpected error occurred.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(SetupCog(bot))
