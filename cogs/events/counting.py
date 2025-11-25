import discord
from discord.ext import commands, tasks
import cogs.utils.db as db_utils 
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class CountingGame(commands.Cog):
    """Handles the logic for the server counting game with batched DB writes."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Local state cache for write-behind
        # Structure: {guild_id: {'count': int, 'last_user': int, 'dirty': bool}}
        self.guild_states: Dict[int, Dict] = {}
        self.sync_counting_stats.start()

    def cog_unload(self):
        self.sync_counting_stats.cancel()

    @tasks.loop(minutes=5)
    async def sync_counting_stats(self):
        """Batch update modified counting stats to DB every 5 minutes."""
        # Find dirty states
        dirty_guilds = {gid: state for gid, state in self.guild_states.items() if state['dirty']}
        
        if not dirty_guilds:
            return

        logger.debug(f"Syncing {len(dirty_guilds)} counting game states to DB...")
        
        for guild_id, state in dirty_guilds.items():
            success = await db_utils.update_counting_stats(
                guild_id, 
                state['count'], 
                state['last_user']
            )
            if success:
                state['dirty'] = False
            else:
                logger.error(f"Failed to sync counting stats for guild {guild_id}")

    @sync_counting_stats.before_loop
    async def before_sync_loop(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener("on_message")
    async def handle_counting(self, message: discord.Message):
        """Listens for messages to check for counting game updates."""
        if message.author.bot or not message.guild or not message.content:
            return

        guild_id = message.guild.id

        # --- Initialize Local State from DB/Cache if missing ---
        if guild_id not in self.guild_states:
             config = await db_utils.get_guild_config(guild_id)
             if not config or not config.get("counting_channel_id"):
                 return # Not set up
             
             self.guild_states[guild_id] = {
                 'count': config.get("current_count", 0),
                 'last_user': config.get("last_counter_id"),
                 'channel_id': config.get("counting_channel_id"),
                 'dirty': False
             }

        state = self.guild_states[guild_id]
        
        # Verify channel matches
        if message.channel.id != state['channel_id']:
            return

        current_count = state['count']
        last_counter_id = state['last_user']

        # --- Validate Input ---
        content = message.content.strip()
        try:
            number = int(content)
        except ValueError:
            if current_count == 0 and content == "1":
                number = 1
            else:
                expected_number = current_count + 1
                if str(expected_number) not in content:
                    try:
                        await message.delete()
                    except (discord.Forbidden, discord.NotFound):
                         pass
                return

        # --- Game Logic ---
        expected_number = current_count + 1

        if last_counter_id is not None and message.author.id == last_counter_id:
            try:
                await message.delete()
                await message.channel.send(f"You can't count twice in a row, {message.author.mention}! The next number is `{expected_number}`.", delete_after=10)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass
            return

        if number == expected_number:
            # Correct! Update Local State Only
            state['count'] = number
            state['last_user'] = message.author.id
            state['dirty'] = True # Mark for sync
            
            try:
                await message.add_reaction("✅")
            except (discord.Forbidden, discord.HTTPException):
                 pass
        else:
            # Wrong number! Reset Local State
            original_count = current_count
            state['count'] = 0
            state['last_user'] = None
            state['dirty'] = True
            
            # For "Streak broken", we might want to force a sync immediately to prevent data loss 
            # if bot crashes right after a fail, but for now we treat it like any other update.
            # To be safe, we can force sync on fail:
            await db_utils.update_counting_stats(guild_id, 0, None)
            state['dirty'] = False

            try:
                await message.add_reaction("❌")
                await message.channel.send(
                    f"**Streak broken!** {message.author.mention} ruined it at **{original_count}**. "
                    f"Expected `{expected_number}`, got `{number}`. The next number is `1`."
                )
            except (discord.Forbidden, discord.HTTPException):
                 pass

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(CountingGame(bot))