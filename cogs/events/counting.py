import discord
from discord.ext import commands
import cogs.utils.db as db_utils # Use alias for db utilities
import logging
from typing import Optional # For type hinting

logger = logging.getLogger(__name__)

class CountingGame(commands.Cog):
    """Handles the logic for the server counting game."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener("on_message") # Explicitly listen only for on_message
    async def handle_counting(self, message: discord.Message):
        """Listens for messages to check for counting game updates."""
        # Ignore messages from bots, in DMs, or without content/guild
        if message.author.bot or not message.guild or not message.content:
            return

        guild_id = message.guild.id

        # --- Get Config (Uses Cache) ---
        config = await db_utils.get_guild_config(guild_id)

        # Proceed only if counting is set up and message is in the correct channel
        # Use .get() for safe access
        counting_channel_id = config.get("counting_channel_id") if config else None
        if not counting_channel_id or counting_channel_id != message.channel.id:
            return

        current_count = config.get("current_count", 0) # Default to 0 if key missing
        last_counter_id = config.get("last_counter_id") # Can be None

        # --- Validate Input ---
        content = message.content.strip()
        try:
            number = int(content)
        except ValueError:
            # Allow starting message "1" if count is 0
            if current_count == 0 and content == "1":
                number = 1
            else:
                # Delete messages that are definitely not the next number
                # Avoid deleting if it *might* be conversation - check only if it doesn't contain the expected number?
                expected_number = current_count + 1
                if str(expected_number) not in content: # Basic check to avoid deleting related chat
                    try:
                        await message.delete()
                        # Optional: Send temporary warning
                        # await message.channel.send(f"{message.author.mention}, please only send numbers in the counting channel.", delete_after=5)
                    except discord.Forbidden:
                         logger.warning(f"Missing permissions to delete non-number message in counting channel {message.channel.id} (Guild {guild_id})")
                    except discord.NotFound:
                         pass # Message already deleted
                return # Ignore non-numeric or irrelevant messages

        # --- Game Logic ---
        expected_number = current_count + 1

        # Rule: Same user cannot count twice in a row
        if last_counter_id is not None and message.author.id == last_counter_id:
            try:
                await message.delete()
                await message.channel.send(f"You can't count twice in a row, {message.author.mention}! The next number is still `{expected_number}`.", delete_after=10)
            except discord.Forbidden:
                logger.warning(f"Missing permissions to delete/warn double count in counting channel {message.channel.id} (Guild {guild_id})")
            except discord.NotFound:
                pass # Message already deleted
            except discord.HTTPException as e:
                logger.warning(f"Failed to send double count warning in {message.channel.id}: {e.status} {e.text}")
            return

        # --- Check Number ---
        if number == expected_number:
            # Correct! Update DB and Cache via helper
            success = await db_utils.update_counting_stats(guild_id, number, message.author.id)
            if success:
                try:
                    await message.add_reaction("✅")
                except discord.Forbidden:
                     logger.warning(f"Missing permissions to add reaction in counting channel {message.channel.id} (Guild {guild_id})")
                except discord.HTTPException as e:
                     logger.warning(f"Failed to add ✅ reaction: {e.status} {e.text}")
            else:
                 logger.error(f"Failed to update counting stats in DB for guild {guild_id}")
                 # Maybe add a different reaction or log prominently
        else:
            # Wrong number! Reset DB/Cache and notify.
            original_count = current_count # Store before resetting
            success = await db_utils.update_counting_stats(guild_id, 0, None) # Reset count and last user

            if success:
                try:
                    await message.add_reaction("❌")
                    await message.channel.send(
                        f"**Streak broken!** {message.author.mention} ruined it at **{original_count}**. "
                        f"Expected `{expected_number}`, got `{number}`. The next number is `1`."
                    )
                    logger.info(f"Counting streak broken in {message.guild.name} ({guild_id}) by {message.author} ({message.author.id}). Expected {expected_number}, got {number}.")
                except discord.Forbidden:
                     logger.warning(f"Missing permissions to add reaction or send message in counting channel {message.channel.id} (Guild {guild_id})")
                except discord.HTTPException as e:
                     logger.warning(f"Failed to add ❌ reaction or send break message: {e.status} {e.text}")
            else:
                 logger.error(f"Failed to reset counting stats in DB for guild {guild_id} after incorrect number.")


async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(CountingGame(bot))

