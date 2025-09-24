import discord
from discord import app_commands
from discord.ext import commands

class ErrorHandler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.tree.error(self.on_app_command_error)

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        print(f"Error in command {interaction.command.name if interaction.command else 'Unknown'}: {error}")
        if isinstance(error, app_commands.errors.MissingPermissions):
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ You do not have the required permissions to run this command.", ephemeral=True
                )
        elif not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ An error occurred while processing your command.", ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(ErrorHandler(bot))

