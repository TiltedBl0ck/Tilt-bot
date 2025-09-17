import os
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import psycopg2
from discord import app_commands
from datetime import datetime, timezone

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN or not DATABASE_URL:
    raise RuntimeError("BOT_TOKEN and DATABASE_URL must be set in environment variables")

# Database helper
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    conn.autocommit = True
    return conn

# Initialize database tables
def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS guild_config (
                    guild_id BIGINT PRIMARY KEY,
                    welcome_channel_id BIGINT,
                    goodbye_channel_id BIGINT,
                    stats_category_id BIGINT,
                    member_count_channel_id BIGINT,
                    bot_count_channel_id BIGINT,
                    role_count_channel_id BIGINT,
                    channel_count_channel_id BIGINT,
                    setup_complete BOOLEAN DEFAULT FALSE
                )
            """)

# Bot intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)

@bot.event
async def on_ready():
    init_db()
    print(f"{bot.user} is online — syncing commands…")
    await bot.tree.sync()
    print("Slash commands synced globally.")
    update_server_stats.start()

# Task to update server stats every 10 minutes
@tasks.loop(minutes=10)
async def update_server_stats():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT guild_id, member_count_channel_id, bot_count_channel_id, role_count_channel_id, channel_count_channel_id FROM guild_config WHERE setup_complete = TRUE")
                configs = cur.fetchall()
        
        for config in configs:
            guild_id, member_ch, bot_ch, role_ch, channel_ch = config
            guild = bot.get_guild(guild_id)
            if not guild:
                continue
                
            # Update member count
            if member_ch:
                channel = guild.get_channel(member_ch)
                if channel:
                    member_count = guild.member_count
                    try:
                        await channel.edit(name=f"👥 Members: {member_count}")
                    except:
                        pass
            
            # Update bot count
            if bot_ch:
                channel = guild.get_channel(bot_ch)
                if channel:
                    bot_count = sum(1 for member in guild.members if member.bot)
                    try:
                        await channel.edit(name=f"🤖 Bots: {bot_count}")
                    except:
                        pass
            
            # Update role count
            if role_ch:
                channel = guild.get_channel(role_ch)
                if channel:
                    role_count = len(guild.roles) - 1  # Exclude @everyone
                    try:
                        await channel.edit(name=f"📋 Roles: {role_count}")
                    except:
                        pass
            
            # Update channel count
            if channel_ch:
                channel = guild.get_channel(channel_ch)
                if channel:
                    channel_count = len(guild.channels)
                    try:
                        await channel.edit(name=f"📺 Channels: {channel_count}")
                    except:
                        pass
    except Exception as e:
        print(f"Error in update_server_stats: {e}")

# --- Utility Commands ---

@bot.tree.command(name="help", description="Show all available commands")
async def help_command(interaction: discord.Interaction):
    try:
        embed = discord.Embed(
            title="🤖 Tilt-bot Help",
            description="Here are the commands you can use:",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        # Utility Commands
        embed.add_field(
            name="📊 Utility Commands", 
            value="`/help` `/serverinfo` `/userinfo` `/roleinfo` `/avatar` `/membercount` `/ping` `/botinfo` `/emojis` `/invite`", 
            inline=False
        )
        
        # Moderation Commands
        embed.add_field(
            name="🛡️ Moderation Commands", 
            value="`/clear` - Clear messages (1-100)", 
            inline=False
        )
        
        # Server Stats Commands
        embed.add_field(
            name="📈 Server Stats Commands", 
            value="`/setup serverstats` - Create server stats\n`/config serverstats` - Manage server stats", 
            inline=False
        )
        
        # Configuration Commands
        embed.add_field(
            name="⚙️ Configuration Commands", 
            value="`/config welcome` `/config goodbye`", 
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message("❌ Error displaying help menu.", ephemeral=True)

@bot.tree.command(name="serverinfo", description="View server information")
async def serverinfo(interaction: discord.Interaction):
    try:
        g = interaction.guild
        embed = discord.Embed(
            title=g.name,
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        embed.add_field(name="Server ID", value=g.id, inline=True)
        embed.add_field(name="Owner", value=g.owner.mention if g.owner else "Unknown", inline=True)
        embed.add_field(name="Created", value=f"<t:{int(g.created_at.timestamp())}:F>", inline=True)
        embed.add_field(name="Members", value=g.member_count, inline=True)
        embed.add_field(name="Text Channels", value=len(g.text_channels), inline=True)
        embed.add_field(name="Voice Channels", value=len(g.voice_channels), inline=True)
        embed.add_field(name="Roles", value=len(g.roles), inline=True)
        bot_count = sum(1 for member in g.members if member.bot)
        embed.add_field(name="Bots", value=bot_count, inline=True)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message("❌ Error retrieving server information.", ephemeral=True)

@bot.tree.command(name="userinfo", description="View information about a user")
@discord.app_commands.describe(member="The member to lookup")
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    try:
        m = member or interaction.user
        embed = discord.Embed(
            title=m.display_name,
            color=m.color,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=m.avatar.url if m.avatar else m.default_avatar.url)
        embed.add_field(name="User ID", value=m.id, inline=True)
        embed.add_field(name="Username", value=str(m), inline=True)
        embed.add_field(name="Bot", value="Yes" if m.bot else "No", inline=True)
        embed.add_field(name="Account Created", value=f"<t:{int(m.created_at.timestamp())}:F>", inline=False)
        if m.joined_at:
            embed.add_field(name="Joined Server", value=f"<t:{int(m.joined_at.timestamp())}:F>", inline=False)
        roles = [r.mention for r in m.roles[1:]] or ["No roles"]
        embed.add_field(name=f"Roles ({len(m.roles)-1})", value=", ".join(roles), inline=False)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message("❌ Error retrieving user information.", ephemeral=True)

@bot.tree.command(name="roleinfo", description="View information about a role")
@discord.app_commands.describe(role="The role to lookup")
async def roleinfo(interaction: discord.Interaction, role: discord.Role):
    try:
        embed = discord.Embed(
            title=role.name,
            color=role.color,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Role ID", value=role.id, inline=True)
        embed.add_field(name="Members", value=len(role.members), inline=True)
        embed.add_field(name="Created", value=f"<t:{int(role.created_at.timestamp())}:F>", inline=True)
        embed.add_field(name="Position", value=role.position, inline=True)
        embed.add_field(name="Mentionable", value=str(role.mentionable), inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message("❌ Error retrieving role information.", ephemeral=True)

@bot.tree.command(name="avatar", description="Get a user's avatar")
@discord.app_commands.describe(member="The member whose avatar to show")
async def avatar(interaction: discord.Interaction, member: discord.Member = None):
    try:
        m = member or interaction.user
        embed = discord.Embed(
            title=f"{m.display_name}'s Avatar",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        url = m.avatar.url if m.avatar else m.default_avatar.url
        embed.set_image(url=url)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message("❌ Error retrieving avatar.", ephemeral=True)

@bot.tree.command(name="membercount", description="Show member count")
async def membercount(interaction: discord.Interaction):
    try:
        count = interaction.guild.member_count
        bot_count = sum(1 for member in interaction.guild.members if member.bot)
        human_count = count - bot_count
        await interaction.response.send_message(f"**{interaction.guild.name}** has **{count}** total members (**{human_count}** humans, **{bot_count}** bots).")
    except Exception as e:
        await interaction.response.send_message("❌ Error retrieving member count.", ephemeral=True)

@bot.tree.command(name="ping", description="Show bot latency")
async def ping(interaction: discord.Interaction):
    try:
        latency = round(bot.latency * 1000)
        await interaction.response.send_message(f"Pong! Latency is {latency}ms.")
    except Exception as e:
        await interaction.response.send_message("❌ Error checking ping.", ephemeral=True)

@bot.tree.command(name="botinfo", description="Information about the bot")
async def botinfo(interaction: discord.Interaction):
    try:
        embed = discord.Embed(
            title="Bot Info",
            color=discord.Color.purple(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Username", value=str(bot.user), inline=True)
        embed.add_field(name="ID", value=bot.user.id, inline=True)
        embed.add_field(name="Latency", value=f"{round(bot.latency*1000)}ms", inline=True)
        embed.add_field(name="Servers", value=len(bot.guilds), inline=True)
        total_members = sum(guild.member_count for guild in bot.guilds)
        embed.add_field(name="Total Members", value=total_members, inline=True)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message("❌ Error retrieving bot information.", ephemeral=True)

@bot.tree.command(name="emojis", description="List server emojis")
async def emojis(interaction: discord.Interaction):
    try:
        es = interaction.guild.emojis
        if not es:
            await interaction.response.send_message("This server has no custom emojis.")
        else:
            await interaction.response.send_message(" ".join(str(e) for e in es))
    except Exception as e:
        await interaction.response.send_message("❌ Error retrieving emojis.", ephemeral=True)

@bot.tree.command(name="invite", description="Get bot invite link")
async def invite(interaction: discord.Interaction):
    try:
        link = f"https://discord.com/oauth2/authorize?client_id={bot.user.id}&scope=bot%20applications.commands&permissions=268438528"
        await interaction.response.send_message(f"Invite me: {link}")
    except Exception as e:
        await interaction.response.send_message("❌ Error generating invite link.", ephemeral=True)

@bot.tree.command(name="clear", description="Clear recent messages")
@discord.app_commands.describe(count="Number of messages to delete (1–100)")
@discord.app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, count: int):
    try:
        if count < 1 or count > 100:
            await interaction.response.send_message("Count must be between 1 and 100.", ephemeral=True)
            return
        deleted = await interaction.channel.purge(limit=count)
        await interaction.response.send_message(f"✅ Deleted {len(deleted)} messages.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message("❌ Error clearing messages.", ephemeral=True)

# Setup group for serverstats
setup_group = app_commands.Group(name="setup", description="Setup commands for Tilt-bot")
bot.tree.add_command(setup_group)

@setup_group.command(name="serverstats", description="Create server stats category and basic counters")
@discord.app_commands.checks.has_permissions(administrator=True)
async def setup_serverstats(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        guild = interaction.guild
        guild_id = guild.id
        
        # Check if already setup
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT setup_complete FROM guild_config WHERE guild_id = %s", (guild_id,))
                row = cur.fetchone()
                if row and row[0]:
                    await interaction.followup.send("⚠️ Server stats are already set up. Use `/config serverstats` to manage them.", ephemeral=True)
                    return
        
        # Create stats category
        category = await guild.create_category("📊 Server Stats")
        
        # Create basic stat channels
        member_channel = await guild.create_voice_channel(f"👥 Members: {guild.member_count}", category=category)
        bot_count = sum(1 for member in guild.members if member.bot)
        bot_channel = await guild.create_voice_channel(f"🤖 Bots: {bot_count}", category=category)
        role_channel = await guild.create_voice_channel(f"📋 Roles: {len(guild.roles)-1}", category=category)
        
        # Save to database
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO guild_config (guild_id, stats_category_id, member_count_channel_id, bot_count_channel_id, role_count_channel_id, setup_complete)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (guild_id)
                    DO UPDATE SET 
                        stats_category_id = EXCLUDED.stats_category_id,
                        member_count_channel_id = EXCLUDED.member_count_channel_id,
                        bot_count_channel_id = EXCLUDED.bot_count_channel_id,
                        role_count_channel_id = EXCLUDED.role_count_channel_id,
                        setup_complete = EXCLUDED.setup_complete
                """, (guild.id, category.id, member_channel.id, bot_channel.id, role_channel.id, True))
        
        embed = discord.Embed(
            title="✅ Server Stats Setup Complete!",
            description=f"Created **{category.name}** category with basic server stats counters.",
            color=discord.Color.green()
        )
        embed.add_field(name="Created Channels", value=f"{member_channel.mention}\n{bot_channel.mention}\n{role_channel.mention}", inline=False)
        embed.add_field(name="Management", value="Use `/config serverstats` to manage these stats.", inline=False)
        await interaction.followup.send(embed=embed)
    except discord.Forbidden:
        await interaction.followup.send("❌ I don't have permission to create channels. Please ensure I have **Manage Channels** and **Connect** permissions.", ephemeral=True)
    except Exception as e:
        print(f"Error in setup_serverstats: {e}")
        await interaction.followup.send("❌ An unexpected error occurred during server stats setup.", ephemeral=True)

