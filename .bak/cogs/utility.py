import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from .utils.db import get_db_connection

class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show all available commands")
    async def help_command(self, interaction: discord.Interaction):
        try:
            config = None
            async with await get_db_connection() as conn:
                async with conn.execute("SELECT * FROM guild_config WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
                    config = await cursor.fetchone()

            welcome_status = "✅" if config and config["welcome_channel_id"] else "❌"
            goodbye_status = "✅" if config and config["goodbye_channel_id"] else "❌"
            serverstats_status = "✅" if config and config["setup_complete"] else "❌"

            embed = discord.Embed(
                title="🤖 Tilt-bot Help",
                description="Here are the commands you can use:",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(
                name="📊 Utility Commands",
                value="`/help` `/serverinfo` `/userinfo` `/roleinfo` `/avatar` `/membercount` `/ping` `/botinfo` `/emojis` `/invite`",
                inline=False
            )
            embed.add_field(
                name="🛡️ Moderation Commands",
                value="`/clear` - Clear messages (1-100)",
                inline=False
            )
            embed.add_field(
                name="⚙️ Setup Commands",
                value=f"{welcome_status} `/setup welcome` - Set up or remove the welcome channel.\n"
                      f"{goodbye_status} `/setup goodbye` - Set up or remove the goodbye channel.\n"
                      f"{serverstats_status} `/setup serverstats` - Set up or remove server stats counters.",
                inline=False
            )
            embed.add_field(
                name="🔧 Configuration Commands",
                value="`/config welcome` - Manage the welcome message.\n"
                      "`/config goodbye` - Manage the goodbye message.\n"
                      "`/config serverstats` - Manage server stats counters.",
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Error in help command: {e}")
            await interaction.response.send_message("❌ Error displaying help menu.", ephemeral=True)

    @app_commands.command(name="serverinfo", description="View server information")
    async def serverinfo(self, interaction: discord.Interaction):
        try:
            g = interaction.guild
            embed = discord.Embed(title=g.name, color=discord.Color.blue(), timestamp=datetime.now(timezone.utc))
            if g.icon:
                embed.set_thumbnail(url=g.icon.url)
            embed.add_field(name="Server ID", value=g.id, inline=True)
            embed.add_field(name="Owner", value=g.owner.mention if g.owner else "Unknown", inline=True)
            embed.add_field(name="Created", value=f"<t:{int(g.created_at.timestamp())}:F>", inline=True)
            embed.add_field(name="Members", value=g.member_count, inline=True)
            embed.add_field(name="Text Channels", value=len(g.text_channels), inline=True)
            embed.add_field(name="Voice Channels", value=len(g.voice_channels), inline=True)
            embed.add_field(name="Roles", value=len(g.roles), inline=True)
            bot_count = sum(1 for m in g.members if m.bot)
            embed.add_field(name="Bots", value=bot_count, inline=True)
            await interaction.response.send_message(embed=embed)
        except Exception:
            await interaction.response.send_message("❌ Error retrieving server information.", ephemeral=True)
            
    @app_commands.command(name="userinfo", description="View information about a user")
    @app_commands.describe(member="The member to lookup")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        try:
            m = member or interaction.user
            embed = discord.Embed(title=m.display_name, color=m.color, timestamp=datetime.now(timezone.utc))
            embed.set_thumbnail(url=m.display_avatar.url)
            embed.add_field(name="User ID", value=m.id, inline=True)
            embed.add_field(name="Username", value=str(m), inline=True)
            embed.add_field(name="Bot", value="Yes" if m.bot else "No", inline=True)
            embed.add_field(name="Account Created", value=f"<t:{int(m.created_at.timestamp())}:F>", inline=False)
            if m.joined_at:
                embed.add_field(name="Joined Server", value=f"<t:{int(m.joined_at.timestamp())}:F>", inline=False)
            roles = [r.mention for r in m.roles[1:]] or ["No roles"]
            embed.add_field(name=f"Roles ({len(m.roles)-1})", value=", ".join(roles), inline=False)
            await interaction.response.send_message(embed=embed)
        except Exception:
            await interaction.response.send_message("❌ Error retrieving user information.", ephemeral=True)

    @app_commands.command(name="roleinfo", description="View information about a role")
    @app_commands.describe(role="The role to lookup")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        try:
            embed = discord.Embed(title=role.name, color=role.color, timestamp=datetime.now(timezone.utc))
            embed.add_field(name="Role ID", value=role.id, inline=True)
            embed.add_field(name="Members", value=len(role.members), inline=True)
            embed.add_field(name="Created", value=f"<t:{int(role.created_at.timestamp())}:F>", inline=True)
            embed.add_field(name="Position", value=role.position, inline=True)
            embed.add_field(name="Mentionable", value=str(role.mentionable), inline=True)
            embed.add_field(name="Color", value=str(role.color), inline=True)
            await interaction.response.send_message(embed=embed)
        except Exception:
            await interaction.response.send_message("❌ Error retrieving role information.", ephemeral=True)

    @app_commands.command(name="avatar", description="Get a user's avatar")
    @app_commands.describe(member="The member whose avatar to show")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member = None):
        try:
            m = member or interaction.user
            embed = discord.Embed(title=f"{m.display_name}'s Avatar", color=discord.Color.blue(), timestamp=datetime.now(timezone.utc))
            embed.set_image(url=m.display_avatar.url)
            await interaction.response.send_message(embed=embed)
        except Exception:
            await interaction.response.send_message("❌ Error retrieving avatar.", ephemeral=True)

    @app_commands.command(name="membercount", description="Show member count")
    async def membercount(self, interaction: discord.Interaction):
        try:
            total = interaction.guild.member_count
            bots = sum(1 for m in interaction.guild.members if m.bot)
            humans = total - bots
            await interaction.response.send_message(
                f"**{interaction.guild.name}** has **{total}** members (**{humans}** humans, **{bots}** bots)."
            )
        except Exception:
            await interaction.response.send_message("❌ Error retrieving member count.", ephemeral=True)

    @app_commands.command(name="ping", description="Show bot latency")
    async def ping(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_message(f"Pong! Latency is {round(self.bot.latency*1000)}ms.")
        except Exception:
            await interaction.response.send_message("❌ Error checking ping.", ephemeral=True)

    @app_commands.command(name="botinfo", description="Information about the bot")
    async def botinfo(self, interaction: discord.Interaction):
        try:
            embed = discord.Embed(title="Bot Info", color=discord.Color.purple(), timestamp=datetime.now(timezone.utc))
            embed.add_field(name="Username", value=str(self.bot.user), inline=True)
            embed.add_field(name="ID", value=self.bot.user.id, inline=True)
            embed.add_field(name="Latency", value=f"{round(self.bot.latency*1000)}ms", inline=True)
            embed.add_field(name="Servers", value=len(self.bot.guilds), inline=True)
            total = sum(g.member_count for g in self.bot.guilds)
            embed.add_field(name="Total Members", value=total, inline=True)
            await interaction.response.send_message(embed=embed)
        except Exception:
            await interaction.response.send_message("❌ Error retrieving bot information.", ephemeral=True)

    @app_commands.command(name="emojis", description="List server emojis")
    async def emojis(self, interaction: discord.Interaction):
        try:
            es = interaction.guild.emojis
            if not es:
                await interaction.response.send_message("This server has no custom emojis.")
            else:
                await interaction.response.send_message(" ".join(str(e) for e in es))
        except Exception:
            await interaction.response.send_message("❌ Error retrieving emojis.", ephemeral=True)

    @app_commands.command(name="invite", description="Get bot invite link")
    async def invite(self, interaction: discord.Interaction):
        try:
            link = f"https://discord.com/oauth2/authorize?client_id={self.bot.user.id}&scope=bot%20applications.commands&permissions=8"
            await interaction.response.send_message(f"Invite me: {link}")
        except Exception:
            await interaction.response.send_message("❌ Error generating invite link.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
