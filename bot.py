# Complete All-in-One Tilt-bot with Full Command Set
# Save this as `bot.py`

import discord
import os
import random
import asyncio
import logging
import traceback
import sys
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional, Union, List, Dict
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if BOT_TOKEN is None:
    print("Error: BOT_TOKEN not found. Make sure you have a .env file with the token.")
    exit(1)

# --- DATABASE SETUP ---
def init_database():
    """Initialize SQLite database for warnings, XP, and configurations"""
    conn = sqlite3.connect('tilt_bot.db')
    cursor = conn.cursor()
    
    # Warnings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            guild_id INTEGER,
            moderator_id INTEGER,
            reason TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # XP System table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_xp (
            user_id INTEGER,
            guild_id INTEGER,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            last_message DATETIME,
            PRIMARY KEY (user_id, guild_id)
        )
    ''')
    
    # Server configurations
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS server_config (
            guild_id INTEGER PRIMARY KEY,
            welcome_channel INTEGER,
            goodbye_channel INTEGER,
            mod_log_channel INTEGER,
            autorole INTEGER,
            welcome_message TEXT,
            goodbye_message TEXT
        )
    ''')
    
    # Tickets table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            channel_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            guild_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'open'
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database
init_database()

# --- LOGGING SETUP ---
def setup_logging():
    """Configure logging with both file and console output"""
    os.makedirs('logs', exist_ok=True)
    
    log_format = logging.Formatter(
        '%(asctime)s:%(levelname)s:%(name)s: %(message)s'
    )
    
    file_handler = logging.FileHandler(
        filename='logs/tilt-bot.log', 
        encoding='utf-8', 
        mode='a'
    )
    file_handler.setFormatter(log_format)
    file_handler.setLevel(logging.INFO)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    console_handler.setLevel(logging.INFO)
    
    discord_logger = logging.getLogger('discord')
    discord_logger.setLevel(logging.INFO)
    discord_logger.addHandler(file_handler)
    discord_logger.addHandler(console_handler)
    
    bot_logger = logging.getLogger('tilt_bot')
    bot_logger.setLevel(logging.INFO)
    bot_logger.addHandler(file_handler)
    bot_logger.addHandler(console_handler)
    
    return bot_logger

logger = setup_logging()

# --- BOT SETUP ---
class TiltBot(commands.Bot):
    """Enhanced bot class with custom initialization and error handling"""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.guilds = True
        
        super().__init__(
            command_prefix="/",
            intents=intents,
            help_command=None,
            case_insensitive=True,
            strip_after_prefix=True
        )
        
        self.commands_used = 0
        self.start_time = datetime.now(timezone.utc)
        
    async def setup_hook(self):
        """Called when the bot is starting up"""
        logger.info("Setting up bot...")
        
        # Add command groups
        self.tree.add_command(Moderation(self))
        self.tree.add_command(Utility(self))
        self.tree.add_command(Fun(self))
        self.tree.add_command(Music(self))
        self.tree.add_command(Admin(self))
        self.tree.add_command(Levels(self))
        self.tree.add_command(Tickets(self))
        self.tree.add_command(Config(self))
        
        # Sync commands globally
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s) globally")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
    
    async def on_ready(self):
        """Called when bot is fully ready"""
        logger.info(f'{self.user} is now online and ready!')
        logger.info(f'Connected to {len(self.guilds)} guild(s)')
        logger.info('-' * 50)
        
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="for /help | All-in-One Bot"
        )
        await self.change_presence(activity=activity, status=discord.Status.online)
        
        # Start XP processing task
        self.xp_processor.start()

    @tasks.loop(seconds=30)
    async def xp_processor(self):
        """Process XP gains every 30 seconds"""
        pass  # XP processing logic would go here

# Initialize bot
bot = TiltBot()

