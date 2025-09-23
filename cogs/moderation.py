import discord
from discord import app_commands
from discord.ext import commands

class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="clear", description="Clear recent messages")
    @app_commands.describe(count="Number of messages to delete (1–100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, count: int):
        try:
            if not 1 <= count <= 100:
                return await interaction.response.send_message("Count must be between 1 and 100.", ephemeral=True)
            deleted = await interaction.channel.purge(limit=count)
            await interaction.response.send_message(f"✅ Deleted {len(deleted)} messages.", ephemeral=True)
        except Exception:
            await interaction.response.send_message("❌ Error clearing messages.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))

