import discord
from discord.ext import commands
# Updated imports
from cogs.utils.db import pool, get_guild_config, set_guild_config_value
import logging

logger = logging.getLogger(__name__)

class CountingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bot messages and DMs
        if message.author.bot or not message.guild:
            return

        # Check if the message is in a configured counting channel for this guild
        guild_id = message.guild.id
        config = await get_guild_config(guild_id) # Use the helper

        # Check if config exists and counting channel is set
        if not config or not config['counting_channel_id'] or message.channel.id != config['counting_channel_id']:
            return

        # Get expected number and last user from config
        expected_number = config['counting_next_number']
        last_user_id = config['counting_last_user_id']

        # --- Input Validation ---
        try:
            # Check if message content is exactly the expected number
            current_number = int(message.content.strip())
        except ValueError:
            # Not a valid number, delete if possible (optional)
            # await message.delete()
            # await message.channel.send(f"{message.author.mention}, that wasn't a valid number!", delete_after=5)
            return # Ignore non-numeric messages silently for now

        # --- Counting Logic ---
        if current_number != expected_number:
            # Incorrect number
            try:
                await message.add_reaction("❌")
                await message.reply(f"Wrong number! The next number was `{expected_number}`. Sequence reset.")
            except discord.Forbidden:
                 logger.warning(f"Missing permissions to react/reply in counting channel {message.channel.id} (Guild: {guild_id})")
            except discord.HTTPException as e:
                 logger.error(f"Failed to react/reply in counting channel {message.channel.id}: {e}")
            
            # Reset the count in the database
            await set_guild_config_value(guild_id, 'counting_next_number', 1)
            await set_guild_config_value(guild_id, 'counting_last_user_id', None) # Reset last user

        elif message.author.id == last_user_id:
            # Same user counted twice
            try:
                 await message.add_reaction("❌")
                 await message.reply("You can't count twice in a row! Sequence reset.")
            except discord.Forbidden:
                 logger.warning(f"Missing permissions to react/reply in counting channel {message.channel.id} (Guild: {guild_id})")
            except discord.HTTPException as e:
                 logger.error(f"Failed to react/reply in counting channel {message.channel.id}: {e}")
                 
            # Reset the count in the database
            await set_guild_config_value(guild_id, 'counting_next_number', 1)
            await set_guild_config_value(guild_id, 'counting_last_user_id', None)

        else:
            # Correct number and different user!
            try:
                await message.add_reaction("✅")
            except discord.Forbidden:
                logger.warning(f"Missing permissions to react in counting channel {message.channel.id} (Guild: {guild_id})")
            except discord.HTTPException as e:
                 logger.error(f"Failed to react in counting channel {message.channel.id}: {e}")


            # Update the next number and last user in the database
            next_num = expected_number + 1
            await set_guild_config_value(guild_id, 'counting_next_number', next_num)
            await set_guild_config_value(guild_id, 'counting_last_user_id', message.author.id)

    # Optional: Listener to handle message deletions in counting channel
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
         if message.author.bot or not message.guild:
             return

         guild_id = message.guild.id
         config = await get_guild_config(guild_id)

         if not config or not config['counting_channel_id'] or message.channel.id != config['counting_channel_id']:
             return

         # Simple approach: If a message is deleted, just notify and maybe reset?
         # A more complex system would check if it was the *last* correct number.
         # For now, let's just log it or send a warning.
         logger.info(f"A message was deleted in counting channel {message.channel.id} (Guild: {guild_id}): '{message.content}' by {message.author}")
         # Potentially send a message to the channel:
         # try:
         #    await message.channel.send(f"⚠️ A message by {message.author.mention} was deleted. Please ensure the count is still correct.", delete_after=10)
         # except discord.Forbidden:
         #     pass # Ignore if no perms


async def setup(bot: commands.Bot):
    await bot.add_cog(CountingCog(bot))