# --- ERROR HANDLING ---
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Comprehensive error handler for all slash commands"""
    logger.error(f"Error in command {interaction.command.name if interaction.command else 'Unknown'}: {error}")
    
    responded = interaction.response.is_done()
    
    try:
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title="❌ Missing Permissions",
                description=f"You need the following permissions: `{', '.join(error.missing_permissions)}`",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
        elif isinstance(error, app_commands.BotMissingPermissions):
            embed = discord.Embed(
                title="❌ Bot Missing Permissions",
                description=f"I need the following permissions: `{', '.join(error.missing_permissions)}`",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
        elif isinstance(error, app_commands.CommandOnCooldown):
            embed = discord.Embed(
                title="⏱️ Command on Cooldown",
                description=f"Please wait {error.retry_after:.2f} seconds before using this command again.",
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc)
            )
        else:
            logger.error(f"Unhandled error: {traceback.format_exception(type(error), error, error.__traceback__)}")
            embed = discord.Embed(
                title="❌ Unexpected Error",
                description="An unexpected error occurred. The incident has been logged.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
        
        if responded:
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
    except Exception as send_error:
        logger.error(f"Failed to send error message: {send_error}")

# --- MODERATION COMMANDS ---
class Moderation(app_commands.Group):
    """Moderation commands for managing server members"""
    
    def __init__(self, bot: TiltBot):
        super().__init__(name="mod", description="Moderation commands")
        self.bot = bot
    
    @app_commands.command(name="kick", description="Kick a member from server")
    @app_commands.describe(member="Member to kick", reason="Reason for kick")
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        if member == interaction.user:
            return await interaction.response.send_message("❌ You cannot kick yourself!", ephemeral=True)
        
        if member.top_role >= interaction.user.top_role:
            return await interaction.response.send_message("❌ You cannot kick someone with equal or higher role!", ephemeral=True)
        
        try:
            await member.kick(reason=f"{reason} | Kicked by {interaction.user}")
            
            embed = discord.Embed(
                title="✅ Member Kicked",
                description=f"**{member}** has been kicked",
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_footer(text=f"Kicked by {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"{interaction.user} kicked {member} for: {reason}")
            
        except Exception as e:
            logger.error(f"Error in kick command: {e}")
            await interaction.response.send_message("❌ Failed to kick member. Check permissions.", ephemeral=True)
    
    @app_commands.command(name="ban", description="Ban a member from server")
    @app_commands.describe(member="Member to ban", reason="Reason for ban", delete_days="Days of messages to delete (0-7)")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided", delete_days: app_commands.Range[int, 0, 7] = 0):
        if member == interaction.user:
            return await interaction.response.send_message("❌ You cannot ban yourself!", ephemeral=True)
        
        if member.top_role >= interaction.user.top_role:
            return await interaction.response.send_message("❌ You cannot ban someone with equal or higher role!", ephemeral=True)
        
        try:
            await member.ban(reason=f"{reason} | Banned by {interaction.user}", delete_message_days=delete_days)
            
            embed = discord.Embed(
                title="🔨 Member Banned",
                description=f"**{member}** has been banned",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            if delete_days > 0:
                embed.add_field(name="Messages Deleted", value=f"Last {delete_days} day(s)", inline=True)
            embed.set_footer(text=f"Banned by {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"{interaction.user} banned {member} for: {reason}")
            
        except Exception as e:
            logger.error(f"Error in ban command: {e}")
            await interaction.response.send_message("❌ Failed to ban member. Check permissions.", ephemeral=True)
    
    @app_commands.command(name="unban", description="Unban a member")
    @app_commands.describe(user_id="User ID to unban", reason="Reason for unban")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
        try:
            user = await self.bot.fetch_user(int(user_id))
            await interaction.guild.unban(user, reason=f"{reason} | Unbanned by {interaction.user}")
            
            embed = discord.Embed(
                title="✅ Member Unbanned",
                description=f"**{user}** has been unbanned",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_footer(text=f"Unbanned by {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"{interaction.user} unbanned {user} for: {reason}")
            
        except Exception as e:
            logger.error(f"Error in unban command: {e}")
            await interaction.response.send_message("❌ Failed to unban user. Check the user ID.", ephemeral=True)
    
    @app_commands.command(name="timeout", description="Timeout a member")
    @app_commands.describe(member="Member to timeout", minutes="Minutes to timeout", reason="Reason for timeout")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided"):
        if member == interaction.user:
            return await interaction.response.send_message("❌ You cannot timeout yourself!", ephemeral=True)
        
        if minutes > 40320:  # Discord's 28-day limit
            return await interaction.response.send_message("❌ Timeout cannot exceed 28 days (40320 minutes)!", ephemeral=True)
        
        try:
            duration = timedelta(minutes=minutes)
            await member.timeout(duration, reason=f"{reason} | Timed out by {interaction.user}")
            
            embed = discord.Embed(
                title="⏰ Member Timed Out",
                description=f"**{member}** has been timed out for {minutes} minutes",
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_footer(text=f"Timed out by {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"{interaction.user} timed out {member} for {minutes} minutes: {reason}")
            
        except Exception as e:
            logger.error(f"Error in timeout command: {e}")
            await interaction.response.send_message("❌ Failed to timeout member. Check permissions.", ephemeral=True)
    
    @app_commands.command(name="clear", description="Clear messages from channel")
    @app_commands.describe(amount="Number of messages to delete (1-100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
        await interaction.response.defer(ephemeral=True)
        
        try:
            deleted = await interaction.channel.purge(limit=amount)
            
            embed = discord.Embed(
                title="🧹 Messages Cleared",
                description=f"Successfully deleted **{len(deleted)}** message(s)",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text=f"Cleared by {interaction.user.display_name}")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"{interaction.user} cleared {len(deleted)} messages in {interaction.channel.name}")
            
        except Exception as e:
            logger.error(f"Error in clear command: {e}")
            await interaction.followup.send("❌ Failed to clear messages. Check permissions.", ephemeral=True)
    
    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.describe(member="Member to warn", reason="Reason for warning")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        if member == interaction.user:
            return await interaction.response.send_message("❌ You cannot warn yourself!", ephemeral=True)
        
        try:
            conn = sqlite3.connect('tilt_bot.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO warnings (user_id, guild_id, moderator_id, reason)
                VALUES (?, ?, ?, ?)
            ''', (member.id, interaction.guild.id, interaction.user.id, reason))
            
            conn.commit()
            
            # Get warning count
            cursor.execute('''
                SELECT COUNT(*) FROM warnings 
                WHERE user_id = ? AND guild_id = ?
            ''', (member.id, interaction.guild.id))
            
            warning_count = cursor.fetchone()[0]
            conn.close()
            
            embed = discord.Embed(
                title="⚠️ Member Warned",
                description=f"**{member}** has been warned",
                color=discord.Color.yellow(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Total Warnings", value=str(warning_count), inline=True)
            embed.set_footer(text=f"Warned by {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"{interaction.user} warned {member} for: {reason}")
            
        except Exception as e:
            logger.error(f"Error in warn command: {e}")
            await interaction.response.send_message("❌ Failed to warn member.", ephemeral=True)
    
    @app_commands.command(name="warnings", description="View warnings for a member")
    @app_commands.describe(member="Member to check warnings for")
    async def warnings(self, interaction: discord.Interaction, member: discord.Member = None):
        if member is None:
            member = interaction.user
        
        try:
            conn = sqlite3.connect('tilt_bot.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT reason, moderator_id, timestamp FROM warnings 
                WHERE user_id = ? AND guild_id = ?
                ORDER BY timestamp DESC
                LIMIT 10
            ''', (member.id, interaction.guild.id))
            
            warnings = cursor.fetchall()
            conn.close()
            
            embed = discord.Embed(
                title=f"⚠️ Warnings for {member.display_name}",
                color=discord.Color.yellow(),
                timestamp=datetime.now(timezone.utc)
            )
            
            if not warnings:
                embed.description = "No warnings found."
            else:
                embed.description = f"Showing last {len(warnings)} warning(s):"
                
                for i, (reason, mod_id, timestamp) in enumerate(warnings, 1):
                    try:
                        moderator = self.bot.get_user(mod_id) or await self.bot.fetch_user(mod_id)
                        mod_name = moderator.display_name
                    except:
                        mod_name = "Unknown Moderator"
                    
                    embed.add_field(
                        name=f"Warning #{i}",
                        value=f"**Reason:** {reason}\n**Moderator:** {mod_name}\n**Date:** <t:{int(datetime.fromisoformat(timestamp).timestamp())}:f>",
                        inline=False
                    )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in warnings command: {e}")
            await interaction.response.send_message("❌ Failed to fetch warnings.", ephemeral=True)
    
    @app_commands.command(name="lock", description="Lock a channel")
    @app_commands.describe(channel="Channel to lock (defaults to current)")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        if channel is None:
            channel = interaction.channel
        
        try:
            overwrite = channel.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = False
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
            
            embed = discord.Embed(
                title="🔒 Channel Locked",
                description=f"{channel.mention} has been locked",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text=f"Locked by {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"{interaction.user} locked {channel.name}")
            
        except Exception as e:
            logger.error(f"Error in lock command: {e}")
            await interaction.response.send_message("❌ Failed to lock channel. Check permissions.", ephemeral=True)
    
    @app_commands.command(name="unlock", description="Unlock a channel")
    @app_commands.describe(channel="Channel to unlock (defaults to current)")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        if channel is None:
            channel = interaction.channel
        
        try:
            overwrite = channel.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = None
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
            
            embed = discord.Embed(
                title="🔓 Channel Unlocked",
                description=f"{channel.mention} has been unlocked",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text=f"Unlocked by {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"{interaction.user} unlocked {channel.name}")
            
        except Exception as e:
            logger.error(f"Error in unlock command: {e}")
            await interaction.response.send_message("❌ Failed to unlock channel. Check permissions.", ephemeral=True)

# --- UTILITY COMMANDS ---
class Utility(app_commands.Group):
    """Utility and information commands"""
    
    def __init__(self, bot: TiltBot):
        super().__init__(name="utility", description="Utility and information commands")
        self.bot = bot
    
    @app_commands.command(name="help", description="Show all available commands")
    @app_commands.describe(category="Choose a specific category", command="Get help for specific command")
    async def help(self, interaction: discord.Interaction, category: Optional[str] = None, command: Optional[str] = None):
        if command:
            # Show specific command help
            embed = discord.Embed(
                title=f"ℹ️ Command Help: {command}",
                description="Detailed information about this command",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🤖 Tilt-bot Help",
            description="Complete all-in-one Discord bot with moderation, utility, fun, and more!",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="🛡️ Moderation",
            value="`/mod kick` `/mod ban` `/mod unban` `/mod timeout` `/mod clear` `/mod warn` `/mod warnings` `/mod lock` `/mod unlock`",
            inline=False
        )
        
        embed.add_field(
            name="🔧 Utility",
            value="`/utility help` `/utility serverinfo` `/utility userinfo` `/utility roleinfo` `/utility avatar` `/utility membercount` `/utility ping` `/utility botinfo` `/utility emojis` `/utility invite`",
            inline=False
        )
        
        embed.add_field(
            name="🎉 Fun",
            value="`/fun coinflip` `/fun dice` `/fun 8ball` `/fun meme` `/fun joke` `/fun quote` `/fun gif` `/fun weather` `/fun poll` `/fun suggest`",
            inline=False
        )
        
        embed.add_field(
            name="🎵 Music",
            value="`/music play` `/music pause` `/music resume` `/music skip` `/music queue` `/music stop` `/music lyrics`",
            inline=False
        )
        
        embed.add_field(
            name="📊 Admin",
            value="`/admin log` `/admin modlogs` `/admin audit` `/admin report`",
            inline=False
        )
        
        embed.add_field(
            name="🏆 Levels",
            value="`/levels level` `/levels leaderboard`",
            inline=False
        )
        
        embed.add_field(
            name="🎫 Tickets",
            value="`/tickets ticket` `/tickets closeticket`",
            inline=False
        )
        
        embed.add_field(
            name="⚙️ Config",
            value="`/config welcome` `/config goodbye` `/config autorole`",
            inline=False
        )
        
        embed.set_footer(text="Use /utility help command:<name> for specific command help")
        
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="serverinfo", description="View server statistics")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        
        embed = discord.Embed(
            title=f"📊 {guild.name}",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        embed.add_field(name="🆔 Server ID", value=guild.id, inline=True)
        embed.add_field(name="👑 Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="📅 Created", value=f"<t:{int(guild.created_at.timestamp())}:F>", inline=True)
        embed.add_field(name="👥 Members", value=f"{guild.member_count:,}", inline=True)
        embed.add_field(name="💬 Text Channels", value=len(guild.text_channels), inline=True)
        embed.add_field(name="🔊 Voice Channels", value=len(guild.voice_channels), inline=True)
        embed.add_field(name="🎭 Roles", value=len(guild.roles), inline=True)
        embed.add_field(name="😀 Emojis", value=len(guild.emojis), inline=True)
        embed.add_field(name="📈 Boost Level", value=f"Level {guild.premium_tier}", inline=True)
        
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")
        
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="userinfo", description="View information about a user")
    @app_commands.describe(member="User to get information about")
    async def userinfo(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        if member is None:
            member = interaction.user
        
        embed = discord.Embed(
            title=f"👤 {member.display_name}",
            description=f"Information about {member.mention}",
            color=member.color if member.color != discord.Color.default() else discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        
        embed.add_field(name="🆔 User ID", value=member.id, inline=True)
        embed.add_field(name="🏷️ Username", value=f"{member.name}#{member.discriminator}", inline=True)
        embed.add_field(name="📅 Account Created", value=f"<t:{int(member.created_at.timestamp())}:F>", inline=False)
        
        if hasattr(member, 'joined_at') and member.joined_at:
            embed.add_field(name="📥 Joined Server", value=f"<t:{int(member.joined_at.timestamp())}:F>", inline=False)
        
        roles = [role.mention for role in member.roles[1:]]
        if roles:
            roles_text = ", ".join(roles[:10])
            if len(roles) > 10:
                roles_text += f" and {len(roles) - 10} more..."
            embed.add_field(name=f"🎭 Roles ({len(roles)})", value=roles_text, inline=False)
        else:
            embed.add_field(name="🎭 Roles", value="No roles", inline=False)
        
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")
        
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="roleinfo", description="View information about a role")
    @app_commands.describe(role="Role to get information about")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        embed = discord.Embed(
            title=f"🎭 Role: {role.name}",
            color=role.color if role.color != discord.Color.default() else discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(name="🆔 Role ID", value=role.id, inline=True)
        embed.add_field(name="👥 Members", value=len(role.members), inline=True)
        embed.add_field(name="📅 Created", value=f"<t:{int(role.created_at.timestamp())}:F>", inline=True)
        embed.add_field(name="🎨 Color", value=str(role.color), inline=True)
        embed.add_field(name="📍 Position", value=role.position, inline=True)
        embed.add_field(name="🔒 Mentionable", value="Yes" if role.mentionable else "No", inline=True)
        
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="avatar", description="Get user avatar")
    @app_commands.describe(member="User to get avatar from")
    async def avatar(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        if member is None:
            member = interaction.user
        
        embed = discord.Embed(
            title=f"🖼️ {member.display_name}'s Avatar",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
        embed.set_image(url=avatar_url)
        embed.add_field(name="Download", value=f"[Click here]({avatar_url})", inline=True)
        
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="membercount", description="Show member count")
    async def membercount(self, interaction: discord.Interaction):
        guild = interaction.guild
        
        embed = discord.Embed(
            title="👥 Member Count",
            description=f"**{guild.name}** has **{guild.member_count:,}** members",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="ping", description="Show bot latency")
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        
        if latency < 100:
            quality = "🟢 Excellent"
            color = discord.Color.green()
        elif latency < 200:
            quality = "🟡 Good"
            color = discord.Color.yellow()
        else:
            quality = "🔴 Poor"
            color = discord.Color.red()
        
        embed = discord.Embed(
            title="🏓 Pong!",
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Latency", value=f"{latency}ms", inline=True)
        embed.add_field(name="Quality", value=quality, inline=True)
        
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="botinfo", description="Information about the bot")
    async def botinfo(self, interaction: discord.Interaction):
        uptime = datetime.now(timezone.utc) - self.bot.start_time
        
        embed = discord.Embed(
            title="🤖 Tilt-bot Information",
            description="Complete all-in-one Discord bot",
            color=discord.Color.purple(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else self.bot.user.default_avatar.url)
        
        embed.add_field(name="📊 Statistics", value=f"**Servers:** {len(self.bot.guilds)}\n**Commands Used:** {self.bot.commands_used:,}", inline=True)
        embed.add_field(name="⏱️ Uptime", value=f"{uptime.days}d {uptime.seconds//3600}h {(uptime.seconds//60)%60}m", inline=True)
        embed.add_field(name="🏓 Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        embed.add_field(name="🔧 Built With", value="discord.py 2.0+\nPython 3.8+", inline=True)
        embed.add_field(name="💻 Version", value="3.0.0", inline=True)
        embed.add_field(name="📅 Created", value="2025", inline=True)
        
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="emojis", description="List server emojis")
    async def emojis(self, interaction: discord.Interaction):
        guild = interaction.guild
        
        if not guild.emojis:
            embed = discord.Embed(
                title="😀 Server Emojis",
                description="This server has no custom emojis.",
                color=discord.Color.blue()
            )
        else:
            emoji_list = [str(emoji) for emoji in guild.emojis[:50]]  # Limit to 50
            
            embed = discord.Embed(
                title=f"😀 Server Emojis ({len(guild.emojis)})",
                description=" ".join(emoji_list),
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            if len(guild.emojis) > 50:
                embed.set_footer(text=f"Showing first 50 of {len(guild.emojis)} emojis")
        
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="invite", description="Get bot invite link")
    async def invite(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🔗 Invite Tilt-bot",
            description="Click the link below to invite me to your server!",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        invite_url = f"https://discord.com/api/oauth2/authorize?client_id={self.bot.user.id}&permissions=8&scope=bot%20applications.commands"
        embed.add_field(name="Invite Link", value=f"[Click here to invite]({invite_url})", inline=False)
        
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1

# --- FUN COMMANDS ---
class Fun(app_commands.Group):
    """Fun and entertainment commands"""
    
    def __init__(self, bot: TiltBot):
        super().__init__(name="fun", description="Fun and entertainment commands")
        self.bot = bot
    
    @app_commands.command(name="coinflip", description="Flip a coin")
    async def coinflip(self, interaction: discord.Interaction):
        result = random.choice(['Heads', 'Tails'])
        emoji = "🪙" if result == "Heads" else "⚫"
        
        embed = discord.Embed(
            title=f"{emoji} Coin Flip",
            description=f"The coin landed on: **{result}**!",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="dice", description="Roll a dice")
    @app_commands.describe(sides="Number of sides on the dice (default: 6)")
    async def dice(self, interaction: discord.Interaction, sides: int = 6):
        if sides < 2:
            return await interaction.response.send_message("❌ Dice must have at least 2 sides!", ephemeral=True)
        
        result = random.randint(1, sides)
        
        embed = discord.Embed(
            title="🎲 Dice Roll",
            description=f"You rolled a **{result}** on a {sides}-sided dice!",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="8ball", description="Ask the magic 8-ball a question")
    @app_commands.describe(question="Your question for the 8-ball")
    async def eightball(self, interaction: discord.Interaction, question: str):
        responses = [
            "It is certain", "It is decidedly so", "Without a doubt", "Yes definitely",
            "You may rely on it", "As I see it, yes", "Most likely", "Outlook good",
            "Yes", "Signs point to yes", "Reply hazy, try again", "Ask again later",
            "Better not tell you now", "Cannot predict now", "Concentrate and ask again",
            "Don't count on it", "My reply is no", "My sources say no",
            "Outlook not so good", "Very doubtful"
        ]
        
        answer = random.choice(responses)
        
        embed = discord.Embed(
            title="🎱 Magic 8-Ball",
            color=discord.Color.purple(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Question", value=question, inline=False)
        embed.add_field(name="Answer", value=answer, inline=False)
        
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="meme", description="Get a random meme (placeholder)")
    async def meme(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="😂 Random Meme",
            description="Meme functionality coming soon! This would fetch memes from an API.",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="joke", description="Get a random joke")
    async def joke(self, interaction: discord.Interaction):
        jokes = [
            "Why don't scientists trust atoms? Because they make up everything!",
            "Why did the scarecrow win an award? He was outstanding in his field!",
            "Why don't eggs tell jokes? They'd crack each other up!",
            "What do you call a fake noodle? An impasta!",
            "Why did the math book look so sad? Because it had too many problems!"
        ]
        
        joke = random.choice(jokes)
        
        embed = discord.Embed(
            title="😄 Random Joke",
            description=joke,
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="quote", description="Get a random inspirational quote")
    async def quote(self, interaction: discord.Interaction):
        quotes = [
            "The only way to do great work is to love what you do. - Steve Jobs",
            "Innovation distinguishes between a leader and a follower. - Steve Jobs",
            "Life is what happens to you while you're busy making other plans. - John Lennon",
            "The future belongs to those who believe in the beauty of their dreams. - Eleanor Roosevelt",
            "It is during our darkest moments that we must focus to see the light. - Aristotle"
        ]
        
        quote = random.choice(quotes)
        
        embed = discord.Embed(
            title="💭 Inspirational Quote",
            description=quote,
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="gif", description="Search for a GIF (placeholder)")
    @app_commands.describe(query="Search term for GIF")
    async def gif(self, interaction: discord.Interaction, query: str):
        embed = discord.Embed(
            title="🎬 GIF Search",
            description=f"GIF search for '{query}' coming soon! This would use Giphy API.",
            color=discord.Color.purple(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="weather", description="Get weather information (placeholder)")
    @app_commands.describe(location="Location to get weather for")
    async def weather(self, interaction: discord.Interaction, location: str):
        embed = discord.Embed(
            title="🌤️ Weather",
            description=f"Weather for '{location}' coming soon! This would use a weather API.",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="poll", description="Create a simple poll")
    @app_commands.describe(question="Poll question", option1="First option", option2="Second option")
    async def poll(self, interaction: discord.Interaction, question: str, option1: str, option2: str):
        embed = discord.Embed(
            title="📊 Poll",
            description=question,
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="🇦 Option A", value=option1, inline=True)
        embed.add_field(name="🇧 Option B", value=option2, inline=True)
        embed.set_footer(text=f"Poll by {interaction.user.display_name}")
        
        message = await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()
        await message.add_reaction("🇦")
        await message.add_reaction("🇧")
        
        self.bot.commands_used += 1
    
    @app_commands.command(name="suggest", description="Submit a suggestion")
    @app_commands.describe(suggestion="Your suggestion")
    async def suggest(self, interaction: discord.Interaction, suggestion: str):
        embed = discord.Embed(
            title="💡 Suggestion",
            description=suggestion,
            color=discord.Color.yellow(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        
        message = await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()
        await message.add_reaction("👍")
        await message.add_reaction("👎")
        
        self.bot.commands_used += 1

# --- MUSIC COMMANDS (Placeholder) ---
class Music(app_commands.Group):
    """Music commands (placeholder implementation)"""
    
    def __init__(self, bot: TiltBot):
        super().__init__(name="music", description="Music commands")
        self.bot = bot
    
    @app_commands.command(name="play", description="Play a song (placeholder)")
    @app_commands.describe(query="Song to play")
    async def play(self, interaction: discord.Interaction, query: str):
        embed = discord.Embed(
            title="🎵 Music Player",
            description=f"Music functionality coming soon!\nWould play: '{query}'",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="pause", description="Pause current song (placeholder)")
    async def pause(self, interaction: discord.Interaction):
        await interaction.response.send_message("⏸️ Music paused (placeholder)")
        self.bot.commands_used += 1
    
    @app_commands.command(name="resume", description="Resume playback (placeholder)")
    async def resume(self, interaction: discord.Interaction):
        await interaction.response.send_message("▶️ Music resumed (placeholder)")
        self.bot.commands_used += 1
    
    @app_commands.command(name="skip", description="Skip current song (placeholder)")
    async def skip(self, interaction: discord.Interaction):
        await interaction.response.send_message("⏭️ Song skipped (placeholder)")
        self.bot.commands_used += 1
    
    @app_commands.command(name="queue", description="View music queue (placeholder)")
    async def queue(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎵 Music Queue",
            description="Queue is empty (placeholder)",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="stop", description="Stop music and leave voice (placeholder)")
    async def stop(self, interaction: discord.Interaction):
        await interaction.response.send_message("⏹️ Music stopped (placeholder)")
        self.bot.commands_used += 1
    
    @app_commands.command(name="lyrics", description="Get song lyrics (placeholder)")
    @app_commands.describe(song="Song to get lyrics for")
    async def lyrics(self, interaction: discord.Interaction, song: str):
        embed = discord.Embed(
            title="🎤 Song Lyrics",
            description=f"Lyrics for '{song}' coming soon!",
            color=discord.Color.purple()
        )
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1

# --- ADMIN/LOGGING COMMANDS ---
class Admin(app_commands.Group):
    """Admin and logging commands"""
    
    def __init__(self, bot: TiltBot):
        super().__init__(name="admin", description="Admin and logging commands")
        self.bot = bot
    
    @app_commands.command(name="log", description="View moderation logs (placeholder)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def log(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📋 Moderation Logs",
            description="Advanced logging system coming soon!",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="modlogs", description="Show user's moderation logs")
    @app_commands.describe(member="Member to check logs for")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def modlogs(self, interaction: discord.Interaction, member: discord.Member):
        embed = discord.Embed(
            title=f"📋 Mod Logs for {member.display_name}",
            description="Detailed mod logs coming soon!",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="audit", description="View audit log (placeholder)")
    @app_commands.checks.has_permissions(view_audit_log=True)
    async def audit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🔍 Audit Log",
            description="Audit log viewer coming soon!",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        self.bot.commands_used += 1
    
    @app_commands.command(name="report", description="Report a member")
    @app_commands.describe(member="Member to report", reason="Reason for report")
    async def report(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        embed = discord.Embed(
            title="📝 Report Submitted",
            description=f"Report against {member.mention} has been submitted to moderators.",
            color=discord.Color.yellow(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_footer(text=f"Reported by {interaction.user.display_name}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        self.bot.commands_used += 1

# --- LEVELS/XP COMMANDS ---
class Levels(app_commands.Group):
    """Level and XP system commands"""
    
    def __init__(self, bot: TiltBot):
        super().__init__(name="levels", description="Level and XP system")
        self.bot = bot
    
    @app_commands.command(name="level", description="Check user XP/level")
    @app_commands.describe(member="Member to check level for")
    async def level(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        if member is None:
            member = interaction.user
        
        try:
            conn = sqlite3.connect('tilt_bot.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT xp, level FROM user_xp 
                WHERE user_id = ? AND guild_id = ?
            ''', (member.id, interaction.guild.id))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                xp, level = result
            else:
                xp, level = 0, 1
            
            embed = discord.Embed(
                title=f"🏆 Level Info for {member.display_name}",
                color=discord.Color.gold(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Level", value=str(level), inline=True)
            embed.add_field(name="XP", value=f"{xp:,}", inline=True)
            embed.add_field(name="Next Level", value=f"{((level + 1) * 100) - xp:,} XP needed", inline=True)
            embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
            
            await interaction.response.send_message(embed=embed)
            self.bot.commands_used += 1
            
        except Exception as e:
            logger.error(f"Error in level command: {e}")
            await interaction.response.send_message("❌ Failed to fetch level information.", ephemeral=True)
    
    @app_commands.command(name="leaderboard", description="Show server leaderboard")
    async def leaderboard(self, interaction: discord.Interaction):
        try:
            conn = sqlite3.connect('tilt_bot.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT user_id, xp, level FROM user_xp 
                WHERE guild_id = ?
                ORDER BY level DESC, xp DESC
                LIMIT 10
            ''', (interaction.guild.id,))
            
            results = cursor.fetchall()
            conn.close()
            
            embed = discord.Embed(
                title=f"🏆 {interaction.guild.name} Leaderboard",
                color=discord.Color.gold(),
                timestamp=datetime.now(timezone.utc)
            )
            
            if not results:
                embed.description = "No XP data found. Start chatting to gain XP!"
            else:
                leaderboard_text = ""
                for i, (user_id, xp, level) in enumerate(results, 1):
                    user = self.bot.get_user(user_id)
                    if user:
                        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                        leaderboard_text += f"{medal} **{user.display_name}** - Level {level} ({xp:,} XP)\n"
                
                embed.description = leaderboard_text
            
            await interaction.response.send_message(embed=embed)
            self.bot.commands_used += 1
            
        except Exception as e:
            logger.error(f"Error in leaderboard command: {e}")
            await interaction.response.send_message("❌ Failed to fetch leaderboard.", ephemeral=True)

# --- TICKET SYSTEM ---
class Tickets(app_commands.Group):
    """Ticket system commands"""
    
    def __init__(self, bot: TiltBot):
        super().__init__(name="tickets", description="Support ticket system")
        self.bot = bot
    
    @app_commands.command(name="ticket", description="Create a support ticket")
    @app_commands.describe(reason="Reason for creating ticket")
    async def ticket(self, interaction: discord.Interaction, reason: str = "General support"):
        try:
            guild = interaction.guild
            category = discord.utils.get(guild.categories, name="Tickets")
            
            if not category:
                category = await guild.create_category("Tickets")
            
            # Create ticket channel
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
            }
            
            channel_name = f"ticket-{interaction.user.name.lower()}-{random.randint(1000, 9999)}"
            ticket_channel = await category.create_text_channel(
                name=channel_name,
                overwrites=overwrites
            )
            
            # Add to database
            conn = sqlite3.connect('tilt_bot.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO tickets (channel_id, user_id, guild_id)
                VALUES (?, ?, ?)
            ''', (ticket_channel.id, interaction.user.id, guild.id))
            conn.commit()
            conn.close()
            
            # Create ticket embed
            embed = discord.Embed(
                title="🎫 Support Ticket Created",
                description=f"Ticket created: {ticket_channel.mention}",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Send welcome message in ticket
            welcome_embed = discord.Embed(
                title="🎫 Support Ticket",
                description=f"Hello {interaction.user.mention}! Support will be with you shortly.",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            welcome_embed.add_field(name="Reason", value=reason, inline=False)
            welcome_embed.add_field(name="Close Ticket", value="Use `/tickets closeticket` to close this ticket.", inline=False)
            
            await ticket_channel.send(embed=welcome_embed)
            
            logger.info(f"Ticket created by {interaction.user} in {guild.name}: {reason}")
            self.bot.commands_used += 1
            
        except Exception as e:
            logger.error(f"Error creating ticket: {e}")
            await interaction.response.send_message("❌ Failed to create ticket. Please try again.", ephemeral=True)
    
    @app_commands.command(name="closeticket", description="Close a support ticket")
    @app_commands.describe(reason="Reason for closing ticket")
    async def closeticket(self, interaction: discord.Interaction, reason: str = "Resolved"):
        try:
            # Check if this is a ticket channel
            conn = sqlite3.connect('tilt_bot.db')
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id FROM tickets 
                WHERE channel_id = ? AND status = 'open'
            ''', (interaction.channel.id,))
            
            result = cursor.fetchone()
            
            if not result:
                await interaction.response.send_message("❌ This is not a ticket channel or the ticket is already closed.", ephemeral=True)
                return
            
            ticket_owner_id = result[0]
            
            # Check permissions
            if (interaction.user.id != ticket_owner_id and 
                not interaction.user.guild_permissions.manage_channels):
                await interaction.response.send_message("❌ You can only close your own tickets or need Manage Channels permission.", ephemeral=True)
                return
            
            # Update database
            cursor.execute('''
                UPDATE tickets SET status = 'closed' 
                WHERE channel_id = ?
            ''', (interaction.channel.id,))
            conn.commit()
            conn.close()
            
            # Send closing message
            embed = discord.Embed(
                title="🎫 Ticket Closing",
                description=f"This ticket will be deleted in 10 seconds.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Closed by", value=interaction.user.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=True)
            
            await interaction.response.send_message(embed=embed)
            
            # Wait and delete
            await asyncio.sleep(10)
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}: {reason}")
            
            logger.info(f"Ticket closed by {interaction.user}: {reason}")
            self.bot.commands_used += 1
            
        except Exception as e:
            logger.error(f"Error closing ticket: {e}")
            await interaction.response.send_message("❌ Failed to close ticket.", ephemeral=True)

# --- CONFIGURATION COMMANDS ---
class Config(app_commands.Group):
    """Server configuration commands"""
    
    def __init__(self, bot: TiltBot):
        super().__init__(name="config", description="Server configuration commands")
        self.bot = bot
    
    @app_commands.command(name="welcome", description="Configure welcome messages")
    @app_commands.describe(channel="Welcome channel", message="Welcome message")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str = None):
        try:
            conn = sqlite3.connect('tilt_bot.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO server_config (guild_id, welcome_channel, welcome_message)
                VALUES (?, ?, ?)
            ''', (interaction.guild.id, channel.id, message or "Welcome to the server, {user}!"))
            
            conn.commit()
            conn.close()
            
            embed = discord.Embed(
                title="✅ Welcome Configured",
                description=f"Welcome messages will be sent to {channel.mention}",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            
            if message:
                embed.add_field(name="Message", value=message, inline=False)
            
            await interaction.response.send_message(embed=embed)
            self.bot.commands_used += 1
            
        except Exception as e:
            logger.error(f"Error configuring welcome: {e}")
            await interaction.response.send_message("❌ Failed to configure welcome messages.", ephemeral=True)
    
    @app_commands.command(name="goodbye", description="Configure goodbye messages")
    @app_commands.describe(channel="Goodbye channel", message="Goodbye message")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def goodbye(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str = None):
        try:
            conn = sqlite3.connect('tilt_bot.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO server_config (guild_id, goodbye_channel, goodbye_message)
                VALUES (?, ?, ?)
            ''', (interaction.guild.id, channel.id, message or "Goodbye, {user}!"))
            
            conn.commit()
            conn.close()
            
            embed = discord.Embed(
                title="✅ Goodbye Configured",
                description=f"Goodbye messages will be sent to {channel.mention}",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            
            if message:
                embed.add_field(name="Message", value=message, inline=False)
            
            await interaction.response.send_message(embed=embed)
            self.bot.commands_used += 1
            
        except Exception as e:
            logger.error(f"Error configuring goodbye: {e}")
            await interaction.response.send_message("❌ Failed to configure goodbye messages.", ephemeral=True)
    
    @app_commands.command(name="autorole", description="Set auto-role for new members")
    @app_commands.describe(role="Role to give new members")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def autorole(self, interaction: discord.Interaction, role: discord.Role):
        try:
            conn = sqlite3.connect('tilt_bot.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO server_config (guild_id, autorole)
                VALUES (?, ?)
            ''', (interaction.guild.id, role.id))
            
            conn.commit()
            conn.close()
            
            embed = discord.Embed(
                title="✅ Auto-role Configured",
                description=f"New members will automatically receive the {role.mention} role",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            
            await interaction.response.send_message(embed=embed)
            self.bot.commands_used += 1
            
        except Exception as e:
            logger.error(f"Error configuring autorole: {e}")
            await interaction.response.send_message("❌ Failed to configure auto-role.", ephemeral=True)

# --- EVENT HANDLERS ---
@bot.event
async def on_member_join(member):
    """Handle member join events"""
    try:
        conn = sqlite3.connect('tilt_bot.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT welcome_channel, welcome_message, autorole FROM server_config 
            WHERE guild_id = ?
        ''', (member.guild.id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            welcome_channel_id, welcome_message, autorole_id = result
            
            # Send welcome message
            if welcome_channel_id:
                channel = member.guild.get_channel(welcome_channel_id)
                if channel:
                    message = welcome_message.replace("{user}", member.mention)
                    
                    embed = discord.Embed(
                        title="🎉 Welcome!",
                        description=message,
                        color=discord.Color.green(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
                    embed.add_field(name="Member Count", value=f"You're member #{member.guild.member_count}!", inline=False)
                    
                    await channel.send(embed=embed)
            
            # Give auto-role
            if autorole_id:
                role = member.guild.get_role(autorole_id)
                if role:
                    await member.add_roles(role, reason="Auto-role")
        
        logger.info(f"Member joined: {member} in {member.guild.name}")
        
    except Exception as e:
        logger.error(f"Error in member join event: {e}")

@bot.event
async def on_member_remove(member):
    """Handle member leave events"""
    try:
        conn = sqlite3.connect('tilt_bot.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT goodbye_channel, goodbye_message FROM server_config 
            WHERE guild_id = ?
        ''', (member.guild.id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            goodbye_channel_id, goodbye_message = result
            
            if goodbye_channel_id:
                channel = member.guild.get_channel(goodbye_channel_id)
                if channel:
                    message = goodbye_message.replace("{user}", str(member))
                    
                    embed = discord.Embed(
                        title="👋 Goodbye",
                        description=message,
                        color=discord.Color.orange(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
                    
                    await channel.send(embed=embed)
        
        logger.info(f"Member left: {member} from {member.guild.name}")
        
    except Exception as e:
        logger.error(f"Error in member remove event: {e}")

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    try:
        logger.info("Starting Tilt-bot All-in-One...")
        bot.run(BOT_TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested by user")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        traceback.print_exc()
    finally:
        logger.info("Tilt-bot has shut down")
