import discord
from discord.ext import commands
import logging
from cogs.utils import db as db_utils  # Renamed for clarity

logger = logging.getLogger(__name__)

async def setup(bot):
    await bot.add_cog(Counting(bot))

class Counting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        # Check if this is a counting channel
        # We need to fetch the config to see if counting_channel_id matches current channel
        try:
            # FIX: Use get_config instead of get_guild_config
            config = await db_utils.get_config(message.guild.id)
            
            if not config or config.get('counting_channel_id') != message.channel.id:
                return

            # It is the counting channel! Let's handle the logic.
            await self.handle_counting(message, config)

        except Exception as e:
            logger.error(f"Error in counting listener: {e}")

    async def handle_counting(self, message, config):
        """
        Core logic for the counting game.
        """
        try:
            current_count = config.get('current_count', 0)
            last_user_id = config.get('last_user_id')

            # Try to parse the number from the message
            try:
                # Strip spaces and try to convert to int
                user_number = int(message.content.strip().split()[0])
            except (ValueError, IndexError):
                # If it's not a number (e.g. someone chatting), we can either:
                # 1. Ignore it (allow chat)
                # 2. Delete it (strict mode)
                # For now, let's ignore non-number messages unless strict mode is added later.
                return

            # Rule 1: Correct next number
            expected_number = current_count + 1
            if user_number != expected_number:
                await message.add_reaction("❌")
                await message.channel.send(f"{message.author.mention} RUINED IT at **{current_count}**! Next number is **1**.")
                # Reset count
                await db_utils.update_counting_stats(message.guild.id, 0, None)
                return

            # Rule 2: One person can't count twice in a row
            if last_user_id == message.author.id:
                await message.add_reaction("❌")
                await message.channel.send(f"{message.author.mention} You can't count twice in a row! Resetting to **1**.")
                # Reset count
                await db_utils.update_counting_stats(message.guild.id, 0, None)
                return

            # Success!
            await message.add_reaction("✅")
            # Update DB with new count and new last_user
            await db_utils.update_counting_stats(message.guild.id, expected_number, message.author.id)

            # Optional: Milestone celebration
            if expected_number % 100 == 0:
                await message.channel.send(f"🎉 **MILESTONE!** We reached **{expected_number}**! 🎉")

        except Exception as e:
            logger.error(f"Error handling counting logic: {e}")