import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone # Use timezone-aware datetime
import cogs.utils.db as db_utils # Use alias for db utilities
import logging

logger = logging.getLogger(__name__)

class HelpCommand(commands.Cog):
    """A command to display all available bot commands."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def build_help_embed(self, interaction: discord.Interaction) -> discord.Embed:
        """Builds and returns the help embed with command statuses."""
        embed = discord.Embed(
            title="Tilt-Bot Help Menu",
            description="Here is a list of all available commands:",
            color=discord.Color.purple(),
            timestamp=datetime.now(timezone.utc) # Use timezone-aware now
        )
        # Use bot.user safely
        bot_user = self.bot.user
        if bot_user and bot_user.display_avatar:
            embed.set_thumbnail(url=bot_user.display_avatar.url)

        # Get the current server's configuration from cache/DB
        config = await db_utils.get_guild_config(interaction.guild.id)

        # Determine status for setup commands safely using .get()
        welcome_status = "✅" if config and config.get("welcome_channel_id") else "❌"
        goodbye_status = "✅" if config and config.get("goodbye_channel_id") else "❌"
        serverstats_status = "✅" if config and config.get("stats_category_id") else "❌"
        counting_status = "✅" if config and config.get("counting_channel_id") else "❌"

        cogs_with_commands = {}
        # Exclude specific cogs from the help menu
        excluded_cogs = ["CommandHandler", "MemberEvents", "ErrorHandler", "HelpCommand", "Gemini", "Puter", "SetupCommands", "ConfigCommands"]

        # Add Setup and Config Groups Manually
        setup_cog = self.bot.get_cog("SetupCommands")
        if setup_cog:
            for cmd in setup_cog.get_app_commands():
                if isinstance(cmd, app_commands.Group) and cmd.name == "setup":
                    cogs_with_commands["⚙️ Setup"] = cmd.commands
                    break

        config_cog = self.bot.get_cog("ConfigCommands")
        if config_cog:
            for cmd in config_cog.get_app_commands():
                if isinstance(cmd, app_commands.Group) and cmd.name == "config":
                    cogs_with_commands["🔧 Config"] = cmd.commands
                    break

        # Add Gemini cog manually (Renaming to AI Chat for user friendliness)
        gemini_cog = self.bot.get_cog("Gemini")
        if gemini_cog:
            cogs_with_commands["🧠 AI Chat"] = gemini_cog.get_app_commands()


        # Add remaining cogs
        for name, cog in self.bot.cogs.items():
            if name in excluded_cogs or name in ["SetupCommands", "ConfigCommands"]:
                continue

            app_commands_in_cog = cog.get_app_commands()
            if app_commands_in_cog:
                cog_title = name.replace("Command", "").replace("Commands", "")
                if cog_title not in cogs_with_commands:
                     cogs_with_commands[cog_title] = app_commands_in_cog

        # Build the embed fields
        for name, command_list in cogs_with_commands.items():
            command_text = []
            is_setup_or_config = name in ["⚙️ Setup", "🔧 Config"]

            for cmd in command_list:
                if is_setup_or_config:
                    status = ""
                    if name == "⚙️ Setup":
                        if cmd.name == "welcome": status = welcome_status
                        elif cmd.name == "goodbye": status = goodbye_status
                        elif cmd.name == "serverstats": status = serverstats_status
                        elif cmd.name == "counting": status = counting_status
                    # For config commands, no status needed typically
                    # Ensure cmd.parent is accessed correctly if needed (it should be set for subcommands)
                    parent_name = cmd.parent.name if cmd.parent else "[error]"
                    command_text.append(f"  `└ /{parent_name} {cmd.name}` {status} - {cmd.description}")

                elif isinstance(cmd, app_commands.Group):
                    sub_cmds_text = [f"  `└ {sub.name}` - {sub.description}" for sub in cmd.commands]
                    sub_cmds_str = "\n".join(sub_cmds_text)
                    command_text.append(f"`/{cmd.name}` - {cmd.description}\n{sub_cmds_str}")
                else:
                    command_text.append(f"`/{cmd.name}` - {cmd.description}")

            if command_text:
                field_title = f"**{name}** (`/{'setup' if name == '⚙️ Setup' else 'config' if name == '🔧 Config' else ''}`)" if is_setup_or_config else f"**{name}**"
                embed.add_field(name=field_title, value="\n".join(command_text), inline=False)

        # Add the bot version to the footer if available
        bot_version = getattr(self.bot, 'version', None)
        embed.set_footer(text=f"Tilt-bot v{bot_version}" if bot_version else "Tilt-bot")


        return embed

    @app_commands.command(name="help", description="Displays a list of all available commands.")
    async def help(self, interaction: discord.Interaction):
        """Builds and sends an embed with all commands, sorted by cog."""
        # Check if guild exists - interaction in DMs won't have guild
        if not interaction.guild:
             await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
             return

        await interaction.response.defer(ephemeral=True)

        try:
            embed = await self.build_help_embed(interaction)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error building help command for guild {interaction.guild.id}: {e}", exc_info=True)
            try:
                await interaction.followup.send("❌ An error occurred while building the help message.", ephemeral=True)
            except discord.InteractionResponded: # If followup fails, maybe original response failed?
                 pass # Logged already


async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(HelpCommand(bot))