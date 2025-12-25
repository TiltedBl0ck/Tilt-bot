import discord
from discord import app_commands
from discord.ext import commands
from cogs.utils import db as db_utils

class HelpCommand(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Shows the help menu with all commands")
    async def help(self, interaction: discord.Interaction):
        try:
            embed = await self.build_help_embed(interaction)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            # Fallback if DB fails
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    async def build_help_embed(self, interaction: discord.Interaction) -> discord.Embed:
        # Fetch guild config to show enabled/disabled status
        config = await db_utils.get_config(interaction.guild.id)
        
        prefix = "/" # Slash commands always use /
        
        embed = discord.Embed(
            title="Tilt-bot Help",
            description=f"Here are all available commands. Use `{prefix}command` to run them.",
            color=discord.Color.gold()
        )
        
        # --- Dynamic Command Listing ---
        # We will iterate through all cogs and list their app commands
        
        # Helper to format command string
        def format_cmd(cmd):
            return f"`/{cmd.name}` - {cmd.description}"

        # 1. Collect commands by category (Cog)
        categories = {}
        
        for name, cog in self.bot.cogs.items():
            # Get commands for this cog
            commands_list = cog.get_app_commands()
            if not commands_list:
                continue
                
            # Filter out the help command itself to avoid clutter
            if name == "HelpCommand":
                continue

            # Organize text
            cmd_text_list = []
            for cmd in commands_list:
                if isinstance(cmd, app_commands.Group):
                    # Handle groups like /announce create, /config welcome
                    group_text = f"**/{cmd.name}** - {cmd.description}\n"
                    for sub in cmd.commands:
                        group_text += f"  └ `{sub.name}`: {sub.description}\n"
                    cmd_text_list.append(group_text)
                else:
                    cmd_text_list.append(format_cmd(cmd))
            
            if cmd_text_list:
                # Clean up Cog Name for display
                # e.g., "SetupCommands" -> "Setup", "ServerInfo" -> "Server Info"
                category_name = name.replace("Command", "").replace("Commands", "")
                # Add spaces before capital letters if needed, or manual mapping
                category_map = {
                    "Setup": "⚙️ Setup & Config",
                    "Config": "🔧 Configuration",
                    "Announcer": "📢 Announcements",
                    "Gemini": "🧠 AI Chat",
                    "Memory": "💾 AI Memory",
                    "ServerInfo": "📊 Server Info",
                    "UserInfo": "👤 User Info",
                    "Avatar": "🖼️ Avatar",
                    "Ping": "🏓 Latency",
                    "Invite": "🔗 Invite",
                    "Clear": "🧹 Moderation",
                    "BotInfo": "🤖 Bot Info",
                    "Counting": "🔢 Counting Game" # Although Counting is an event cog, if it has commands they go here
                }
                display_name = category_map.get(category_name, f"📂 {category_name}")
                
                categories[display_name] = "\n".join(cmd_text_list)

        # 2. Add Fields to Embed
        # Sort keys to make it look consistent (optional, but nice)
        sorted_cats = sorted(categories.keys())
        
        # Prioritize certain categories
        priority = ["⚙️ Setup & Config", "🔧 Configuration", "📢 Announcements", "🧠 AI Chat"]
        
        # Add priority categories first
        for cat in priority:
            if cat in categories:
                embed.add_field(name=cat, value=categories[cat], inline=False)
                del categories[cat] # Remove so we don't add twice
        
        # Add the rest
        for cat in sorted(categories.keys()):
             embed.add_field(name=cat, value=categories[cat], inline=False)

        # --- Module Status Section ---
        if config:
            # AI Chat Status (Default is OFF/0 in DB schema if not set)
            ai_enabled = config.get('ai_chat_enabled', 0)
            ai_status = "✅ On" if ai_enabled else "❌ Off"
            if config.get('ai_chat_channel_id'):
                ai_status += f" (<#{config['ai_chat_channel_id']}>)"
            else:
                ai_status += " (Not Set)"

            # Welcome Status
            welcome_status = "✅ On" if config.get('welcome_channel_id') else "❌ Off"
            
            # Counting Status
            counting_status = "✅ On" if config.get('counting_channel_id') else "❌ Off"
            
            # Server Stats Status
            stats_status = "✅ On" if config.get('stats_category_id') else "❌ Off"

            status_text = (
                f"**AI Chat:** {ai_status}\n"
                f"**Welcome Messages:** {welcome_status}\n"
                f"**Counting Game:** {counting_status}\n"
                f"**Server Stats:** {stats_status}"
            )
            embed.add_field(name="📊 Module Status", value=status_text, inline=False)

        # Footer
        version = getattr(self.bot, 'version', '1.0.3')
        embed.set_footer(text=f"Tilt-bot v{version} • /setup to configure modules")
        return embed

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCommand(bot))