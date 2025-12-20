import logging
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
from typing import Optional
from cogs.utils import db

logger = logging.getLogger(__name__)

# --- Timezone Setup ---
UTC_PLUS_8 = timezone(timedelta(hours=8))

class Announcer(commands.Cog):
    """DotNotify-style announcement system with recurring messages."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Local state
        self.next_cache_sync = datetime.now(UTC_PLUS_8).replace(tzinfo=None)
        self.cached_announcements = []
        self.send_announcements.start()
    
    def get_frequency_display(self, frequency: str) -> str:
        freq_map = {
            "once": "Once (No Repeat)",
            "1min": "Every 1 Minute", "3min": "Every 3 Minutes", "5min": "Every 5 Minutes",
            "10min": "Every 10 Minutes", "15min": "Every 15 Minutes", "30min": "Every 30 Minutes",
            "1hr": "Every 1 Hour", "3hrs": "Every 3 Hours", "6hrs": "Every 6 Hours",
            "12hrs": "Every 12 Hours", "1day": "Every 1 Day", "3days": "Every 3 Days",
            "1week": "Every 1 Week", "2weeks": "Every 2 Weeks", "1month": "Every 1 Month",
        }
        return freq_map.get(frequency, frequency)
    
    def parse_time_input(self, time_str: str) -> Optional[datetime]:
        formats = ["%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M", "%H:%M", "%Y/%m/%d %H:%M"]
        now = datetime.now(UTC_PLUS_8)
        for fmt in formats:
            try:
                dt = datetime.strptime(time_str, fmt)
                if fmt == "%H:%M":
                    dt = dt.replace(year=now.year, month=now.month, day=now.day)
                    if dt < now.replace(tzinfo=None): 
                        dt += timedelta(days=1)
                return dt
            except ValueError:
                continue
        return None

    def cog_unload(self):
        self.send_announcements.cancel()
    
    @tasks.loop(seconds=10)
    async def send_announcements(self):
        """Main loop to process and send scheduled announcements."""
        now = datetime.now(UTC_PLUS_8).replace(tzinfo=None)

        # Periodic cache sync
        if now >= self.next_cache_sync or not self.cached_announcements:
            try:
                self.cached_announcements = await db.get_due_announcements()
                self.next_cache_sync = now + timedelta(minutes=15)
                logger.debug("Synced announcements cache.")
            except Exception as e:
                logger.error(f"Sync failed: {e}")
        
        for ann in self.cached_announcements[:]:
            run_time = ann.get('next_run')
            if run_time and run_time <= now + timedelta(seconds=2):
                try:
                    channel = self.bot.get_channel(ann['channel_id'])
                    if channel:
                        await channel.send(ann['message'])
                        logger.info(f"Announcement {ann['id']} sent.")
                        
                        if ann['frequency'] == 'once':
                            await db.mark_announcement_inactive(ann['id'])
                            self.cached_announcements.remove(ann)
                        else:
                            # Update next run in DB and local cache
                            new_run = await db.update_announcement_next_run(ann['id'], ann['frequency'])
                            if new_run:
                                ann['next_run'] = new_run
                            else:
                                self.cached_announcements.remove(ann)
                    else:
                        await db.mark_announcement_inactive(ann['id'])
                        self.cached_announcements.remove(ann)
                except Exception as e:
                    logger.error(f"Error sending announcement {ann['id']}: {e}")

    @send_announcements.before_loop
    async def before_send(self):
        await self.bot.wait_until_ready()
    
    announce_group = app_commands.Group(name="announce", description="Announcement management")
    
    class FrequencySelect(discord.ui.Select):
        def __init__(self, parent_cog, msg, ch, guild_id, user_id, start_dt, edit_id=None):
            self.parent_cog = parent_cog
            self.message = msg
            self.channel = ch
            self.guild_id = guild_id
            self.user_id = user_id
            self.start_dt = start_dt
            self.edit_id = edit_id
            
            options = [
                discord.SelectOption(label="Once (No Repeat)", value="once", emoji="✅"),
                discord.SelectOption(label="Every 5 Minutes", value="5min", emoji="⏱️"),
                discord.SelectOption(label="Every 1 Hour", value="1hr", emoji="🕐"),
                discord.SelectOption(label="Every 1 Day", value="1day", emoji="📅"),
                discord.SelectOption(label="Every 1 Week", value="1week", emoji="📆")
            ]
            super().__init__(placeholder="Choose frequency...", options=options)
        
        async def callback(self, inter: discord.Interaction):
            freq = self.values[0]
            await inter.response.defer(ephemeral=True)
            try:
                if self.edit_id:
                    updates = {'message': self.message, 'channel_id': self.channel.id, 'frequency': freq, 'next_run': self.start_dt}
                    success = await db.update_announcement_details(self.edit_id, self.guild_id, updates)
                    if success:
                        await inter.followup.send(f"✅ Announcement `{self.edit_id}` updated.")
                    else:
                        await inter.followup.send("❌ DB update failed.")
                else:
                    # CORRECTED CALL: No tz_offset_hours passed here
                    ann_id = await db.create_announcement(
                        self.guild_id, self.channel.id, self.message, freq, self.user_id,
                        manual_next_run=self.start_dt
                    )
                    if ann_id:
                        await inter.followup.send(f"✅ Announcement created! ID: `{ann_id}`")
                    else:
                        await inter.followup.send("❌ Failed to create announcement.")
            except Exception as e:
                await inter.followup.send(f"❌ Error: {str(e)[:100]}")
    
    class FrequencyView(discord.ui.View):
        def __init__(self, parent_cog, msg, ch, guild_id, user_id, start_dt, edit_id=None):
            super().__init__(timeout=180)
            self.add_item(Announcer.FrequencySelect(parent_cog, msg, ch, guild_id, user_id, start_dt, edit_id))

    @announce_group.command(name="create", description="Create an announcement")
    async def announce_create(self, interaction: discord.Interaction, message: str, channel: discord.TextChannel, start_time: str):
        parsed = self.parse_time_input(start_time)
        if not parsed:
            await interaction.response.send_message("❌ Invalid time format. Use HH:MM.", ephemeral=True)
            return
        
        view = self.FrequencyView(self, message, channel, interaction.guild.id, interaction.user.id, parsed)
        await interaction.response.send_message("Please select a frequency:", view=view, ephemeral=True)

    @announce_group.command(name="list", description="List announcements")
    async def announce_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        announcements = await db.get_announcements_by_server(interaction.guild.id)
        if not announcements:
            await interaction.followup.send("No active announcements.")
            return
        
        embed = discord.Embed(title="Server Announcements", color=discord.Color.blue())
        for ann in announcements:
            freq = self.get_frequency_display(ann['frequency'])
            embed.add_field(
                name=f"ID: {ann['id']}",
                value=f"**Freq:** {freq}\n**Next:** {ann['next_run'].strftime('%H:%M')}\n**Msg:** {ann['message'][:50]}...",
                inline=False
            )
        await interaction.followup.send(embed=embed)

    @announce_group.command(name="stop", description="Stop an announcement")
    async def announce_stop(self, interaction: discord.Interaction, announcement_id: int):
        success = await db.stop_announcement(announcement_id, interaction.guild.id)
        if success:
            await interaction.response.send_message(f"✅ Announcement `{announcement_id}` stopped.")
        else:
            await interaction.response.send_message("❌ Failed to stop (not found).")

async def setup(bot: commands.Bot):
    await bot.add_cog(Announcer(bot))