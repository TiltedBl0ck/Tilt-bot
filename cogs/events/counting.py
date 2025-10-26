import discord
from discord.ext import commands
# Import the specific helper functions needed
from cogs.utils.db import get_guild_config, set_guild_config_value
import logging

logger = logging.getLogger(__name__)

class CountingGame(commands.Cog):
    """Handles the logic for the server counting game."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listens for messages to check for counting game updates."""
        # Ignore messages from bots, in DMs, or without content
        if message.author.bot or not message.guild or not message.content:
            return

        guild_id = message.guild.id

        try:
            config = await get_guild_config(guild_id)

            # Proceed only if counting is set up and message is in the correct channel
            # Use .get() for safer access to potentially missing keys
            counting_channel_id = config.get("counting_channel_id") if config else None
            if not counting_channel_id or counting_channel_id != message.channel.id:
                return

            current_count = config.get("current_count", 0) # Default to 0 if not set
            last_counter_id = config.get("last_counter_id")

            # Check if the message content is just a number (strip whitespace)
            content = message.content.strip()
            try:
                number = int(content)
            except ValueError:
                # If it's the very start (count is 0) and the message isn't "1", delete it
                if current_count == 0 and content != "1":
                     try:
                        await message.delete()
                        await message.channel.send(f"Wrong start, {message.author.mention}! The first number must be `1`.", delete_after=10)
                     except discord.Forbidden:
                         logger.warning(f"Missing permissions to delete message/send warning in counting channel {message.channel.id} for guild {guild_id}")
                     except discord.NotFound: pass # Message already deleted
                # Otherwise, ignore non-numeric messages silently or delete them
                # Deleting might be disruptive if people chat slightly off-topic. Consider ignoring instead.
                # logger.debug(f"Ignoring non-numeric message in counting channel: {content}")
                return

            # --- Game Logic ---
            expected_number = current_count + 1

            # Rule: The same user cannot count two numbers in a row (if last_counter_id is set)
            if last_counter_id is not None and message.author.id == last_counter_id:
                try:
                    await message.delete()
                    await message.channel.send(f"You can't count twice in a row, {message.author.mention}! The next number is still `{expected_number}`.", delete_after=10)
                except discord.Forbidden:
                    logger.warning(f"Missing permissions to delete message/send warning (double count) in counting channel {message.channel.id} for guild {guild_id}")
                except discord.NotFound: pass
                return

            # Check if the number is correct
            if number == expected_number:
                # Correct! Update the database using the helper function
                try:
                    await set_guild_config_value(guild_id, "current_count", number)
                    await set_guild_config_value(guild_id, "last_counter_id", message.author.id)
                    await message.add_reaction("✅")
                except Exception as e:
                     logger.error(f"Failed to update count or add reaction for guild {guild_id}: {e}", exc_info=True)
            else:
                # Wrong number! Reset the streak and notify.
                try:
                    original_count = current_count # Store before resetting
                    await set_guild_config_value(guild_id, "current_count", 0)
                    await set_guild_config_value(guild_id, "last_counter_id", None)
                    await message.add_reaction("❌")
                    await message.channel.send(f"**Streak broken!** {message.author.mention} ruined it at **{original_count}**. The next number is `1`. Expected `{expected_number}`, got `{number}`.")
                    logger.info(f"Counting streak broken in {message.guild.name} ({guild_id}) by {message.author} ({message.author.id}). Expected {expected_number}, got {number}.")
                except Exception as e:
                    logger.error(f"Failed to reset count or notify on wrong number for guild {guild_id}: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error processing message in counting game for guild {guild_id}: {e}", exc_info=True)


async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(CountingGame(bot))
