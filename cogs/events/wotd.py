import discord
from discord.ext import commands, tasks
import logging
from cogs.utils import db as db_utils
from cogs.utils import wotd_fetcher
from datetime import datetime, timedelta, timezone
import re

logger = logging.getLogger(__name__)

class WordOfTheDay(commands.Cog):
    """
    Fetches and broadcasts the Word of the Day from Merriam-Webster.
    Checks frequently (every 5 mins) to deliver at user-configured times.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cached_wotd_data = None
        self.last_fetch_time = 0
        self.wotd_loop.start()

    def cog_unload(self):
        self.wotd_loop.cancel()

    @tasks.loop(minutes=5)
    async def wotd_loop(self):
        """Checks if it's time to send WOTD for any guild."""
        try:
            # 1. Fetch Data (with caching for 1 hour)
            now_ts = datetime.now().timestamp()
            if not self.cached_wotd_data or (now_ts - self.last_fetch_time > 3600):
                 data = await wotd_fetcher.fetch_wotd()
                 if data:
                     self.cached_wotd_data = data
                     self.last_fetch_time = now_ts
                     logger.debug(f"Refreshed WOTD cache: {data['word']}")
            
            if not self.cached_wotd_data:
                return

            current_word = self.cached_wotd_data['word']
            
            # 2. Iterate Configs
            configs = await db_utils.get_wotd_configs()
            
            for config in configs:
                # SKIP if we already sent THIS word to THIS guild
                # This ensures we only send once per day/word update
                if config['wotd_last_word'] == current_word:
                    continue
                
                # 3. Calculate Guild Time
                tz_offset = 0
                tz_str = config['wotd_timezone']
                
                # Parse timezone string (simple offset support)
                # Formats: "UTC+8", "UTC-5", "+8", "-5", "8"
                try:
                    match = re.search(r'([+-]?\d+)', tz_str)
                    if match:
                        tz_offset = int(match.group(1))
                except Exception:
                    tz_offset = 0 # Default to UTC if parse fails
                
                # Limit offset to realistic bounds (-12 to +14) to prevent errors
                tz_offset = max(-12, min(14, tz_offset))
                
                guild_tz = timezone(timedelta(hours=tz_offset))
                guild_now = datetime.now(guild_tz)
                
                target_hour = config['wotd_hour']
                
                # 4. Check Delivery Time
                # We send if it is currently the target hour OR later in the day.
                # Since we checked `wotd_last_word` above, this "catch-up" logic 
                # handles cases where the bot was offline during the exact hour.
                if guild_now.hour >= target_hour:
                     # It's time!
                     await self.send_wotd(config, self.cached_wotd_data)
                     
                     # Update DB so we don't send again until the word changes
                     await db_utils.update_guild_wotd_word(config['guild_id'], current_word)
                     logger.info(f"Sent WOTD '{current_word}' to guild {config['guild_id']} (Time: {guild_now.strftime('%H:%M')})")

        except Exception as e:
            logger.error(f"Error in WOTD loop: {e}")

    async def send_wotd(self, config, data):
        """Helper to send the embed."""
        guild = self.bot.get_guild(config['guild_id'])
        if not guild: return
        
        channel = guild.get_channel(config['wotd_channel_id'])
        if not channel:
            logger.warning(f"WOTD channel {config['wotd_channel_id']} not found in guild {guild.id}")
            return

        # Construct Embed
        embed = discord.Embed(
            title="📚 Word of the Day",
            url=data['url'],
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Word", value=f"**{data['word']}**", inline=True)
        embed.add_field(name="Type", value=f"*{data['type']}*", inline=True)
        embed.add_field(name="Definition", value=data['definition'], inline=False)
        embed.add_field(name="Example", value=f"_{data['example']}_", inline=False)
        embed.set_footer(text="Source: Merriam-Webster")

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logger.warning(f"Missing permissions to send WOTD in guild {guild.id}")
        except Exception as e:
            logger.error(f"Error sending WOTD to guild {guild.id}: {e}")

    @wotd_loop.before_loop
    async def before_wotd(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(WordOfTheDay(bot))