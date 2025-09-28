import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone
from cogs.utils.db import get_db_connection
import logging

logger = logging.getLogger(__name__)

class MemberEvents(commands.Cog):
    """Handles events related to guild members and server stats."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_server_stats.start()

    def cog_unload(self):
        self.update_server_stats.cancel()

    @tasks.loop(minutes=10)
    async def update_server_stats(self):
        """A background task that updates server statistics channels every 10 minutes."""
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute("SELECT * FROM guild_config WHERE stats_category_id IS NOT NULL")
                configs = await cursor.fetchall()
                for config in configs:
                    guild = self.bot.get_guild(config["guild_id"])
                    if not guild:
                        continue
                    
                    # Update Member Count
                    if config["member_count_channel_id"]:
                        channel = guild.get_channel(config["member_count_channel_id"])
                        if channel:
                            await channel.edit(name=f"👥 Members: {guild.member_count}")
                    
                    # Update Bot Count
                    if config["bot_count_channel_id"]:
                        channel = guild.get_channel(config["bot_count_channel_id"])
                        if channel:
                            bot_count = sum(1 for m in guild.members if m.bot)
                            await channel.edit(name=f"🤖 Bots: {bot_count}")

                    # Update Role Count
                    if config["role_count_channel_id"]:
                        channel = guild.get_channel(config["role_count_channel_id"])
                        if channel:
                            await channel.edit(name=f"📜 Roles: {len(guild.roles)}")
        except Exception as e:
            logger.error(f"Error in update_server_stats task: {e}")
    
    @update_server_stats.before_loop
    async def before_update_stats(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Sends a welcome message when a new member joins."""
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute("SELECT * FROM guild_config WHERE guild_id = ?", (member.guild.id,))
                config = await cursor.fetchone()
                if config and config["welcome_channel_id"]:
                    channel = member.guild.get_channel(config["welcome_channel_id"])
                    if channel:
                        message = config["welcome_message"] or f"Welcome {member.mention} to the server!"
                        message = message.replace("{user.mention}", member.mention).replace("{user.name}", member.name)
                        embed = discord.Embed(
                            description=message,
                            color=discord.Color.green(),
                            timestamp=datetime.now(timezone.utc)
                        ).set_author(name=f"Welcome, {member.display_name}!").set_thumbnail(url=member.display_avatar.url)
                        if config["welcome_image"]:
                            embed.set_image(url=config["welcome_image"])
                        await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"An error occurred in the on_member_join event: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Sends a goodbye message when a member leaves."""
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute("SELECT * FROM guild_config WHERE guild_id = ?", (member.guild.id,))
                config = await cursor.fetchone()
                if config and config["goodbye_channel_id"]:
                    channel = member.guild.get_channel(config["goodbye_channel_id"])
                    if channel:
                        message = config["goodbye_message"] or f"{member.display_name} has left the server."
                        message = message.replace("{user.name}", member.name)
                        embed = discord.Embed(
                            description=message,
                            color=discord.Color.red(),
                            timestamp=datetime.now(timezone.utc)
                        ).set_author(name=f"Goodbye, {member.display_name}.").set_thumbnail(url=member.display_avatar.url)
                        if config["goodbye_image"]:
                            embed.set_image(url=config["goodbye_image"])
                        await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"An error occurred in the on_member_remove event: {e}", exc_info=True)

async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(MemberEvents(bot))

