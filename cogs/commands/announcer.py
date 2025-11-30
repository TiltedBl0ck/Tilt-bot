import logging
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from typing import Optional
from cogs.utils import db

logger = logging.getLogger(__name__)


class Announcer(commands.Cog):
    """DotNotify-style announcement system with recurring messages - Database Backed."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.next_check_time = datetime.now()
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
    
    def cog_unload(self):
        self.send_announcements.cancel()
    
    @tasks.loop(seconds=5)
    async def send_announcements(self):
        """Check and send announcements on schedule."""
        now = datetime.now()

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
    
    @announce_group.command(name="create", description="Create a recurring announcement")
    @app_commands.describe(message="Message to announce", channel="Channel to send to")
    async def announce_create(self, interaction: discord.Interaction, message: str, channel: discord.TextChannel):
        """Create a new announcement."""
        await interaction.response.defer(ephemeral=True)
        
        if not channel.permissions_for(interaction.user).send_messages:
            await interaction.followup.send("❌ You don't have permission to send messages in that channel")
            return
        
        if len(message) > 1900:
            await interaction.followup.send("❌ Message too long (max 1900 characters)")
            return
        
        try:
            embed = discord.Embed(
                title="📢 Select Announcement Frequency",
                description=f"**Server:** {interaction.guild.name}\n**Channel:** {channel.mention}\n**Message Preview:** {message[:150]}",
                color=discord.Color.blue()
            )
            
            class FrequencySelect(discord.ui.Select):
                def __init__(self, parent_cog, msg, ch, guild_id, user_id):
                    self.parent_cog = parent_cog
                    self.message = msg
                    self.channel = ch
                    self.guild_id = guild_id
                    self.user_id = user_id
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
                    super().__init__(placeholder="Choose frequency...", min_values=1, max_values=1, options=options)
                
                async def callback(self, inter: discord.Interaction):
                    freq_value = self.values[0]
                    try:
                        await inter.response.defer()
                        ann_id = await db.create_announcement(self.guild_id, self.channel.id, self.message, freq_value, self.user_id)
                        
                        if ann_id is None:
                            await inter.followup.send("❌ Failed to create announcement", ephemeral=True)
                            return
                        
                        new_announcement = {
                            'id': ann_id, 'server_id': self.guild_id, 'channel_id': self.channel.id,
                            'message': self.message, 'frequency': freq_value,
                            'next_run': db.get_next_run_time(freq_value), 'created_by': self.user_id, 'is_active': True
                        }
                        self.parent_cog.cached_announcements.append(new_announcement)

                        try:
                            await self.channel.send(self.message)
                        except Exception: pass
                        
                        next_run = db.get_next_run_time(freq_value)
                        next_run_display = next_run.strftime("%Y-%m-%d %H:%M") if next_run else "N/A"
                        freq_display = self.parent_cog.get_frequency_display(freq_value)
                        
                        success_embed = discord.Embed(
                            title="✅ Announcement Created",
                            description=f"**ID:** `{ann_id}`\n**Channel:** {self.channel.mention}\n**Frequency:** {freq_display}\n**Next Send:** {next_run_display}",
                            color=discord.Color.green()
                        )
                        success_embed.add_field(name="Message Preview", value=self.message[:200], inline=False)
                        await inter.followup.send(embed=success_embed)
                    except Exception as e:
                        try: await inter.followup.send(f"❌ Error: {str(e)[:100]}", ephemeral=True)
                        except: pass
            
            class FrequencyView(discord.ui.View):
                def __init__(self, parent_cog, msg, ch, guild_id, user_id):
                    super().__init__(timeout=300)
                    self.add_item(FrequencySelect(parent_cog, msg, ch, guild_id, user_id))
            
            view = FrequencyView(self, message, channel, interaction.guild.id, interaction.user.id)
            await interaction.followup.send(embed=embed, view=view)
        except Exception as e:
            try: await interaction.followup.send(f"❌ Error: {str(e)[:100]}")
            except: pass

    @announce_group.command(name="edit", description="Edit an existing announcement")
    @app_commands.describe(
        announcement_id="ID of the announcement to edit",
        message="New message (optional)",
        frequency="New frequency (optional)",
        channel="New channel (optional)"
    )
    @app_commands.choices(frequency=[
        app_commands.Choice(name="Every 1 Minute", value="1min"),
        app_commands.Choice(name="Every 3 Minutes", value="3min"),
        app_commands.Choice(name="Every 5 Minutes", value="5min"),
        app_commands.Choice(name="Every 10 Minutes", value="10min"),
        app_commands.Choice(name="Every 15 Minutes", value="15min"),
        app_commands.Choice(name="Every 30 Minutes", value="30min"),
        app_commands.Choice(name="Every 1 Hour", value="1hr"),
        app_commands.Choice(name="Every 3 Hours", value="3hrs"),
        app_commands.Choice(name="Every 6 Hours", value="6hrs"),
        app_commands.Choice(name="Every 12 Hours", value="12hrs"),
        app_commands.Choice(name="Every 1 Day", value="1day"),
        app_commands.Choice(name="Every 3 Days", value="3days"),
        app_commands.Choice(name="Every 1 Week", value="1week"),
        app_commands.Choice(name="Every 2 Weeks", value="2weeks"),
        app_commands.Choice(name="Every 1 Month", value="1month"),
    ])
    async def announce_edit(
        self, 
        interaction: discord.Interaction, 
        announcement_id: int, 
        message: Optional[str] = None, 
        frequency: Optional[str] = None, 
        channel: Optional[discord.TextChannel] = None
    ):
        """Edit an existing announcement's details."""
        await interaction.response.defer(ephemeral=True)

        # 1. Check if ANY edit is requested
        if not message and not frequency and not channel:
            await interaction.followup.send("⚠️ No changes provided. Please specify a message, frequency, or channel to update.")
            return

        # 2. Check existence in DB
        announcement = await db.get_announcement(announcement_id, interaction.guild.id)
        if not announcement:
            await interaction.followup.send(f"❌ Announcement `{announcement_id}` not found in this server.")
            return

        # 3. Check permissions if channel is changing
        if channel and not channel.permissions_for(interaction.user).send_messages:
            await interaction.followup.send("❌ You don't have permission to send messages in the new channel.")
            return

        updates = {}
        description_lines = []

        if message:
            updates['message'] = message
            description_lines.append("📝 **Message:** Updated")
        
        if channel:
            updates['channel_id'] = channel.id
            description_lines.append(f"📺 **Channel:** {channel.mention}")

        if frequency:
            updates['frequency'] = frequency
            # Recalculate next run based on new frequency immediately
            new_next_run = db.get_next_run_time(frequency)
            updates['next_run'] = new_next_run.isoformat() if new_next_run else None
            description_lines.append(f"⏱️ **Frequency:** {self.get_frequency_display(frequency)}")
            description_lines.append(f"⏭️ **Next Run:** {new_next_run.strftime('%Y-%m-%d %H:%M') if new_next_run else 'N/A'}")

        # 4. Perform Update
        success = await db.update_announcement_details(announcement_id, interaction.guild.id, updates)

        if success:
            # 5. Update Local Cache
            # Find and update the item in the cache list
            for i, ann in enumerate(self.cached_announcements):
                if ann['id'] == announcement_id:
                    # Update only the keys that changed
                    for key, val in updates.items():
                        # Handle specific conversions for cache
                        if key == 'next_run' and val:
                             self.cached_announcements[i][key] = datetime.fromisoformat(val)
                        else:
                             self.cached_announcements[i][key] = val
                    break
            
            # If the item wasn't in cache (e.g. freshly rebooted), we might want to fetch it or just rely on next sync
            # Since update_announcement_details affects DB, the next sync loop will pick it up anyway if cache is empty.

            embed = discord.Embed(
                title="✅ Announcement Updated",
                description="\n".join(description_lines),
                color=discord.Color.green()
            )
            embed.set_footer(text=f"ID: {announcement_id}")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ Failed to update the announcement in the database.")

    @announce_group.command(name="list", description="List all announcements")
    async def announce_list(self, interaction: discord.Interaction):
        """List all active announcements for this server."""
        await interaction.response.defer(ephemeral=True)
        try:
            announcements = await db.get_announcements_by_server(interaction.guild.id)
            if not announcements:
                await interaction.followup.send("❌ No announcements scheduled")
                return
            
            embed = discord.Embed(
                title="📢 Active Announcements",
                description=f"Server: {interaction.guild.name}\nTotal: {len(announcements)}",
                color=discord.Color.blue()
            )
            for ann in announcements:
                channel = self.bot.get_channel(ann['channel_id'])
                channel_name = channel.mention if channel else f"(Unknown #{ann['channel_id']})"
                next_run_display = ann['next_run'].strftime("%m-%d %H:%M") if ann['next_run'] else "N/A"
                freq_display = self.get_frequency_display(ann['frequency'])
                msg_preview = ann['message'][:75] + ("..." if len(ann['message']) > 75 else "")
                field_value = f"**Channel:** {channel_name}\n**Frequency:** {freq_display}\n**Next:** {next_run_display}\n**Msg:** {msg_preview}"
                embed.add_field(name=f"ID: {ann['id']}", value=field_value, inline=False)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            try: await interaction.followup.send(f"❌ Error: {str(e)[:100]}")
            except: pass
    
    @announce_group.command(name="stop", description="Stop an announcement")
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
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed)
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