# Config group for welcome/goodbye and serverstats
config = app_commands.Group(name="config", description="Configure bot settings")
bot.tree.add_command(config)

@config.command(name="welcome", description="Set the welcome channel")
@discord.app_commands.describe(channel="Text channel for welcome messages")
@discord.app_commands.checks.has_permissions(administrator=True)
async def config_welcome(interaction: discord.Interaction, channel: discord.TextChannel):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO guild_config (guild_id, welcome_channel_id)
                    VALUES (%s, %s)
                    ON CONFLICT (guild_id)
                    DO UPDATE SET welcome_channel_id = EXCLUDED.welcome_channel_id
                """, (interaction.guild.id, channel.id))
        await interaction.response.send_message(f"✅ Welcome channel set to {channel.mention}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message("❌ Error setting welcome channel.", ephemeral=True)

@config.command(name="goodbye", description="Set the goodbye channel")
@discord.app_commands.describe(channel="Text channel for goodbye messages")
@discord.app_commands.checks.has_permissions(administrator=True)
async def config_goodbye(interaction: discord.Interaction, channel: discord.TextChannel):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO guild_config (guild_id, goodbye_channel_id)
                    VALUES (%s, %s)
                    ON CONFLICT (guild_id)
                    DO UPDATE SET goodbye_channel_id = EXCLUDED.goodbye_channel_id
                """, (interaction.guild.id, channel.id))
        await interaction.response.send_message(f"✅ Goodbye channel set to {channel.mention}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message("❌ Error setting goodbye channel.", ephemeral=True)

@config.command(name="serverstats", description="Manage server stats system")
@discord.app_commands.describe(action="Action to perform on server stats")
@discord.app_commands.choices(action=[
    app_commands.Choice(name="View Current Setup", value="view"),
    app_commands.Choice(name="Delete All Stats", value="delete"),
    app_commands.Choice(name="Reset Stats", value="reset")
])
@discord.app_commands.checks.has_permissions(administrator=True)
async def config_serverstats(interaction: discord.Interaction, action: app_commands.Choice[str]):
    await interaction.response.defer(ephemeral=True)
    try:
        guild = interaction.guild
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT stats_category_id, member_count_channel_id, bot_count_channel_id, role_count_channel_id, setup_complete FROM guild_config WHERE guild_id = %s", (guild.id,))
                row = cur.fetchone()
        
        if not row or not row[4]:  # setup_complete check
            await interaction.followup.send("❌ No server stats setup found. Use `/setup serverstats` first.", ephemeral=True)
            return
        
        stats_cat_id, member_ch_id, bot_ch_id, role_ch_id, _ = row
        
        if action.value == "view":
            category = guild.get_channel(stats_cat_id)
            member_ch = guild.get_channel(member_ch_id)
            bot_ch = guild.get_channel(bot_ch_id)
            role_ch = guild.get_channel(role_ch_id)
            
            embed = discord.Embed(
                title="📊 Current Server Stats Setup",
                color=discord.Color.blue()
            )
            embed.add_field(name="Category", value=category.mention if category else "Not found", inline=False)
            embed.add_field(name="Member Counter", value=member_ch.mention if member_ch else "Not found", inline=True)
            embed.add_field(name="Bot Counter", value=bot_ch.mention if bot_ch else "Not found", inline=True)
            embed.add_field(name="Role Counter", value=role_ch.mention if role_ch else "Not found", inline=True)
            await interaction.followup.send(embed=embed)
            
        elif action.value == "delete":
            # Delete all channels and category
            category = guild.get_channel(stats_cat_id)
            if category:
                for channel in category.channels:
                    try:
                        await channel.delete()
                    except:
                        pass
                try:
                    await category.delete()
                except:
                    pass
            
            # Clear database
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""UPDATE guild_config SET 
                        stats_category_id = NULL, 
                        member_count_channel_id = NULL, 
                        bot_count_channel_id = NULL, 
                        role_count_channel_id = NULL,
                        channel_count_channel_id = NULL,
                        setup_complete = FALSE 
                        WHERE guild_id = %s""", (guild.id,))
            
            await interaction.followup.send("✅ All server stats have been deleted successfully.")
            
        elif action.value == "reset":
            # Update all counters with current values
            member_ch = guild.get_channel(member_ch_id)
            bot_ch = guild.get_channel(bot_ch_id)
            role_ch = guild.get_channel(role_ch_id)
            
            if member_ch:
                try:
                    await member_ch.edit(name=f"👥 Members: {guild.member_count}")
                except:
                    pass
            if bot_ch:
                bot_count = sum(1 for member in guild.members if member.bot)
                try:
                    await bot_ch.edit(name=f"🤖 Bots: {bot_count}")
                except:
                    pass
            if role_ch:
                role_count = len(guild.roles) - 1
                try:
                    await role_ch.edit(name=f"📋 Roles: {role_count}")
                except:
                    pass
            
            await interaction.followup.send("✅ Server stats counters have been reset with current values.")
            
    except Exception as e:
        print(f"Error in config_serverstats: {e}")
        await interaction.followup.send("❌ Error managing server stats.", ephemeral=True)

@bot.event
async def on_member_join(member: discord.Member):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT welcome_channel_id FROM guild_config WHERE guild_id = %s", (member.guild.id,))
                row = cur.fetchone()
        if row and row[0]:
            channel = member.guild.get_channel(row[0])
            if channel:
                embed = discord.Embed(
                    title="Welcome! 🎉",
                    description=f"Welcome to **{member.guild.name}**, {member.mention}!",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
                embed.add_field(name="Member Count", value=f"You are member #{member.guild.member_count}", inline=True)
                await channel.send(embed=embed)
    except Exception as e:
        pass  # Silent fail for event handlers

@bot.event
async def on_member_remove(member: discord.Member):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT goodbye_channel_id FROM guild_config WHERE guild_id = %s", (member.guild.id,))
                row = cur.fetchone()
        if row and row[0]:
            channel = member.guild.get_channel(row[0])
            if channel:
                embed = discord.Embed(
                    title="Goodbye 👋",
                    description=f"**{member.display_name}** has left the server.",
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="Member Count", value=f"We now have {member.guild.member_count} members", inline=True)
                await channel.send(embed=embed)
    except Exception as e:
        pass  # Silent fail for event handlers

# Global error handler for slash commands
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # Log the error server-side
    print(f"Error in command {interaction.command.name if interaction.command else 'Unknown'}: {error}")

    # If the interaction hasn't been responded to yet, send an error message
    if not interaction.response.is_done():
        await interaction.response.send_message(
            "❌ An error occurred while processing your command.",
            ephemeral=True
        )

if __name__ == "__main__":
    bot.run(BOT_TOKEN)