import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

class HelpCommand(commands.Cog):
    """A command to display all available bot commands."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Displays a list of all available commands.")
    async def help(self, interaction: discord.Interaction):
        """Builds and sends an embed with all commands, sorted by cog."""
        await interaction.response.defer(ephemeral=True)
        
        embed = discord.Embed(
            title="Tilt-Bot Help Menu",
            description="Here is a list of all available commands:",
            color=discord.Color.purple(),
            timestamp=datetime.utcnow()
        )
        if self.bot.user.display_avatar:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        # A dictionary to hold commands sorted by their cog name
        cogs_with_commands = {}

        for name, cog in self.bot.cogs.items():
            # Skip utility cogs
            if name in ["CommandHandler", "MemberEvents", "ErrorHandler"]:
                continue
            
            # Get only slash commands from the cog
            app_commands_in_cog = cog.get_app_commands()
            if app_commands_in_cog:
                # Add cog and its commands to dictionary
                cogs_with_commands[name] = app_commands_in_cog

        # Add a field for each cog
        for name, command_list in cogs_with_commands.items():
            command_text = []
            for cmd in command_list:
                if isinstance(cmd, app_commands.Group):
                    sub_cmds = "\n".join([f"  `└ {sub.name}` - {sub.description}" for sub in cmd.commands])
                    command_text.append(f"`/{cmd.name}` - {cmd.description}\n{sub_cmds}")
                else:
                    command_text.append(f"`/{cmd.name}` - {cmd.description}")
            
            embed.add_field(name=f"**{name}**", value="\n".join(command_text), inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(HelpCommand(bot))

