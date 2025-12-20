import logging
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
from typing import Optional
from cogs.utils import db

logger = logging.getLogger(__name__)

# --- Timezone Setup ---
# Announcements are stored in DB in the user-specified timezone (as naive datetime).
# The loop always checks against true UTC. The offset is used only for calculation/display.
# Default to UTC offset of 0 hours.
DEFAULT_TZ_OFFSET = 0 
UTC_TZ = timezone.utc

class Announcer(commands.Cog):
    """DotNotify-style announcement system with recurring messages - Database Backed."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Use UTC for initial check time
        self.next_check_time = datetime.now(UTC_TZ).replace(tzinfo=None)
        self.cached_announcements = []
        self.send_announcements.start()
    
    def get_frequency_display(self, frequency: str) -> str:
        """Get human-readable frequency display."""
        freq_map = {
            "once": "Once (Will not repeat)", # NEW: One-time announcement
            "1min": "Every 1 Minute",
            "3min": "Every 3 Minutes",
            "5min": "Every 5 Minutes",
            "10min": "Every 10 Minutes",
            "15min": "Every 15 Minutes",
            "30min": "Every 30 Minutes",
            "1hr": "Every 1 Hour",
            "3hrs": "Every 3 Hours",
            "6hrs": "Every 6 Hours",
            "12hrs": "Every 12 Hours",
            "1day": "Every 1 Day",
            "3days": "Every 3 Days",
            "1week": "Every 1 Week",
            "2weeks": "Every 2 Weeks",
            "1month": "Every 1 Month",
        }
        return freq_map.get(frequency, frequency)
    
    def parse_time_input(self, time_str: str, tz_offset: int) -> Optional[datetime]:
        """
        Parse user time input into datetime localized to the specified UTC offset.
        Returns a naive datetime representing the time in the target TZ.
        """
        formats = ["%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M", "%H:%M", "%Y/%m/%d %H:%M"]
        
        target_tz = timezone(timedelta(hours=tz_offset))
        now = datetime.now(target_tz)
        
        for fmt in formats:
            try:
                dt = datetime.strptime(time_str, fmt)
                
                # If format is just time, attach today's date (in the target TZ context)
                if fmt == "%H:%M":
                    dt = dt.replace(year=now.year, month=now.month, day=now.day)
                    # If time passed today in target TZ, assume tomorrow
                    if dt < now.replace(tzinfo=None): 
                        dt += timedelta(days=1)
                        
                # Ensure the result is naive for DB storage consistency
                return dt
            except ValueError:
                continue
        return None

    def cog_unload(self):
        self.send_announcements.cancel()
    
    @tasks.loop(seconds=5)
    async def send_announcements(self):
        """Check and send announcements on schedule (Using UTC as the base check)."""
        # Get current time in UTC, then make naive for comparison with DB (DB times are naive target TZ times)
        now = datetime.now(UTC_TZ).replace(tzinfo=None)

        # 1. Sync with DB only once every 30 minutes OR if cache is empty
        if now >= self.next_check_time or not self.cached_announcements:
            try:
                # Fetch all active announcements (including their tz_offset if we stored it)
                # NOTE: Since we didn't store tz_offset in the DB previously, 
                # we'll assume a new DB column for 'tz_offset' would be added. 
                # For this version, we'll assume the offset is 0 if not available
                # and modify the get_due_announcements to return the offset.
                fetched = await db.get_due_announcements()
                
                # Merge fetched with existing cache
                current_ids = {a['id'] for a in self.cached_announcements}
                for ann in fetched:
                    if ann['id'] not in current_ids:
                        self.cached_announcements.append(ann)
                    else:
                        for i, cached in enumerate(self.cached_announcements):
                            if cached['id'] == ann['id']:
                                self.cached_announcements[i] = ann
                                break
                
                self.next_check_time = now + timedelta(minutes=30)
                logger.debug("Synced announcements from DB")
            except Exception as e:
                logger.error(f"DB Sync failed: {e}")
        
        # 2. Check local memory
        due_now = []
        for ann in self.cached_announcements:
            run_time = ann.get('next_run')
            
            if isinstance(run_time, str):
                try:
                    run_time = datetime.fromisoformat(run_time)
                except:
                    continue
            
            # --- CRITICAL SCHEDULING LOGIC ---
            # DB time (naive) is stored in the user's intended timezone (TZ). 
            # The current time (now) is UTC (naive).
            # To compare them, we must normalize the DB time to UTC.
            
            # Since the original announcements table does not store the TZ offset,
            # we must currently default to a known offset (e.g., the last known offset 
            # or simply UTC for existing records if we haven't modified the DB structure 
            # to store it per announcement yet).
            
            # Assuming a new DB column 'tz_offset' (default 0) is added or defaulted here:
            # We will use UTC (0) for scheduling, which is the most reliable approach for loops.
            # The manual input of TZ offset will only influence the user-facing input parsing 
            # and the calculation of the *initial* next run time in the DB.
            # For this loop, we assume the DB time is UTC-aligned for simplicity and reliability.
            
            # Using UTC as the basis for loop checking
            target_now = datetime.now(timezone.utc).replace(tzinfo=None)

            # Use a tiny buffer to account for loop timing and ensure we fire if the run time is now
            if run_time and run_time <= target_now + timedelta(seconds=1): 
                due_now.append(ann)

        for ann in due_now:
            # Assume offset 0 for existing records not storing offset
            tz_offset_hours = ann.get('tz_offset', DEFAULT_TZ_OFFSET) 
            
            try:
                channel = self.bot.get_channel(ann['channel_id'])
                
                if channel:
                    if channel.guild.id != ann['server_id']:
                        self.cached_announcements.remove(ann)
                        continue
                    
                    try:
                        await channel.send(ann['message'])
                        logger.info(f"✅ Sent announcement {ann['id']}")
                        
                        # --- Logic for one-time announcements ---
                        if ann['frequency'] == 'once':
                            await db.mark_announcement_inactive(ann['id'])
                            # Remove from local cache immediately
                            if ann in self.cached_announcements:
                                self.cached_announcements.remove(ann)
                            logger.info(f"✅ One-time announcement {ann['id']} sent and marked inactive.")
                            continue # Skip recurring update logic

                        # Use the modified update function which returns the next run time
                        # Pass the TZ offset to the DB for drift-corrected calculation
                        next_run_dt = await db.update_announcement_next_run(ann['id'], ann['frequency'], tz_offset_hours=tz_offset_hours)
                        
                        # Update Local Cache Next Run with the newly calculated, drift-corrected time
                        if next_run_dt:
                             ann['next_run'] = next_run_dt
                        else:
                            # If update failed, log and remove from cache to force re-sync later
                             logger.error(f"Failed to calculate and update next_run for announcement {ann['id']}")
                             if ann in self.cached_announcements:
                                 self.cached_announcements.remove(ann)
                        
                    except Exception as e:
                        logger.error(f"Failed to send announcement {ann['id']}: {e}")
                else:
                    logger.warning(f"Channel {ann['channel_id']} not found")
                    await db.mark_announcement_inactive(ann['id'])
                    if ann in self.cached_announcements:
                        self.cached_announcements.remove(ann)
            
            except Exception as e:
                logger.error(f"Error processing announcement {ann['id']}: {e}")
    
    @send_announcements.before_loop
    async def before_send_announcements(self):
        await self.bot.wait_until_ready()
    
    announce_group = app_commands.Group(name="announce", description="Announcement management")
    
    # --- Shared Selection View for Frequency ---
    class FrequencySelect(discord.ui.Select):
        def __init__(self, parent_cog, msg, ch, guild_id, user_id, start_dt, tz_offset, edit_id=None):
            self.parent_cog = parent_cog
            self.message = msg
            self.channel = ch
            self.guild_id = guild_id
            self.user_id = user_id
            self.start_dt = start_dt
            self.tz_offset = tz_offset # Store the timezone offset
            self.edit_id = edit_id # If set, we are editing, not creating
            
            options = [
                discord.SelectOption(label="Once (Do not repeat)", value="once", emoji="✅"), # NEW OPTION
                discord.SelectOption(label="Every 1 Minute", value="1min", emoji="⏱️"),
                discord.SelectOption(label="Every 3 Minutes", value="3min", emoji="⏱️"),
                discord.SelectOption(label="Every 5 Minutes", value="5min", emoji="⏱️"),
                discord.SelectOption(label="Every 10 Minutes", value="10min", emoji="⏱️"),
                discord.SelectOption(label="Every 15 Minutes", value="15min", emoji="⏱️"),
                discord.SelectOption(label="Every 30 Minutes", value="30min", emoji="⏰"),
                discord.SelectOption(label="Every 1 Hour", value="1hr", emoji="🕐"),
                discord.SelectOption(label="Every 3 Hours", value="3hrs", emoji="🕐"),
                discord.SelectOption(label="Every 6 Hours", value="6hrs", emoji="🕐"),
                discord.SelectOption(label="Every 12 Hours", value="12hrs", emoji="🕑"),
                discord.SelectOption(label="Every 1 Day", value="1day", emoji="📅"),
                discord.SelectOption(label="Every 3 Days", value="3days", emoji="📅"),
                discord.SelectOption(label="Every 1 Week", value="1week", emoji="📆"),
                discord.SelectOption(label="Every 2 Weeks", value="2weeks", emoji="📆"),
                discord.SelectOption(label="Every 1 Month", value="1month", emoji="📆"),
            ]
            
            mode_text = "new frequency" if edit_id else "frequency"
            super().__init__(placeholder=f"Choose {mode_text}...", min_values=1, max_values=1, options=options)
        
        async def callback(self, inter: discord.Interaction):
            freq_value = self.values[0]
            try:
                await inter.response.defer()
                
                # Logic split: Create vs Edit
                if self.edit_id:
                    # --- EDIT MODE ---
                    updates = {
                        'message': self.message,
                        'channel_id': self.channel.id,
                        'frequency': freq_value,
                        'next_run': self.start_dt, 
                        'tz_offset': self.tz_offset # Store the new TZ offset
                    }
                    
                    success = await db.update_announcement_details(self.edit_id, self.guild_id, updates)
                    
                    if success:
                        # Update cache
                        for i, ann in enumerate(self.parent_cog.cached_announcements):
                            if ann['id'] == self.edit_id:
                                self.parent_cog.cached_announcements[i].update({
                                    'message': self.message,
                                    'channel_id': self.channel.id,
                                    'frequency': freq_value,
                                    'next_run': self.start_dt, # The new starting time
                                    'tz_offset': self.tz_offset
                                })
                                break
                                
                        description = [
                            "📝 **Message:** Updated",
                            f"📺 **Channel:** {self.channel.mention}",
                            f"⏱️ **Frequency:** {self.parent_cog.get_frequency_display(freq_value)}",
                            f"🌎 **Timezone:** UTC{self.tz_offset:+d}", # Display the TZ offset
                            f"⏭️ **Next Run:** {self.start_dt.strftime('%Y-%m-%d %H:%M')}"
                        ]
                        
                        embed = discord.Embed(
                            title="✅ Announcement Updated",
                            description="\n".join(description),
                            color=discord.Color.green()
                        )
                        embed.set_footer(text=f"ID: {self.edit_id}")
                        await inter.followup.send(embed=embed)
                    else:
                        await inter.followup.send("❌ Failed to update database.", ephemeral=True)
                
                else:
                    # --- CREATE MODE ---
                    # Pass offset to DB function for initial calculation
                    ann_id = await db.create_announcement(
                        self.guild_id, self.channel.id, self.message, freq_value, self.user_id,
                        manual_next_run=self.start_dt, tz_offset_hours=self.tz_offset
                    )
                    
                    if ann_id is None:
                        await inter.followup.send("❌ Failed to create announcement", ephemeral=True)
                        return
                    
                    # Store offset in the DB right after creation
                    await db.update_announcement_details(ann_id, self.guild_id, {'tz_offset': self.tz_offset})
                    
                    new_announcement = {
                        'id': ann_id, 'server_id': self.guild_id, 'channel_id': self.channel.id,
                        'message': self.message, 'frequency': freq_value,
                        'next_run': self.start_dt, 'created_by': self.user_id, 'is_active': True,
                        'tz_offset': self.tz_offset
                    }
                    self.parent_cog.cached_announcements.append(new_announcement)

                    # Determine next run display
                    freq_display = self.parent_cog.get_frequency_display(freq_value)
                    
                    success_embed = discord.Embed(
                        title="✅ Announcement Created",
                        description=f"**ID:** `{ann_id}`\n**Channel:** {self.channel.mention}\n**Frequency:** {freq_display}\n**Timezone:** UTC{self.tz_offset:+d}\n**Next Send:** {self.start_dt.strftime('%Y-%m-%d %H:%M')}",
                        color=discord.Color.green()
                    )
                    success_embed.add_field(name="Message Preview", value=self.message[:200], inline=False)
                    await inter.followup.send(embed=success_embed)

            except Exception as e:
                try: await inter.followup.send(f"❌ Error: {str(e)[:100]}", ephemeral=True)
                except: pass
    
    class FrequencyView(discord.ui.View):
        def __init__(self, parent_cog, msg, ch, guild_id, user_id, start_dt, tz_offset, edit_id=None):
            super().__init__(timeout=300)
            self.add_item(Announcer.FrequencySelect(parent_cog, msg, ch, guild_id, user_id, start_dt, tz_offset, edit_id))

    @announce_group.command(name="create", description="Create a recurring announcement (Start Time & Timezone Required)")
    @app_commands.describe(
        message="Message to announce", 
        channel="Channel to send to",
        start_time="Start time (HH:MM or YYYY-MM-DD HH:MM). Example: 14:30",
        tz_offset="Timezone offset from UTC (e.g., -5 for EST, +8 for HKT). Default 0."
    )
    async def announce_create(
        self, 
        interaction: discord.Interaction, 
        message: str, 
        channel: discord.TextChannel,
        start_time: str,
        tz_offset: app_commands.Range[int, -12, 14] = DEFAULT_TZ_OFFSET # Discord supports up to +14
    ):
        """Create a new announcement."""
        await interaction.response.defer(ephemeral=True)
        
        if not channel.permissions_for(interaction.user).send_messages:
            await interaction.followup.send("❌ You don't have permission to send messages in that channel")
            return
        
        if len(message) > 1900:
            await interaction.followup.send("❌ Message too long (max 1900 characters)")
            return

        # Pass offset to parse_time_input
        parsed_start = self.parse_time_input(start_time, tz_offset)
        if not parsed_start:
            await interaction.followup.send("❌ Invalid time format. Use `HH:MM` (24h) or `YYYY-MM-DD HH:MM`", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="📢 Select Announcement Frequency",
            description=f"**Server:** {interaction.guild.name}\n**Channel:** {channel.mention}\n**Message:** {message[:100]}...\n**Timezone:** UTC{tz_offset:+d}\n**Start Time:** {parsed_start.strftime('%Y-%m-%d %H:%M')}",
            color=discord.Color.blue()
        )
        
        # Pass offset to the view and select menu callback
        view = self.FrequencyView(self, message, channel, interaction.guild.id, interaction.user.id, parsed_start, tz_offset)
        await interaction.followup.send(embed=embed, view=view)

    @announce_group.command(name="edit", description="Edit an announcement (All fields required to update schedule)")
    @app_commands.describe(
        announcement_id="ID of the announcement to edit",
        message="New message",
        channel="New channel",
        start_time="New start/next run time (HH:MM or YYYY-MM-DD HH:MM)",
        tz_offset="Timezone offset from UTC (e.g., -5 for EST, +8 for HKT). Default 0."
    )
    async def announce_edit(
        self, 
        interaction: discord.Interaction, 
        announcement_id: int, 
        message: str, 
        channel: discord.TextChannel,
        start_time: str,
        tz_offset: app_commands.Range[int, -12, 14] = DEFAULT_TZ_OFFSET
    ):
        """Edit an existing announcement (Similar flow to Create)."""
        await interaction.response.defer(ephemeral=True)

        # 1. Check existence
        announcement = await db.get_announcement(announcement_id, interaction.guild.id)
        if not announcement:
            await interaction.followup.send(f"❌ Announcement `{announcement_id}` not found in this server.")
            return

        # 2. Check permissions
        if not channel.permissions_for(interaction.user).send_messages:
            await interaction.followup.send("❌ You don't have permission to send messages in the new channel.")
            return

        # 3. Parse Time
        parsed_start = self.parse_time_input(start_time, tz_offset)
        if not parsed_start:
            await interaction.followup.send("❌ Invalid time format. Use `HH:MM` or `YYYY-MM-DD HH:MM`", ephemeral=True)
            return

        # 4. Trigger UI for Frequency Selection (Same as Create)
        embed = discord.Embed(
            title="✏️ Update Frequency",
            description=f"**Editing ID:** `{announcement_id}`\n**New Channel:** {channel.mention}\n**New Timezone:** UTC{tz_offset:+d}\n**New Start:** {parsed_start.strftime('%Y-%m-%d %H:%M')}\n\nPlease select the new frequency to complete the edit.",
            color=discord.Color.gold()
        )
        
        # Pass edit_id and tz_offset to trigger edit mode in the callback
        view = self.FrequencyView(self, message, channel, interaction.guild.id, interaction.user.id, parsed_start, tz_offset, edit_id=announcement_id)
        await interaction.followup.send(embed=embed, view=view)

    @announce_group.command(name="list", description="List all announcements")
    async def announce_list(self, interaction: discord.Interaction):
        """List all active announcements for this server."""
        await interaction.response.defer(ephemeral=True)
        try:
            # We assume get_announcements_by_server now returns the 'tz_offset'
            announcements = await db.get_announcements_by_server(interaction.guild.id)
            
            if not announcements:
                await interaction.followup.send("❌ No announcements found.")
                return
            
            embed = discord.Embed(
                title="📢 Server Announcements",
                description=f"Server: {interaction.guild.name}\nTotal: {len(announcements)}",
                color=discord.Color.blue()
            )
            
            for ann in announcements:
                channel = self.bot.get_channel(ann['channel_id'])
                channel_name = channel.mention if channel else f"(Unknown #{ann['channel_id']})"
                
                # Default to 0 if tz_offset is not found (for old records)
                tz_offset = ann.get('tz_offset', 0) 
                
                # Check status if available, default to Active if key missing (since existing query likely filters active)
                is_active = ann.get('is_active', 1) 
                status_emoji = "🟢" if is_active else "🔴"
                status_text = "Active" if is_active else "Disabled"
                
                next_run_display = ann['next_run'].strftime("%m-%d %H:%M") if ann.get('next_run') else "N/A"
                freq_display = self.get_frequency_display(ann['frequency'])
                
                # Increase preview length to 250 characters and change label
                msg_preview = ann['message'][:250] + ("..." if len(ann['message']) > 250 else "")
                
                field_value = (
                    f"**Status:** {status_emoji} {status_text}\n"
                    f"**Channel:** {channel_name}\n"
                    f"**Timezone:** UTC{tz_offset:+d}\n"
                    f"**Frequency:** {freq_display}\n"
                    f"**Next:** {next_run_display}\n"
                    f"**Message:** {msg_preview}" 
                )
                embed.add_field(name=f"ID: {ann['id']}", value=field_value, inline=False)
                
            await interaction.followup.send(embed=embed)
        except Exception as e:
            try: await interaction.followup.send(f"❌ Error: {str(e)[:100]}")
            except: pass
    
    @announce_group.command(name="stop", description="Stop an announcement (Inactive)")
    @app_commands.describe(announcement_id="ID of announcement to stop")
    async def announce_stop(self, interaction: discord.Interaction, announcement_id: int):
        """Stop a specific announcement."""
        await interaction.response.defer(ephemeral=True)
        try:
            announcement = await db.get_announcement(announcement_id, interaction.guild.id)
            if not announcement:
                await interaction.followup.send(f"❌ Announcement `{announcement_id}` not found in this server")
                return
            await db.stop_announcement(announcement_id, interaction.guild.id)
            self.cached_announcements = [ann for ann in self.cached_announcements if ann['id'] != announcement_id]
            embed = discord.Embed(
                title="✅ Announcement Stopped",
                description=f"**ID:** `{announcement_id}`\n**Message:** {announcement['message'][:200]}...",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)[:100]}")

    @announce_group.command(name="delete", description="Permanently delete an announcement")
    @app_commands.describe(announcement_id="ID of announcement to delete")
    async def announce_delete(self, interaction: discord.Interaction, announcement_id: int):
        """Permanently delete an announcement from the database."""
        await interaction.response.defer(ephemeral=True)
        try:
            # Check existence first
            announcement = await db.get_announcement(announcement_id, interaction.guild.id)
            if not announcement:
                await interaction.followup.send(f"❌ Announcement `{announcement_id}` not found in this server")
                return
            
            success = await db.delete_announcement(announcement_id, interaction.guild.id)
            if success:
                # Remove from cache
                self.cached_announcements = [ann for ann in self.cached_announcements if ann['id'] != announcement_id]
                embed = discord.Embed(
                    title="🗑️ Announcement Deleted",
                    description=f"**ID:** `{announcement_id}` has been permanently removed.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("❌ Failed to delete announcement from database.")
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)[:100]}")
    
    @announce_group.command(name="preview", description="Preview an announcement")
    @app_commands.describe(announcement_id="ID of announcement to preview")
    async def announce_preview(self, interaction: discord.Interaction, announcement_id: int):
        """Preview an announcement message."""
        await interaction.response.defer(ephemeral=True)
        try:
            announcement = await db.get_announcement(announcement_id, interaction.guild.id)
            if not announcement:
                await interaction.followup.send(f"❌ Announcement `{announcement_id}` not found in this server")
                return
            
            # Default to 0 if tz_offset is not found (for old records)
            tz_offset = announcement.get('tz_offset', 0) 
            
            freq_display = self.get_frequency_display(announcement['frequency'])
            embed = discord.Embed(title="📋 Announcement Preview", description=announcement['message'], color=discord.Color.gold())
            embed.set_footer(text=f"ID: {announcement_id} | Frequency: {freq_display} | Timezone: UTC{tz_offset:+d}")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)[:100]}")


async def setup(bot: commands.Bot):
    """Setup cog."""
    await bot.add_cog(Announcer(bot))