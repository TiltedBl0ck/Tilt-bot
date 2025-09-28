import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

class UserInfoCommand(commands.Cog):
    """A command to display information about a server member."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="userinfo", description="Displays detailed information about a user.")
    @app_commands.describe(member="The user you want to get info about (optional).")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        """Provides a detailed embed on a specified user or the command author."""
        user = member or interaction.user
        
        embed = discord.Embed(
            title=f"User Info: {user.display_name}",
            color=user.color or discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url=user.display_avatar.url)

        embed.add_field(name="Username", value=f"`{user}`", inline=True)
        embed.add_field(name="User ID", value=f"`{user.id}`", inline=True)
        embed.add_field(name="Is a Bot?", value="Yes" if user.bot else "No", inline=True)
        
        embed.add_field(name="Account Created", value=f"<t:{int(user.created_at.timestamp())}:F>", inline=False)
        if isinstance(user, discord.Member) and user.joined_at:
            embed.add_field(name="Joined Server", value=f"<t:{int(user.joined_at.timestamp())}:F>", inline=False)

        if isinstance(user, discord.Member):
            roles = [r.mention for r in reversed(user.roles) if r.name != "@everyone"]
            role_str = ", ".join(roles) if roles else "None"
            embed.add_field(name=f"Roles ({len(roles)})", value=role_str, inline=False)

        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(UserInfoCommand(bot))
