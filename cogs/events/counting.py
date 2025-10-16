import discord
from discord.ext import commands
from cogs.utils.db import get_db_connection
import logging

logger = logging.getLogger(__name__)

class CountingGame(commands.Cog):
    """Handles the logic for the server counting game."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listens for messages to check for counting game updates."""
        # Ignore messages from bots or in DMs
        if message.author.bot or not message.guild:
            return

        async with get_db_connection() as conn:
            cursor = await conn.execute("SELECT counting_channel_id, current_count, last_counter_id FROM guild_config WHERE guild_id = ?", (message.guild.id,))
            config = await cursor.fetchone()

            # Proceed only if counting is set up for this server and message is in the correct channel
            if not config or not config["counting_channel_id"] or config["counting_channel_id"] != message.channel.id:
                return

            # Check if the message content is a valid integer
            try:
                number = int(message.content)
            except ValueError:
                # If the current count is 0, the first number must be 1. Delete any other message.
                if config["current_count"] == 0 and message.content.strip() != "1":
                    await message.delete()
                    await message.channel.send(f"Wrong start, {message.author.mention}! The first number must be `1`.", delete_after=10)
                return # If it's not a number, ignore it

            # --- Game Logic ---
            expected_number = (config["current_count"] or 0) + 1

            # Rule: The same user cannot count two numbers in a row.
            if message.author.id == config["last_counter_id"]:
                await message.delete()
                await message.channel.send(f"You can't count twice in a row, {message.author.mention}! The next number is still `{expected_number}`.", delete_after=10)
                return

            # Check if the number is correct
            if number == expected_number:
                # Correct! Update the database with the new count and the user who sent it.
                await conn.execute(
                    "UPDATE guild_config SET current_count = ?, last_counter_id = ? WHERE guild_id = ?",
                    (number, message.author.id, message.guild.id)
                )
                await conn.commit()
                await message.add_reaction("✅") # Give feedback that the number was correct
            else:
                # Wrong number! Reset the streak and notify the channel.
                await conn.execute(
                    "UPDATE guild_config SET current_count = 0, last_counter_id = NULL WHERE guild_id = ?",
                    (message.guild.id,)
                )
                await conn.commit()
                await message.add_reaction("❌") # Give feedback that the number was wrong
                await message.channel.send(f"**Streak broken!** {message.author.mention} ruined it at **{config['current_count']}**. The next number is `1`.")
                logger.info(f"Counting streak broken in {message.guild.name} by {message.author}.")


async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(CountingGame(bot))
