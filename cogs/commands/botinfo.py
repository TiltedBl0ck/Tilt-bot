import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

class BotInfoCommand(commands.Cog):
    """A command to display information about the bot."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="botinfo", description="Displays information about Tilt-bot.")
    async def botinfo(self, interaction: discord.Interaction):
        """Provides a detailed embed with bot statistics."""
        embed = discord.Embed(
            title="Tilt-bot Statistics",
            color=discord.Color.purple(),
            timestamp=datetime.utcnow()
        )
        if self.bot.user.display_avatar:
            embed.set_author(name=self.bot.user.name, icon_url=self.bot.user.display_avatar.url)

        embed.add_field(name="Version", value=f"`{self.bot.version}`", inline=True)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        embed.add_field(name="Servers", value=f"{len(self.bot.guilds)}", inline=True)
        
        total_users = sum(guild.member_count for guild in self.bot.guilds)
        embed.add_field(name="Total Users", value=f"{total_users}", inline=True)

        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(BotInfoCommand(bot))
