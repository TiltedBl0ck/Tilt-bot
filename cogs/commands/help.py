import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from cogs.utils.db import get_db
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

        # Get the database connection
        db = await get_db()
        guild_id = interaction.guild.id

        # Fetch setup status for different features
        welcome_cursor = await db.execute("SELECT channel_id FROM welcome WHERE guild_id = ?", (guild_id,))
        welcome_data = await welcome_cursor.fetchone()
        
        goodbye_cursor = await db.execute("SELECT channel_id FROM goodbye WHERE guild_id = ?", (guild_id,))
        goodbye_data = await goodbye_cursor.fetchone()
        
        counting_cursor = await db.execute("SELECT channel_id FROM counting WHERE guild_id = ?", (guild_id,))
        counting_data = await counting_cursor.fetchone()

        stats_cursor = await db.execute("SELECT channel_type FROM serverstats WHERE guild_id = ?", (guild_id,))
        stats_data = [row[0] for row in await stats_cursor.fetchall()]
        all_stats_setup = all(stat_type in stats_data for stat_type in ["total", "members", "bots"])

        # Determine status for setup commands
        welcome_status = "✅" if welcome_data else "❌"
        goodbye_status = "✅" if goodbye_data else "❌"
        serverstats_status = "✅" if all_stats_setup else "❌"
        counting_status = "✅" if counting_data else "❌"

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
                            elif sub.name == "counting":
                                sub_cmds_text.append(f"  `└ {sub.name}` {counting_status} - {sub.description}")
                            else:
                                sub_cmds_text.append(f"  `└ {sub.name}` - {sub.description}")
                        else:
                            sub_cmds_text.append(f"  `└ {sub.name}` - {sub.description}")
                    
                    sub_cmds_str = "\n".join(sub_cmds_text)
                    command_text.append(f"`/{cmd.name}` - {cmd.description}\n{sub_cmds_str}")
                else:
                    command_text.append(f"`/{cmd.name}` - {cmd.description}")
            
            embed.add_field(name=f"**{name}**", value="\n".join(command_text), inline=False)

        embed.set_footer(text="Tilt-bot | Made by tilted.", icon_url=self.bot.user.avatar.url)

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

