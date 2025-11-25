import logging
import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Literal

logger = logging.getLogger(__name__)

# Store announcements in JSON file
ANNOUNCEMENTS_FILE = "announcements.json"

# Frequency choices
FREQUENCY_CHOICES = [
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
]


class Announcer(commands.Cog):
    """DotNotify-style announcement system with recurring messages."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.announcements = {}
        self.announcement_counter = 0
        self.load_announcements()
        self.send_announcements.start()
    
    def cog_unload(self):
        self.send_announcements.cancel()
    
    def load_announcements(self):
        """Load announcements from JSON file."""
        if os.path.exists(ANNOUNCEMENTS_FILE):
            try:
                with open(ANNOUNCEMENTS_FILE, 'r') as f:
                    data = json.load(f)
                    self.announcements = data.get("announcements", {})
                    self.announcement_counter = data.get("counter", 0)
                logger.info(f"✅ Loaded {len(self.announcements)} announcements")
            except Exception as e:
                logger.error(f"Error loading announcements: {e}")
        else:
            self.announcements = {}
            self.announcement_counter = 0
    
    def save_announcements(self):
        """Save announcements to JSON file."""
        try:
            with open(ANNOUNCEMENTS_FILE, 'w') as f:
                json.dump({
                    "announcements": self.announcements,
                    "counter": self.announcement_counter
                }, f, indent=2)
            logger.info("✅ Announcements saved")
        except Exception as e:
            logger.error(f"Error saving announcements: {e}")
    
    def get_next_run_time(self, frequency: str) -> datetime:
        """Calculate next run time based on frequency."""
        now = datetime.now()
        
        if frequency == "30min":
            return now + timedelta(minutes=30)
        elif frequency == "1hr":
            return now + timedelta(hours=1)
        elif frequency == "3hrs":
            return now + timedelta(hours=3)
        elif frequency == "6hrs":
            return now + timedelta(hours=6)
        elif frequency == "12hrs":
            return now + timedelta(hours=12)
        elif frequency == "1day":
            return now + timedelta(days=1)
        elif frequency == "3days":
            return now + timedelta(days=3)
        elif frequency == "1week":
            return now + timedelta(weeks=1)
        elif frequency == "2weeks":
            return now + timedelta(weeks=2)
        elif frequency == "1month":
            return now + timedelta(days=30)
        else:
            return None
    
    def get_frequency_display(self, frequency: str) -> str:
        """Get human-readable frequency display."""
        freq_map = {
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
    
    @tasks.loop(minutes=1)
    async def send_announcements(self):
        """Check and send announcements on schedule."""
        now = datetime.now().isoformat()
        
        announcements_to_remove = []
        
        for ann_id, announcement in self.announcements.items():
            try:
                next_run = announcement.get("next_run")
                
                if next_run and next_run <= now:
                    channel_id = announcement.get("channel_id")
                    message = announcement.get("message")
                    frequency = announcement.get("frequency")
                    
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        # Send the announcement
                        await channel.send(message)
                        logger.info(f"✅ Sent announcement {ann_id}")
                        
                        # Calculate next run time
                        if frequency:
                            next_run_dt = self.get_next_run_time(frequency)
                            if next_run_dt:
                                announcement["next_run"] = next_run_dt.isoformat()
                                self.save_announcements()
                    else:
                        logger.warning(f"Channel {channel_id} not found for announcement {ann_id}")
                        announcements_to_remove.append(ann_id)
            
            except Exception as e:
                logger.error(f"Error sending announcement {ann_id}: {e}")
        
        # Remove announcements with invalid channels
        for ann_id in announcements_to_remove:
            del self.announcements[ann_id]
        
        if announcements_to_remove:
            self.save_announcements()
    
    @send_announcements.before_loop
    async def before_send_announcements(self):
        """Wait for bot to be ready before starting loop."""
        await self.bot.wait_until_ready()
    
    # Create announce command group
    announce_group = app_commands.Group(name="announce", description="Announcement management")
    
    @announce_group.command(name="create", description="Create a recurring announcement")
    @app_commands.describe(
        message="Message to announce",
        channel="Channel to send to",
        frequency="How often to send the announcement"
    )
    @app_commands.choices(frequency=FREQUENCY_CHOICES)
    async def announce_create(
        self, 
        interaction: discord.Interaction, 
        message: str, 
        channel: discord.TextChannel,
        frequency: app_commands.Choice[str]
    ):
        """Create a new announcement."""
        await interaction.response.defer(ephemeral=True)
        
        # Validate message length
        if len(message) > 1900:
            await interaction.followup.send("❌ Message too long (max 1900 characters)")
            return
        
        # Create announcement
        self.announcement_counter += 1
        ann_id = str(self.announcement_counter)
        
        now = datetime.now()
        freq_value = frequency.value
        next_run = self.get_next_run_time(freq_value)
        
        self.announcements[ann_id] = {
            "id": ann_id,
            "message": message,
            "channel_id": channel.id,
            "frequency": freq_value,
            "created_at": now.isoformat(),
            "next_run": next_run.isoformat() if next_run else None
        }
        
        self.save_announcements()
        
        # Format response
        next_run_display = next_run.strftime("%Y-%m-%d %H:%M") if next_run else "N/A"
        freq_display = self.get_frequency_display(freq_value)
        
        embed = discord.Embed(
            title="✅ Announcement Created",
            description=f"**ID:** `{ann_id}`\n**Channel:** {channel.mention}\n**Frequency:** {freq_display}\n**Next Send:** {next_run_display}",
            color=discord.Color.green()
        )
        embed.add_field(name="Message Preview", value=message[:200] + ("..." if len(message) > 200 else ""), inline=False)
        
        await interaction.followup.send(embed=embed)
    
    @announce_group.command(name="list", description="List all announcements")
    async def announce_list(self, interaction: discord.Interaction):
        """List all active announcements."""
        await interaction.response.defer(ephemeral=True)
        
        if not self.announcements:
            await interaction.followup.send("❌ No announcements scheduled")
            return
        
        # Build announcement list
        embed = discord.Embed(
            title="📢 Active Announcements",
            description=f"Total: {len(self.announcements)}",
            color=discord.Color.blue()
        )
        
        for ann_id, announcement in list(self.announcements.items())[:10]:  # Max 10 per embed
            channel_id = announcement.get("channel_id")
            frequency = announcement.get("frequency", "unknown")
            next_run = announcement.get("next_run", "N/A")
            message = announcement.get("message", "No message")
            
            channel = self.bot.get_channel(channel_id)
            channel_name = channel.mention if channel else f"(Unknown #{channel_id})"
            
            if next_run != "N/A":
                next_run_dt = datetime.fromisoformat(next_run)
                next_run_display = next_run_dt.strftime("%m-%d %H:%M")
            else:
                next_run_display = "N/A"
            
            freq_display = self.get_frequency_display(frequency)
            field_value = f"**Channel:** {channel_name}\n**Frequency:** {freq_display}\n**Next Send:** {next_run_display}\n**Message:** {message[:100]}{'...' if len(message) > 100 else ''}"
            embed.add_field(name=f"ID: {ann_id}", value=field_value, inline=False)
        
        if len(self.announcements) > 10:
            embed.set_footer(text=f"Showing 10 of {len(self.announcements)} announcements")
        
        await interaction.followup.send(embed=embed)
    
    @announce_group.command(name="stop", description="Stop an announcement")
    @app_commands.describe(announcement_id="ID of announcement to stop")
    async def announce_stop(self, interaction: discord.Interaction, announcement_id: str):
        """Stop a specific announcement."""
        await interaction.response.defer(ephemeral=True)
        
        if announcement_id not in self.announcements:
            await interaction.followup.send(f"❌ Announcement `{announcement_id}` not found")
            return
        
        announcement = self.announcements[announcement_id]
        message = announcement.get("message", "Unknown")
        
        del self.announcements[announcement_id]
        self.save_announcements()
        
        embed = discord.Embed(
            title="✅ Announcement Stopped",
            description=f"**ID:** `{announcement_id}`\n**Message:** {message[:200]}...",
            color=discord.Color.green()
        )
        
        await interaction.followup.send(embed=embed)
    
    @announce_group.command(name="preview", description="Preview an announcement")
    @app_commands.describe(announcement_id="ID of announcement to preview")
    async def announce_preview(self, interaction: discord.Interaction, announcement_id: str):
        """Preview an announcement message."""
        await interaction.response.defer(ephemeral=True)
        
        if announcement_id not in self.announcements:
            await interaction.followup.send(f"❌ Announcement `{announcement_id}` not found")
            return
        
        announcement = self.announcements[announcement_id]
        frequency = announcement.get("frequency", "unknown")
        freq_display = self.get_frequency_display(frequency)
        
        embed = discord.Embed(
            title="📋 Announcement Preview",
            description=announcement.get("message"),
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"ID: {announcement_id} | Frequency: {freq_display}")
        
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    """Setup cog."""
    await bot.add_cog(Announcer(bot))