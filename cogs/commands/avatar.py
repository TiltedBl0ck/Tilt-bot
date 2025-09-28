import discord
from discord import app_commands
from discord.ext import commands

class AvatarCommand(commands.Cog):
    """A command to display a user's avatar."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="avatar", description="Displays a user's avatar.")
    @app_commands.describe(member="The user whose avatar you want to see (optional).")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member = None):
        """Shows the avatar of the specified member or the command user."""
        user = member or interaction.user
        
        embed = discord.Embed(
            title=f"{user.display_name}'s Avatar",
            color=user.color or discord.Color.blue()
        )
        embed.set_image(url=user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(AvatarCommand(bot))
