import logging
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime
from cogs.utils import db

logger = logging.getLogger(__name__)


class Announcer(commands.Cog):
    """DotNotify-style announcement system with recurring messages - Database Backed."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
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
    
    @tasks.loop(minutes=1)
    async def send_announcements(self):
        """Check and send announcements on schedule."""
        try:
            announcements = await db.get_due_announcements()
            
            for ann in announcements:
                try:
                    channel = self.bot.get_channel(ann['channel_id'])
                    
                    if channel:
                        # Verify channel is in correct server (security check)
                        if channel.guild.id != ann['server_id']:
                            logger.warning(f"Security: Announcement {ann['id']} channel not in correct server")
                            continue
                        
                        try:
                            await channel.send(ann['message'])
                            logger.info(f"✅ Sent announcement {ann['id']}")
                        except Exception as e:
                            logger.error(f"Failed to send announcement {ann['id']}: {e}")
                        
                        # Calculate next run time
                        await db.update_announcement_next_run(ann['id'], ann['frequency'])
                    else:
                        logger.warning(f"Channel {ann['channel_id']} not found for announcement {ann['id']}")
                        # Mark as inactive if channel doesn't exist
                        await db.mark_announcement_inactive(ann['id'])
                
                except Exception as e:
                    logger.error(f"Error processing announcement {ann['id']}: {e}")
        
        except Exception as e:
            logger.error(f"Error in send_announcements task: {e}")
    
    @send_announcements.before_loop
    async def before_send_announcements(self):
        """Wait for bot to be ready before starting loop."""
        await self.bot.wait_until_ready()
    
    # Create announce command group
    announce_group = app_commands.Group(name="announce", description="Announcement management")
    
    @announce_group.command(name="create", description="Create a recurring announcement")
    @app_commands.describe(
        message="Message to announce",
        channel="Channel to send to"
    )
    async def announce_create(
        self, 
        interaction: discord.Interaction, 
        message: str, 
        channel: discord.TextChannel
    ):
        """Create a new announcement."""
        await interaction.response.defer(ephemeral=True)
        
        # Security: Check if user has permissions in this server
        if not channel.permissions_for(interaction.user).send_messages:
            await interaction.followup.send("❌ You don't have permission to send messages in that channel")
            return
        
        # Validate message length
        if len(message) > 1900:
            await interaction.followup.send("❌ Message too long (max 1900 characters)")
            return
        
        try:
            # Send confirmation with frequency selector
            embed = discord.Embed(
                title="📢 Select Announcement Frequency",
                description=f"**Server:** {interaction.guild.name}\n**Channel:** {channel.mention}\n**Message Preview:** {message[:150]}{'...' if len(message) > 150 else ''}",
                color=discord.Color.blue()
            )
            
            # Create select menu for frequency
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
                    super().__init__(
                        placeholder="Choose frequency...",
                        min_values=1,
                        max_values=1,
                        options=options
                    )
                
                async def callback(self, inter: discord.Interaction):
                    freq_value = self.values[0]
                    
                    try:
                        await inter.response.defer()
                        
                        # Create announcement in database
                        ann_id = await db.create_announcement(
                            self.guild_id,
                            self.channel.id,
                            self.message,
                            freq_value,
                            self.user_id
                        )
                        
                        if ann_id is None:
                            await inter.followup.send("❌ Failed to create announcement", ephemeral=True)
                            return
                        
                        # Send message immediately to the channel
                        try:
                            await self.channel.send(self.message)
                            logger.info(f"✅ Sent initial announcement {ann_id}")
                        except Exception as e:
                            logger.error(f"Failed to send initial announcement {ann_id}: {e}")
                        
                        # Format response
                        next_run = db.get_next_run_time(freq_value)
                        next_run_display = next_run.strftime("%Y-%m-%d %H:%M") if next_run else "N/A"
                        freq_display = self.parent_cog.get_frequency_display(freq_value)
                        
                        success_embed = discord.Embed(
                            title="✅ Announcement Created",
                            description=f"**ID:** `{ann_id}`\n**Channel:** {self.channel.mention}\n**Frequency:** {freq_display}\n**Next Send:** {next_run_display}",
                            color=discord.Color.green()
                        )
                        success_embed.add_field(name="Message Preview", value=self.message[:200] + ("..." if len(self.message) > 200 else ""), inline=False)
                        
                        await inter.followup.send(embed=success_embed)
                    except Exception as e:
                        logger.error(f"Error in frequency select: {e}")
                        try:
                            await inter.followup.send(f"❌ Error: {str(e)[:100]}", ephemeral=True)
                        except:
                            pass
            
            # Create view with select menu
            class FrequencyView(discord.ui.View):
                def __init__(self, parent_cog, msg, ch, guild_id, user_id):
                    super().__init__(timeout=300)
                    self.add_item(FrequencySelect(parent_cog, msg, ch, guild_id, user_id))
            
            view = FrequencyView(self, message, channel, interaction.guild.id, interaction.user.id)
            await interaction.followup.send(embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error in create command: {e}")
            try:
                await interaction.followup.send(f"❌ Error: {str(e)[:100]}")
            except:
                pass
    
    @announce_group.command(name="list", description="List all announcements")
    async def announce_list(self, interaction: discord.Interaction):
        """List all active announcements for this server."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            announcements = await db.get_announcements_by_server(interaction.guild.id)
            
            if not announcements:
                await interaction.followup.send("❌ No announcements scheduled")
                return
            
            # Build announcement list
            embed = discord.Embed(
                title="📢 Active Announcements",
                description=f"Server: {interaction.guild.name}\nTotal: {len(announcements)}",
                color=discord.Color.blue()
            )
            
            for ann in announcements:
                channel_id = ann['channel_id']
                frequency = ann['frequency']
                next_run = ann['next_run']
                message = ann['message']
                
                channel = self.bot.get_channel(channel_id)
                channel_name = channel.mention if channel else f"(Unknown #{channel_id})"
                
                if next_run:
                    try:
                        next_run_display = next_run.strftime("%m-%d %H:%M")
                    except:
                        next_run_display = "N/A"
                else:
                    next_run_display = "N/A"
                
                freq_display = self.get_frequency_display(frequency)
                msg_preview = message[:75] + ("..." if len(message) > 75 else "")
                field_value = f"**Channel:** {channel_name}\n**Frequency:** {freq_display}\n**Next:** {next_run_display}\n**Msg:** {msg_preview}"
                embed.add_field(name=f"ID: {ann['id']}", value=field_value, inline=False)
            
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in list command: {e}")
            try:
                await interaction.followup.send(f"❌ Error: {str(e)[:100]}")
            except:
                pass
    
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
            
            # Stop the announcement
            await db.stop_announcement(announcement_id, interaction.guild.id)
            
            message = announcement['message']
            
            embed = discord.Embed(
                title="✅ Announcement Stopped",
                description=f"**ID:** `{announcement_id}`\n**Message:** {message[:200]}...",
                color=discord.Color.green()
            )
            
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error stopping announcement: {e}")
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
            
            frequency = announcement['frequency']
            freq_display = self.get_frequency_display(frequency)
            
            embed = discord.Embed(
                title="📋 Announcement Preview",
                description=announcement['message'],
                color=discord.Color.gold()
            )
            embed.set_footer(text=f"ID: {announcement_id} | Frequency: {freq_display}")
            
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error previewing announcement: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)[:100]}")


async def setup(bot: commands.Bot):
    """Setup cog."""
    await bot.add_cog(Announcer(bot))