import discord
from discord import app_commands
from discord.ext import commands
from cogs.utils import db as db_utils

class HelpCommand(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Shows the help menu")
    async def help(self, interaction: discord.Interaction):
        try:
            embed = await self.build_help_embed(interaction)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            # Fallback if DB fails
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    async def build_help_embed(self, interaction: discord.Interaction) -> discord.Embed:
        # Fetch guild config to customize help (e.g. show enabled modules)
        # FIX: Changed get_guild_config -> get_config
        config = await db_utils.get_config(interaction.guild.id)
        
        prefix = "/" # Slash commands always use /
        
        embed = discord.Embed(
            title="Tilt-bot Help",
            description=f"Here are the available commands. Use `{prefix}command` to run them.",
            color=discord.Color.gold()
        )
        
        # General Commands
        general = ""
        general += f"**{prefix}ping** - Check bot latency\n"
        general += f"**{prefix}botinfo** - View bot stats\n"
        general += f"**{prefix}serverinfo** - View server stats\n"
        general += f"**{prefix}userinfo [user]** - View user stats\n"
        general += f"**{prefix}avatar [user]** - View user avatar\n"
        general += f"**{prefix}invite** - Get bot invite link\n"
        embed.add_field(name="📜 General", value=general, inline=False)

        # Admin / Config Commands
        if interaction.user.guild_permissions.administrator:
            admin = ""
            admin += f"**{prefix}setup** - Interactive setup wizard\n"
            admin += f"**{prefix}config [setting] [value]** - Manually edit settings\n"
            admin += f"**{prefix}announce create/list/stop** - Manage announcements\n"
            admin += f"**{prefix}clear [amount]** - Delete messages\n"
            embed.add_field(name="⚙️ Admin", value=admin, inline=False)

        # Features Status
        if config:
            features = ""
            # AI Chat
            ai_status = "✅ On" if config.get('ai_chat_enabled') else "❌ Off"
            ai_channel = f"<#{config['ai_chat_channel_id']}>" if config.get('ai_chat_channel_id') else "Not Set"
            features += f"**AI Chat:** {ai_status} ({ai_channel})\n"
            
            # Welcome
            welcome_status = "✅ On" if config.get('welcome_channel_id') else "❌ Off"
            features += f"**Welcome Messages:** {welcome_status}\n"
            
            # Counting
            counting_status = "✅ On" if config.get('counting_channel_id') else "❌ Off"
            features += f"**Counting Game:** {counting_status}\n"
            
            embed.add_field(name="📊 Module Status", value=features, inline=False)

        embed.set_footer(text="Tilt-bot v1.0.1 • /setup to configure")
        return embed

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCommand(bot))