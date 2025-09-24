import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

class HelpDropdown(discord.ui.Select):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Get cogs and create dropdown options
        options = [
            discord.SelectOption(label="Home", description="Return to the main help menu.", emoji="🏠")
        ]
        for cog_name, cog in bot.cogs.items():
            # Hide cogs that have no visible commands or are the error handler
            if not hasattr(cog, '__cog_app_commands__') or not cog.__cog_app_commands__ or cog_name == "ErrorHandler":
                continue
            options.append(discord.SelectOption(
                label=cog_name,
                description=cog.description or "No description provided.",
                emoji="⚙️" # You can customize emojis per cog later if you wish
            ))
        
        super().__init__(placeholder="Choose a category to see its commands...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        # When a user selects an option, we edit the message directly.
        # This is the most efficient way to respond to a component interaction.
        selected_cog_name = self.values[0]
        
        if selected_cog_name == "Home":
            # Resend the initial home embed
            embed = create_home_embed(self.bot)
            await interaction.response.edit_message(embed=embed)
            return
            
        # Find the cog object
        cog = self.bot.get_cog(selected_cog_name)
        if not cog:
            # Edit the message to show an error if the cog isn't found
            await interaction.response.edit_message(content="Could not find that category.", embed=None, view=self.view)
            return

        # Create an embed for the selected category
        embed = discord.Embed(
            title=f"📚 {cog.qualified_name} Commands",
            description=cog.description or "Here are the available commands:",
            color=discord.Color.blue()
        )

        # Add commands to the embed
        for command in cog.get_app_commands():
            embed.add_field(name=f"`/{command.name}`", value=command.description or "No description", inline=False)
        
        embed.set_footer(text="Use the dropdown to explore other categories.")
        # Edit the original message with the new embed
        await interaction.response.edit_message(embed=embed)


class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=180) # View times out after 3 minutes
        self.add_item(HelpDropdown(bot))


def create_home_embed(bot: commands.Bot) -> discord.Embed:
    """Creates the initial 'home' embed for the help command."""
    embed = discord.Embed(
        title="Tilt-Bot Help Menu",
        description=f"Welcome! I'm Tilt-Bot, a multi-purpose bot designed to make your server better.\n"
                    f"Use the dropdown menu below to see the commands for a specific category.",
        color=discord.Color.purple(),
        timestamp=datetime.utcnow()
    )
    embed.add_field(
        name="How to use this menu",
        value="Click the dropdown and select a category like 'Moderation' or 'Utility' to see all related commands.",
        inline=False
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.set_footer(text=f"Tilt-Bot v{bot.version} | Coded by TiltedBl0ck")
    return embed


class HelpCog(commands.Cog, name="Help"):
    """An interactive and categorized help command."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Displays an interactive menu of all available commands.")
    async def help(self, interaction: discord.Interaction):
        """The main help command."""
        # Defer the response to prevent "Unknown Interaction" errors
        await interaction.response.defer(ephemeral=True)
        
        embed = create_home_embed(self.bot)
        view = HelpView(self.bot)
        
        # Use followup.send after deferring
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))

