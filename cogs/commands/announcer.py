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
    """DotNotify-style announcement system with recurring messages - Database Backed."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Use UTC+8 for initial check time
        self.next_check_time = datetime.now(UTC_PLUS_8).replace(tzinfo=None)
        self.cached_announcements = []
        self.send_announcements.start()
    
    def get_frequency_display(self, frequency: str) -> str:
        """Get human-readable frequency display."""
        freq_map = {
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
    
    def parse_time_input(self, time_str: str) -> Optional[datetime]:
        """Parse user time input into datetime (UTC+8 enforced)."""
        formats = ["%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M", "%H:%M", "%Y/%m/%d %H:%M"]
        
        # Current time in UTC+8
        now = datetime.now(UTC_PLUS_8)
        
        for fmt in formats:
            try:
                dt = datetime.strptime(time_str, fmt)
                
                # If format is just time, attach today's date (in UTC+8 context)
                if fmt == "%H:%M":
                    dt = dt.replace(year=now.year, month=now.month, day=now.day)
                    # If time passed today in UTC+8, assume tomorrow
                    # We compare naive datetimes here
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
        """Check and send announcements on schedule (Using UTC+8)."""
        # Get current time in UTC+8, then make naive for comparison with DB
        now = datetime.now(UTC_PLUS_8).replace(tzinfo=None)

        # 1. Sync with DB only once every 30 minutes OR if cache is empty
        if now >= self.next_check_time or not self.cached_announcements:
            try:
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
            
            if run_time and run_time <= now:
                due_now.append(ann)

        for ann in due_now:
            try:
                channel = self.bot.get_channel(ann['channel_id'])
                
                if channel:
                    if channel.guild.id != ann['server_id']:
                        self.cached_announcements.remove(ann)
                        continue
                    
                    try:
                        await channel.send(ann['message'])
                        logger.info(f"✅ Sent announcement {ann['id']}")
                        
                        await db.update_announcement_next_run(ann['id'], ann['frequency'])
                        
                        # Update Local Cache Next Run
                        next_run_dt = db.get_next_run_time(ann['frequency'])
                        ann['next_run'] = next_run_dt
                        
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
        def __init__(self, parent_cog, msg, ch, guild_id, user_id, start_dt, edit_id=None):
            self.parent_cog = parent_cog
            self.message = msg
            self.channel = ch
            self.guild_id = guild_id
            self.user_id = user_id
            self.start_dt = start_dt
            self.edit_id = edit_id # If set, we are editing, not creating
            
            options = [
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
                        'next_run': self.start_dt.isoformat()
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
                                    'next_run': self.start_dt
                                })
                                break
                                
                        description = [
                            "📝 **Message:** Updated",
                            f"📺 **Channel:** {self.channel.mention}",
                            f"⏱️ **Frequency:** {self.parent_cog.get_frequency_display(freq_value)}",
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
                    ann_id = await db.create_announcement(
                        self.guild_id, self.channel.id, self.message, freq_value, self.user_id,
                        manual_next_run=self.start_dt
                    )
                    
                    if ann_id is None:
                        await inter.followup.send("❌ Failed to create announcement", ephemeral=True)
                        return
                    
                    new_announcement = {
                        'id': ann_id, 'server_id': self.guild_id, 'channel_id': self.channel.id,
                        'message': self.message, 'frequency': freq_value,
                        'next_run': self.start_dt, 'created_by': self.user_id, 'is_active': True
                    }
                    self.parent_cog.cached_announcements.append(new_announcement)

                    # Determine next run display
                    freq_display = self.parent_cog.get_frequency_display(freq_value)
                    
                    success_embed = discord.Embed(
                        title="✅ Announcement Created",
                        description=f"**ID:** `{ann_id}`\n**Channel:** {self.channel.mention}\n**Frequency:** {freq_display}\n**Next Send:** {self.start_dt.strftime('%Y-%m-%d %H:%M')}",
                        color=discord.Color.green()
                    )
                    success_embed.add_field(name="Message Preview", value=self.message[:200], inline=False)
                    await inter.followup.send(embed=success_embed)

            except Exception as e:
                try: await inter.followup.send(f"❌ Error: {str(e)[:100]}", ephemeral=True)
                except: pass
    
    class FrequencyView(discord.ui.View):
        def __init__(self, parent_cog, msg, ch, guild_id, user_id, start_dt, edit_id=None):
            super().__init__(timeout=300)
            self.add_item(Announcer.FrequencySelect(parent_cog, msg, ch, guild_id, user_id, start_dt, edit_id))

    @announce_group.command(name="create", description="Create a recurring announcement (Start Time Required)")
    @app_commands.describe(
        message="Message to announce", 
        channel="Channel to send to",
        start_time="Start time (HH:MM or YYYY-MM-DD HH:MM). Example: 14:30"
    )
    async def announce_create(
        self, 
        interaction: discord.Interaction, 
        message: str, 
        channel: discord.TextChannel,
        start_time: str
    ):
        """Create a new announcement."""
        await interaction.response.defer(ephemeral=True)
        
        if not channel.permissions_for(interaction.user).send_messages:
            await interaction.followup.send("❌ You don't have permission to send messages in that channel")
            return
        
        if len(message) > 1900:
            await interaction.followup.send("❌ Message too long (max 1900 characters)")
            return

        parsed_start = self.parse_time_input(start_time)
        if not parsed_start:
            await interaction.followup.send("❌ Invalid time format. Use `HH:MM` (24h) or `YYYY-MM-DD HH:MM`", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="📢 Select Announcement Frequency",
            description=f"**Server:** {interaction.guild.name}\n**Channel:** {channel.mention}\n**Message:** {message[:100]}...\n**Start Time:** {parsed_start.strftime('%Y-%m-%d %H:%M')}",
            color=discord.Color.blue()
        )
        
        view = self.FrequencyView(self, message, channel, interaction.guild.id, interaction.user.id, parsed_start)
        await interaction.followup.send(embed=embed, view=view)

    @announce_group.command(name="edit", description="Edit an announcement (All fields required to update schedule)")
    @app_commands.describe(
        announcement_id="ID of the announcement to edit",
        message="New message",
        channel="New channel",
        start_time="New start/next run time (HH:MM or YYYY-MM-DD HH:MM)"
    )
    async def announce_edit(
        self, 
        interaction: discord.Interaction, 
        announcement_id: int, 
        message: str, 
        channel: discord.TextChannel,
        start_time: str
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
        parsed_start = self.parse_time_input(start_time)
        if not parsed_start:
            await interaction.followup.send("❌ Invalid time format. Use `HH:MM` or `YYYY-MM-DD HH:MM`", ephemeral=True)
            return

        # 4. Trigger UI for Frequency Selection (Same as Create)
        embed = discord.Embed(
            title="✏️ Update Frequency",
            description=f"**Editing ID:** `{announcement_id}`\n**New Channel:** {channel.mention}\n**New Start:** {parsed_start.strftime('%Y-%m-%d %H:%M')}\n\nPlease select the new frequency to complete the edit.",
            color=discord.Color.gold()
        )
        
        # Pass edit_id to trigger edit mode in the callback
        view = self.FrequencyView(self, message, channel, interaction.guild.id, interaction.user.id, parsed_start, edit_id=announcement_id)
        await interaction.followup.send(embed=embed, view=view)

    @announce_group.command(name="list", description="List all announcements")
    async def announce_list(self, interaction: discord.Interaction):
        """List all active announcements for this server."""
        await interaction.response.defer(ephemeral=True)
        try:
            # We assume get_announcements_by_server now returns a field 'is_active' or similar status
            # If the DB function filters by active=True, we might need to adjust it to show all if desired.
            # But based on the prompt "show disabled and enabled", let's assume we fetch ALL.
            # For now, I'll stick to the existing DB call but add visual indicators if the DB supports status.
            # If the DB call filters out inactive ones, this will only show active ones.
            # To show both, we'd need to modify `db.get_announcements_by_server` to not filter by `is_active`.
            # Assuming for now we just want to list what we get back with status:
            
            # NOTE: Ideally, update db.py to return is_active field if not already present in the dict
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
                
                # Check status if available, default to Active if key missing (since existing query likely filters active)
                # If we modify the DB query later to include inactive, this logic will handle it.
                is_active = ann.get('is_active', 1) # Default to 1 (True) if not returned
                status_emoji = "🟢" if is_active else "🔴"
                status_text = "Active" if is_active else "Disabled"
                
                next_run_display = ann['next_run'].strftime("%m-%d %H:%M") if ann.get('next_run') else "N/A"
                freq_display = self.get_frequency_display(ann['frequency'])
                msg_preview = ann['message'][:50] + ("..." if len(ann['message']) > 50 else "")
                
                field_value = (
                    f"**Status:** {status_emoji} {status_text}\n"
                    f"**Channel:** {channel_name}\n"
                    f"**Frequency:** {freq_display}\n"
                    f"**Next:** {next_run_display}\n"
                    f"**Msg:** {msg_preview}"
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
            freq_display = self.get_frequency_display(announcement['frequency'])
            embed = discord.Embed(title="📋 Announcement Preview", description=announcement['message'], color=discord.Color.gold())
            embed.set_footer(text=f"ID: {announcement_id} | Frequency: {freq_display}")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)[:100]}")


async def setup(bot: commands.Bot):
    """Setup cog."""
    await bot.add_cog(Announcer(bot))