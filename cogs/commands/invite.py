import discord
from discord import app_commands
from discord.ext import commands

class InviteCommand(commands.Cog):
    """A command to get the bot's invite link."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="invite", description="Get the bot's invite link.")
    async def invite(self, interaction: discord.Interaction):
        """Sends an invite link with a button."""
        invite_link = discord.utils.oauth_url(
            self.bot.user.id,
            permissions=discord.Permissions(permissions=8), # Administrator
            scopes=("bot", "applications.commands")
        )
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Click to Invite!", style=discord.ButtonStyle.green, url=invite_link))
        
        await interaction.response.send_message("Use the button below to add me to your server:", view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(InviteCommand(bot))
