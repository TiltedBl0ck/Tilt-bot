import discord
from discord import app_commands
from discord.ext import commands

class PingCommand(commands.Cog):
    """A command to check the bot's latency."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Checks the bot's response time.")
    async def ping(self, interaction: discord.Interaction):
        """Responds with the bot's current websocket latency."""
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"Pong! 🏓 Latency is {latency}ms.")

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(PingCommand(bot))

