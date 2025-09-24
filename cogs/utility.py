import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from .utils.db import get_db_connection

class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Shows a detailed list of all available commands.")
    @app_commands.guild_only()
    async def help(self, interaction: discord.Interaction):
        """Displays a categorized and detailed list of all available bot commands."""
        async with await get_db_connection() as conn:
            async with conn.execute("SELECT * FROM guild_config WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
                config = await cursor.fetchone()

        # Determine the status of setup modules for this server
        welcome_status = "✅ Configured" if config and config["welcome_channel_id"] else "❌ Not Set"
        goodbye_status = "✅ Configured" if config and config["goodbye_channel_id"] else "❌ Not Set"
        serverstats_status = "✅ Configured" if config and config["setup_complete"] else "❌ Not Set"

        embed = discord.Embed(
            title="Tilt-bot Help",
            description="Here are the commands you can use:",
            color=discord.Color.dark_theme(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="🛠️ Utility Commands",
            value="`/help` `/serverinfo` `/userinfo` `/avatar` `/ping` `/botinfo` `/invite`",
            inline=False
        )
        embed.add_field(
            name="🛡️ Moderation Commands",
            value="`/clear` - Clear messages (1-100)",
            inline=False
        )
        embed.add_field(
            name="⚙️ Setup Commands",
            value=f"`/setup welcome` - Set up the welcome channel. **({welcome_status})**\n"
                  f"`/setup goodbye` - Set up the goodbye channel. **({goodbye_status})**\n"
                  f"`/setup serverstats` - Create server stats counters. **({serverstats_status})**",
            inline=False
        )
        embed.add_field(
            name="🔧 Configuration Commands",
            value="`/config welcome` - Manage the welcome message.\n"
                  "`/config goodbye` - Manage the goodbye message.\n"
                  "`/config serverstats` - Manage server stats counters.",
            inline=False
        )
        
        embed.set_footer(text=f"Tilt-bot {self.bot.version}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="serverinfo", description="Displays detailed information about the current server.")
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction):
        """Provides a comprehensive embed with server details."""
        guild = interaction.guild
        embed = discord.Embed(title=f"Server Info: {guild.name}", color=discord.Color.blue(), timestamp=datetime.now(timezone.utc))
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        embed.set_author(name=self.bot.user.name, icon_url=self.bot.user.display_avatar.url)
        embed.add_field(name="Owner", value=guild.owner.mention, inline=True)
        embed.add_field(name="Server ID", value=f"`{guild.id}`", inline=True)
        embed.add_field(name="Created On", value=f"<t:{int(guild.created_at.timestamp())}:D>", inline=True)
        
        humans = len([m for m in guild.members if not m.bot])
        bots = len([m for m in guild.members if m.bot])
        embed.add_field(name="Members", value=f"**Total:** {guild.member_count}\n**Humans:** {humans}\n**Bots:** {bots}", inline=True)
        embed.add_field(name="Channels", value=f"**Text:** {len(guild.text_channels)}\n**Voice:** {len(guild.voice_channels)}", inline=True)
        embed.add_field(name="Roles", value=len(guild.roles), inline=True)

        await interaction.response.send_message(embed=embed)
            
    @app_commands.command(name="userinfo", description="Displays detailed information about a user.")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        """Provides a detailed embed on a specified user or the command author."""
        user = member or interaction.user
        embed = discord.Embed(title=f"User Info: {user.display_name}", color=user.color, timestamp=datetime.now(timezone.utc))
        embed.set_thumbnail(url=user.display_avatar.url)
        
        embed.add_field(name="Username", value=f"`{user}`", inline=True)
        embed.add_field(name="User ID", value=f"`{user.id}`", inline=True)
        embed.add_field(name="Is a Bot?", value="Yes" if user.bot else "No", inline=True)
        
        embed.add_field(name="Account Created", value=f"<t:{int(user.created_at.timestamp())}:F>", inline=False)
        if isinstance(user, discord.Member) and user.joined_at:
            embed.add_field(name="Joined Server", value=f"<t:{int(user.joined_at.timestamp())}:F>", inline=False)
        
        if isinstance(user, discord.Member):
            roles = [r.mention for r in user.roles[1:]] or ["None"]
            embed.add_field(name=f"Roles ({len(user.roles)-1})", value=", ".join(roles), inline=False)
            
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="Displays a user's avatar.")
    @app_commands.describe(member="The user whose avatar you want to see.")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member = None):
        """Shows a user's avatar in a large format."""
        user = member or interaction.user
        embed = discord.Embed(title=f"{user.display_name}'s Avatar", color=discord.Color.dark_grey())
        embed.set_image(url=user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ping", description="Checks the bot's response time.")
    async def ping(self, interaction: discord.Interaction):
        """Calculates and displays the bot's latency."""
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"Pong! 🏓 Latency is {latency}ms.")

    @app_commands.command(name="botinfo", description="Displays information about Tilt-bot.")
    async def botinfo(self, interaction: discord.Interaction):
        """Shows detailed statistics and information about the bot itself."""
        embed = discord.Embed(title="Tilt-bot Statistics", color=discord.Color.purple(), timestamp=datetime.now(timezone.utc))
        embed.set_author(name=self.bot.user.name, icon_url=self.bot.user.display_avatar.url)
        
        embed.add_field(name="Version", value=f"`{self.bot.version}`", inline=True)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency*1000)}ms", inline=True)
        embed.add_field(name="Developer", value="TiltedBl0ck", inline=True)
        
        embed.add_field(name="Servers", value=len(self.bot.guilds), inline=True)
        total_members = sum(g.member_count for g in self.bot.guilds)
        embed.add_field(name="Total Users", value=total_members, inline=True)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="invite", description="Get the bot's invite link.")
    async def invite(self, interaction: discord.Interaction):
        """Provides a button to invite the bot to another server."""
        invite_link = f"https://discord.com/oauth2/authorize?client_id={self.bot.user.id}&scope=bot%20applications.commands&permissions=8"
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Click to Invite!", style=discord.ButtonStyle.green, url=invite_link))
        await interaction.response.send_message("Use the button below to add me to your server:", view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))

