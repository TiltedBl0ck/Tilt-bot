import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from cogs.utils.db import get_db_connection
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
            timestamp=datetime.utcnow()
        )
        if self.bot.user.display_avatar:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        # Get the current server's configuration for status checks using an async context manager
        config = None
        async with get_db_connection() as conn:
            cursor = await conn.execute("SELECT * FROM guild_config WHERE guild_id = ?", (interaction.guild_id,))
            config = await cursor.fetchone()

        # Determine status for setup commands
        welcome_status = "✅" if config and config["welcome_channel_id"] else "❌"
        goodbye_status = "✅" if config and config["goodbye_channel_id"] else "❌"
        serverstats_status = "✅" if config and config["stats_category_id"] else "❌"

        cogs_with_commands = {}
        # Exclude this cog and other handlers from the help menu
        excluded_cogs = ["CommandHandler", "MemberEvents", "ErrorHandler", "HelpCommand", "Gemini"]
        
        # Add the Gemini cog manually to control its position and title
        gemini_cog = self.bot.get_cog("Gemini")
        if gemini_cog:
            cogs_with_commands["AI Chat"] = gemini_cog.get_app_commands()

        for name, cog in self.bot.cogs.items():
            if name in excluded_cogs:
                continue
            
            app_commands_in_cog = cog.get_app_commands()
            if app_commands_in_cog:
                # Use a more user-friendly name for the cog
                cog_title = name.replace("Command", "").replace("Commands", "")
                cogs_with_commands[cog_title] = app_commands_in_cog

        for name, command_list in cogs_with_commands.items():
            command_text = []
            for cmd in command_list:
                if isinstance(cmd, app_commands.Group):
                    sub_cmds_text = []
                    for sub in cmd.commands:
                        # Add status indicators for specific setup commands
                        if cmd.name == "setup":
                            if sub.name == "welcome":
                                sub_cmds_text.append(f"  `└ {sub.name}` {welcome_status} - {sub.description}")
                            elif sub.name == "goodbye":
                                sub_cmds_text.append(f"  `└ {sub.name}` {goodbye_status} - {sub.description}")
                            elif sub.name == "serverstats":
                                sub_cmds_text.append(f"  `└ {sub.name}` {serverstats_status} - {sub.description}")
                            else:
                                sub_cmds_text.append(f"  `└ {sub.name}` - {sub.description}")
                        else:
                            sub_cmds_text.append(f"  `└ {sub.name}` - {sub.description}")
                    
                    sub_cmds_str = "\n".join(sub_cmds_text)
                    command_text.append(f"`/{cmd.name}` - {cmd.description}\n{sub_cmds_str}")
                else:
                    command_text.append(f"`/{cmd.name}` - {cmd.description}")
            
            embed.add_field(name=f"**{name}**", value="\n".join(command_text), inline=False)
        
        # Add the bot version to the footer
        embed.set_footer(text=f"Tilt-bot v{self.bot.version}")
        
        return embed

    @app_commands.command(name="help", description="Displays a list of all available commands.")
    async def help(self, interaction: discord.Interaction):
        """Builds and sends an embed with all commands, sorted by cog."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            embed = await self.build_help_embed(interaction)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error building help command: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while building the help message.", ephemeral=True)

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(HelpCommand(bot))

