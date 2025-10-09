import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

class ServerInfoCommand(commands.Cog):
    """A command to display information about the current server."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="serverinfo", description="Displays detailed information about this server.")
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction):
        """Provides a detailed embed with server statistics."""
        guild = interaction.guild
        embed = discord.Embed(
            title=f"Server Info: {guild.name}",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="Owner", value=guild.owner.mention, inline=True)
        embed.add_field(name="Server ID", value=f"`{guild.id}`", inline=True)
        embed.add_field(name="Created On", value=f"<t:{int(guild.created_at.timestamp())}:D>", inline=True)

        humans = sum(1 for member in guild.members if not member.bot)
        bots = sum(1 for member in guild.members if member.bot)
        
        embed.add_field(name="Members", value=f"**Total:** {guild.member_count}\n**Humans:** {humans}\n**Bots:** {bots}", inline=True)
        embed.add_field(name="Channels", value=f"**Text:** {len(guild.text_channels)}\n**Voice:** {len(guild.voice_channels)}", inline=True)
        embed.add_field(name="Roles", value=f"{len(guild.roles)}", inline=True)
        
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(ServerInfoCommand(bot))
