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
        if not 1 <= count <= 100:
            return await interaction.response.send_message("Count must be between 1 and 100.", ephemeral=True)
        try:
            deleted = await interaction.channel.purge(limit=count)
            await interaction.response.send_message(f"✅ Deleted {len(deleted)} messages.", ephemeral=True, delete_after=5)
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I do not have the `Manage Messages` permission to do this.", ephemeral=True
            )
        except discord.HTTPException as e:
            print(f"Error during message purge: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while trying to clear messages. They might be too old.", ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
