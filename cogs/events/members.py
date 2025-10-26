import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone # Use timezone-aware datetime
import cogs.utils.db as db_utils # Import module alias
import logging
import asyncio # Import asyncio for sleep

logger = logging.getLogger(__name__)

class MemberEvents(commands.Cog):
    """Handles events related to guild members and server stats."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_server_stats.start()

    def cog_unload(self):
        """Clean up when the cog is unloaded."""
        self.update_server_stats.cancel()
        logger.info("Cancelled update_server_stats task.")


    @tasks.loop(minutes=10)
    async def update_server_stats(self):
        """A background task that updates server statistics channels every 10 minutes."""
        logger.debug("Running update_server_stats task.")
        if db_utils.pool is None:
            logger.warning("Database pool not available, skipping server stats update.")
            return

        try:
            # Use fetch directly instead of execute + fetchall
            async with db_utils.get_db_connection() as conn: # Use alias
                # Use fetch to get a list of asyncpg.Record objects
                configs = await conn.fetch("""
                    SELECT guild_id, member_count_channel_id, bot_count_channel_id, role_count_channel_id
                    FROM guild_config
                    WHERE stats_category_id IS NOT NULL
                """)

                logger.debug(f"Found {len(configs)} guilds with server stats enabled.")

                for config_record in configs:
                    # Convert asyncpg.Record to a dictionary for easier access
                    config = dict(config_record)
                    guild = self.bot.get_guild(config["guild_id"])
                    if not guild:
                        logger.warning(f"Guild {config['guild_id']} not found during stats update.")
                        continue

                    logger.debug(f"Updating stats for guild: {guild.name} ({guild.id})")

                    # --- Update Member Count ---
                    if config.get("member_count_channel_id"): # Use .get for safety
                        member_channel = guild.get_channel(config["member_count_channel_id"])
                        if member_channel and isinstance(member_channel, discord.VoiceChannel):
                            new_name = f"👥 Members: {guild.member_count}"
                            if member_channel.name != new_name:
                                try:
                                    await member_channel.edit(name=new_name, reason="Update Server Stats")
                                    logger.debug(f"Updated member count for {guild.name} to {guild.member_count}")
                                except discord.Forbidden:
                                    logger.error(f"Missing permissions to edit member count channel in {guild.name}")
                                except discord.HTTPException as e:
                                     logger.error(f"HTTP error editing member count channel in {guild.name}: {e.status} {e.text}")
                                except Exception as e:
                                    logger.error(f"Error editing member count channel in {guild.name}: {e}", exc_info=True)
                        elif member_channel:
                             logger.warning(f"Member count channel {config['member_count_channel_id']} in {guild.name} is not a voice channel.")
                        else:
                             logger.warning(f"Member count channel {config['member_count_channel_id']} not found in {guild.name}.")
                    else:
                         logger.debug(f"No member count channel configured for guild {guild.id}")


                    # --- Update Bot Count ---
                    if config.get("bot_count_channel_id"):
                        bot_channel = guild.get_channel(config["bot_count_channel_id"])
                        if bot_channel and isinstance(bot_channel, discord.VoiceChannel):
                             bot_count = sum(1 for m in guild.members if m.bot)
                             new_name = f"🤖 Bots: {bot_count}"
                             if bot_channel.name != new_name:
                                try:
                                    await bot_channel.edit(name=new_name, reason="Update Server Stats")
                                    logger.debug(f"Updated bot count for {guild.name} to {bot_count}")
                                except discord.Forbidden:
                                    logger.error(f"Missing permissions to edit bot count channel in {guild.name}")
                                except discord.HTTPException as e:
                                     logger.error(f"HTTP error editing bot count channel in {guild.name}: {e.status} {e.text}")
                                except Exception as e:
                                    logger.error(f"Error editing bot count channel in {guild.name}: {e}", exc_info=True)
                        elif bot_channel:
                             logger.warning(f"Bot count channel {config['bot_count_channel_id']} in {guild.name} is not a voice channel.")
                        else:
                             logger.warning(f"Bot count channel {config['bot_count_channel_id']} not found in {guild.name}.")
                    else:
                         logger.debug(f"No bot count channel configured for guild {guild.id}")


                    # --- Update Role Count ---
                    if config.get("role_count_channel_id"):
                        role_channel = guild.get_channel(config["role_count_channel_id"])
                        if role_channel and isinstance(role_channel, discord.VoiceChannel):
                             role_count = len(guild.roles)
                             new_name = f"📜 Roles: {role_count}"
                             if role_channel.name != new_name:
                                try:
                                    await role_channel.edit(name=new_name, reason="Update Server Stats")
                                    logger.debug(f"Updated role count for {guild.name} to {role_count}")
                                except discord.Forbidden:
                                    logger.error(f"Missing permissions to edit role count channel in {guild.name}")
                                except discord.HTTPException as e:
                                     logger.error(f"HTTP error editing role count channel in {guild.name}: {e.status} {e.text}")
                                except Exception as e:
                                    logger.error(f"Error editing role count channel in {guild.name}: {e}", exc_info=True)
                        elif role_channel:
                            logger.warning(f"Role count channel {config['role_count_channel_id']} in {guild.name} is not a voice channel.")
                        else:
                            logger.warning(f"Role count channel {config['role_count_channel_id']} not found in {guild.name}.")
                    else:
                         logger.debug(f"No role count channel configured for guild {guild.id}")

                    await asyncio.sleep(1) # Add a small delay between guilds to avoid potential rate limits

        except ConnectionError as e: # Catch connection issues from get_db_connection
            logger.error(f"Database connection error during stats update: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in update_server_stats task loop: {e}", exc_info=True)

    @update_server_stats.before_loop
    async def before_update_stats(self):
        """Waits until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()
        logger.info("Bot ready, starting update_server_stats loop.")


    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Sends a welcome message when a new member joins."""
        guild = member.guild
        logger.info(f"Member joined: {member} ({member.id}) in guild {guild.name} ({guild.id})")

        if db_utils.pool is None:
            logger.warning(f"Database pool not ready, cannot process join for {member} in {guild.name}")
            return

        try:
            async with db_utils.get_db_connection() as conn: # Use alias
                config_record = await conn.fetchrow("SELECT welcome_channel_id, welcome_message, welcome_image FROM guild_config WHERE guild_id = $1", guild.id)

                if config_record:
                     config = dict(config_record) # Convert to dict
                     if config.get("welcome_channel_id"):
                        channel = guild.get_channel(config["welcome_channel_id"])
                        if channel and isinstance(channel, discord.TextChannel):
                            message = config.get("welcome_message") or f"Welcome {member.mention} to the server!" # Use .get
                            # Safe replacements
                            message = message.replace("{user.mention}", member.mention)
                            message = message.replace("{user.name}", member.name)
                            message = message.replace("{user.discriminator}", member.discriminator or '0000') # Handle no discriminator
                            message = message.replace("{user.id}", str(member.id))
                            message = message.replace("{server.name}", guild.name)
                            message = message.replace("{member.count}", str(guild.member_count))


                            embed = discord.Embed(
                                description=message,
                                color=discord.Color.green(),
                                timestamp=datetime.now(timezone.utc)
                            )
                            avatar_url = member.display_avatar.url if member.display_avatar else None
                            embed.set_author(name=f"Welcome, {member.display_name}!", icon_url=avatar_url)
                            if avatar_url:
                                 embed.set_thumbnail(url=avatar_url)

                            if config.get("welcome_image"):
                                # Basic URL validation (optional, consider a regex for stricter check)
                                if str(config["welcome_image"]).startswith(("http://", "https://")):
                                    embed.set_image(url=config["welcome_image"])
                                else:
                                    logger.warning(f"Invalid welcome_image URL for guild {guild.id}: {config['welcome_image']}")

                            try:
                                await channel.send(embed=embed)
                                logger.info(f"Sent welcome message for {member} in {guild.name}")
                            except discord.Forbidden:
                                logger.error(f"Missing permissions to send welcome message in channel {channel.id} for guild {guild.id}")
                            except discord.HTTPException as e:
                                 logger.error(f"HTTP error sending welcome message in {channel.id}: {e.status} {e.text}")
                            except Exception as e:
                                logger.error(f"Failed to send welcome message: {e}", exc_info=True)
                        elif channel:
                             logger.warning(f"Welcome channel {config['welcome_channel_id']} for guild {guild.id} is not a text channel.")
                        else:
                             logger.warning(f"Welcome channel {config['welcome_channel_id']} for guild {guild.id} not found.")

        except ConnectionError as e:
             logger.error(f"Database connection error during on_member_join for guild {guild.id}: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred in on_member_join for guild {guild.id}: {e}", exc_info=True)


    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Sends a goodbye message when a member leaves."""
        guild = member.guild
        logger.info(f"Member left: {member} ({member.id}) from guild {guild.name} ({guild.id})")

        if db_utils.pool is None:
            logger.warning(f"Database pool not ready, cannot process leave for {member} in {guild.name}")
            return

        try:
            async with db_utils.get_db_connection() as conn: # Use alias
                config_record = await conn.fetchrow("SELECT goodbye_channel_id, goodbye_message, goodbye_image FROM guild_config WHERE guild_id = $1", guild.id)

                if config_record:
                    config = dict(config_record) # Convert to dict
                    if config.get("goodbye_channel_id"):
                        channel = guild.get_channel(config["goodbye_channel_id"])
                        if channel and isinstance(channel, discord.TextChannel):
                            message = config.get("goodbye_message") or f"{member.display_name} has left the server."
                            # Safe replacements
                            message = message.replace("{user.mention}", member.mention) # Note: Mention might not ping if user left
                            message = message.replace("{user.name}", member.name)
                            message = message.replace("{user.discriminator}", member.discriminator or '0000') # Handle no discriminator
                            message = message.replace("{user.id}", str(member.id))
                            message = message.replace("{server.name}", guild.name)
                            # Member count should reflect the count *after* removal, which happens just before this event usually
                            message = message.replace("{member.count}", str(guild.member_count))


                            embed = discord.Embed(
                                description=message,
                                color=discord.Color.red(),
                                timestamp=datetime.now(timezone.utc)
                            )
                            avatar_url = member.display_avatar.url if member.display_avatar else None
                            # Use display_name in case name+discriminator isn't unique enough or desired
                            embed.set_author(name=f"Goodbye, {member.display_name}.", icon_url=avatar_url)
                            if avatar_url:
                                 embed.set_thumbnail(url=avatar_url)

                            if config.get("goodbye_image"):
                                 if str(config["goodbye_image"]).startswith(("http://", "https://")):
                                    embed.set_image(url=config["goodbye_image"])
                                 else:
                                    logger.warning(f"Invalid goodbye_image URL for guild {guild.id}: {config['goodbye_image']}")

                            try:
                                await channel.send(embed=embed)
                                logger.info(f"Sent goodbye message for {member} in {guild.name}")
                            except discord.Forbidden:
                                logger.error(f"Missing permissions to send goodbye message in channel {channel.id} for guild {guild.id}")
                            except discord.HTTPException as e:
                                 logger.error(f"HTTP error sending goodbye message in {channel.id}: {e.status} {e.text}")
                            except Exception as e:
                                logger.error(f"Failed to send goodbye message: {e}", exc_info=True)
                        elif channel:
                             logger.warning(f"Goodbye channel {config['goodbye_channel_id']} for guild {guild.id} is not a text channel.")
                        else:
                             logger.warning(f"Goodbye channel {config['goodbye_channel_id']} for guild {guild.id} not found.")

        except ConnectionError as e:
             logger.error(f"Database connection error during on_member_remove for guild {guild.id}: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred in on_member_remove for guild {guild.id}: {e}", exc_info=True)


async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(MemberEvents(bot))

