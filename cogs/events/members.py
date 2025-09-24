import discord
from discord.ext import commands
from datetime import datetime, timezone
from cogs.utils.db import get_db_connection
import logging

logger = logging.getLogger(__name__)

class MemberEvents(commands.Cog):
    """Handles events related to guild members, such as joins and leaves."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        Triggered when a new member joins a guild. Sends a welcome message
        if the guild has one configured.
        """
        conn = await get_db_connection()
        if not conn:
            return

        try:
            cursor = await conn.execute("SELECT * FROM guild_config WHERE guild_id = ?", (member.guild.id,))
            config = await cursor.fetchone()
            
            if config and config["welcome_channel_id"]:
                channel = member.guild.get_channel(config["welcome_channel_id"])
                if channel:
                    # Use the custom message or a default one
                    message = config["welcome_message"] or f"Welcome to the server, {member.mention}!"
                    message = message.replace("{user.mention}", member.mention).replace("{user.name}", member.name)

                    embed = discord.Embed(
                        title="Welcome! 🎉",
                        description=message,
                        color=discord.Color.green(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.set_thumbnail(url=member.display_avatar.url)
                    if config["welcome_image"]:
                        embed.set_image(url=config["welcome_image"])
                    
                    await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in on_member_join for guild {member.guild.id}: {e}")
        finally:
            await conn.close()

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """
        Triggered when a member leaves a guild. Sends a goodbye message
        if the guild has one configured.
        """
        conn = await get_db_connection()
        if not conn:
            return
            
        try:
            cursor = await conn.execute("SELECT * FROM guild_config WHERE guild_id = ?", (member.guild.id,))
            config = await cursor.fetchone()

            if config and config["goodbye_channel_id"]:
                channel = member.guild.get_channel(config["goodbye_channel_id"])
                if channel:
                    # Use the custom message or a default one
                    message = config["goodbye_message"] or f"**{member.display_name}** has left the server."
                    message = message.replace("{user.name}", member.name)

                    embed = discord.Embed(
                        title="Goodbye 👋",
                        description=message,
                        color=discord.Color.red(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.set_thumbnail(url=member.display_avatar.url)
                    if config["goodbye_image"]:
                        embed.set_image(url=config["goodbye_image"])
                        
                    await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in on_member_remove for guild {member.guild.id}: {e}")
        finally:
            await conn.close()

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(MemberEvents(bot))

