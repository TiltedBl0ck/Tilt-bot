import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

class HelpCog(commands.Cog, name="Help"):
    """A command to display all available bot commands in a single embed."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def build_help_embed(self) -> discord.Embed:
        """Creates the help embed with all commands."""
        embed = discord.Embed(
            title="Tilt-Bot Help Menu",
            description="Here is a list of all available commands, sorted by category.",
            color=discord.Color.purple(),
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text=f"Tilt-Bot v{self.bot.version} | Coded by TiltedBl0ck")

        # Iterate through cogs and add their commands to the embed
        for cog_name, cog in self.bot.cogs.items():
            # Skip cogs that shouldn't be in the help menu
            if cog_name in ["Help", "ErrorHandler"] or not hasattr(cog, 'get_app_commands'):
                continue

            # Get a list of command descriptions
            commands_list = [
                f"`/{command.name}` - {command.description or 'No description provided.'}"
                for command in cog.get_app_commands()
            ]
            
            # Add a field for the cog if it has any commands
            if commands_list:
                embed.add_field(
                    name=f"**{cog.qualified_name}**",
                    value="\n".join(commands_list),
                    inline=False
                )
        return embed

    @app_commands.command(name="help", description="Displays a list of all available commands.")
    async def help(self, interaction: discord.Interaction):
        """
        The main help command. It defers the response immediately to prevent timeouts,
        then builds and sends the complete command list.
        """
        # Defer the response immediately. This tells Discord "I got the command, I'm working on it."
        # This is crucial for preventing the "Unknown Interaction" error.
        await interaction.response.defer(ephemeral=True)

        # Build the embed using the helper function
        embed = self.build_help_embed()

        # Send the complete embed as a follow-up message
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))

