import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone # Use timezone-aware datetime
import cogs.utils.db as db_utils # Import module alias
import logging
import asyncio # Import asyncio for sleep
import asyncpg # Import asyncpg for exception handling

logger = logging.getLogger(__name__)

class MemberEvents(commands.Cog):
    """Handles events related to guild members using cached config and server stats."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Start task only if pool initialization succeeded during startup
        if db_utils.pool is not None:
             self.update_server_stats.start()
        else:
             logger.warning("Database pool not initialized. Server stats task will not start.")


    def cog_unload(self):
        """Clean up when the cog is unloaded."""
        self.update_server_stats.cancel()
        logger.info("Cancelled update_server_stats task.")


    # OPTIMIZATION: Increased interval from 10 minutes to 30 minutes
    # This reduces database wakeups and API calls significantly.
    @tasks.loop(minutes=30)
    async def update_server_stats(self):
        """A background task that updates server statistics channels every 30 minutes."""
        logger.debug("Running update_server_stats task.")
        if db_utils.pool is None:
            # This check ensures the task stops trying if the pool becomes unavailable later
            logger.warning("Database pool not available, skipping server stats update.")
            if self.update_server_stats.is_running():
                self.update_server_stats.cancel() # Stop the task if DB is gone
            return

        guild_configs_to_update = []
        try:
            # Fetch only the necessary IDs from guilds that have stats enabled
            async with db_utils.get_db_connection() as conn:
                configs = await conn.fetch("""
                    SELECT guild_id, member_count_channel_id, bot_count_channel_id, role_count_channel_id
                    FROM guild_config
                    WHERE stats_category_id IS NOT NULL
                      AND (member_count_channel_id IS NOT NULL OR
                           bot_count_channel_id IS NOT NULL OR
                           role_count_channel_id IS NOT NULL)
                """)
                # Convert records to dicts immediately for easier processing
                guild_configs_to_update = [dict(record) for record in configs]

        except (ConnectionError, asyncio.TimeoutError, asyncpg.PostgresError) as e: # Use imported asyncpg
            logger.error(f"Database error fetching guilds for stats update: {e}")
            await asyncio.sleep(60) # Wait a bit before retrying if DB error occurs
            return # Skip this iteration
        except Exception as e:
             logger.error(f"Unexpected error fetching guilds for stats update: {e}", exc_info=True)
             await asyncio.sleep(60)
             return


        logger.debug(f"Found {len(guild_configs_to_update)} guilds with server stats channels configured.")

        # Process each guild
        for config in guild_configs_to_update:
            guild = self.bot.get_guild(config["guild_id"])
            if not guild:
                logger.warning(f"Guild {config['guild_id']} not found during stats update.")
                continue

            logger.debug(f"Updating stats for guild: {guild.name} ({guild.id})")
            update_tasks = [] # Collect edit tasks for this guild

            # --- Update Member Count ---
            if config.get("member_count_channel_id"):
                member_channel = guild.get_channel(config["member_count_channel_id"])
                if member_channel and isinstance(member_channel, discord.VoiceChannel):
                    new_name = f"👥 Members: {guild.member_count}"
                    if member_channel.name != new_name:
                        update_tasks.append(
                            member_channel.edit(name=new_name, reason="Update Server Stats")
                        )

            # --- Update Bot Count ---
            if config.get("bot_count_channel_id"):
                bot_channel = guild.get_channel(config["bot_count_channel_id"])
                if bot_channel and isinstance(bot_channel, discord.VoiceChannel):
                     bot_count = sum(1 for m in guild.members if m.bot)
                     new_name = f"🤖 Bots: {bot_count}"
                     if bot_channel.name != new_name:
                         update_tasks.append(
                            bot_channel.edit(name=new_name, reason="Update Server Stats")
                         )

            # --- Update Role Count ---
            if config.get("role_count_channel_id"):
                role_channel = guild.get_channel(config["role_count_channel_id"])
                if role_channel and isinstance(role_channel, discord.VoiceChannel):
                     role_count = len(guild.roles) # Excludes @everyone implicitly
                     new_name = f"📜 Roles: {role_count}"
                     if role_channel.name != new_name:
                          update_tasks.append(
                            role_channel.edit(name=new_name, reason="Update Server Stats")
                          )

            # --- Execute updates for the current guild ---
            if update_tasks:
                logger.debug(f"Attempting {len(update_tasks)} channel edits for guild {guild.id}")
                results = await asyncio.gather(*update_tasks, return_exceptions=True)
                success_count = 0
                for i, result in enumerate(results):
                    channel_type = "unknown"
                    if i < len(update_tasks): 
                        try:
                           channel_obj = update_tasks[i].__self__
                           if isinstance(channel_obj, discord.VoiceChannel):
                               channel_type = f"{channel_obj.name} ({channel_obj.id})"
                        except: pass

                    if isinstance(result, Exception):
                        if isinstance(result, discord.Forbidden):
                            logger.error(f"Missing permissions to edit stats channel ({channel_type}) in {guild.name}")
                        elif isinstance(result, discord.HTTPException):
                             # Rate limits are common here, logging as error might be too noisy if frequent, but good for debugging
                             logger.warning(f"HTTP error editing stats channel ({channel_type}) in {guild.name}: {result.status} {result.text}")
                        else:
                            logger.error(f"Unexpected error editing stats channel ({channel_type}) in {guild.name}: {result}", exc_info=result)
                    else:
                        success_count += 1
                if success_count > 0:
                     logger.debug(f"Successfully updated {success_count} stats channels for {guild.name}")

            # Check for invalid/missing channels after attempting updates
            if config.get("member_count_channel_id") and not guild.get_channel(config["member_count_channel_id"]):
                 logger.warning(f"Member count channel {config['member_count_channel_id']} not found in {guild.name}.")
            if config.get("bot_count_channel_id") and not guild.get_channel(config["bot_count_channel_id"]):
                 logger.warning(f"Bot count channel {config['bot_count_channel_id']} not found in {guild.name}.")
            if config.get("role_count_channel_id") and not guild.get_channel(config["role_count_channel_id"]):
                 logger.warning(f"Role count channel {config['role_count_channel_id']} not found in {guild.name}.")


            await asyncio.sleep(1) # Small delay between guilds

        # Log completion of the loop iteration
        logger.debug("Finished update_server_stats iteration.")


    @update_server_stats.before_loop
    async def before_update_stats(self):
        """Waits until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()
        logger.info("Bot ready, starting update_server_stats loop.")

    @update_server_stats.error
    async def on_stats_error(self, error):
        """Handles errors within the update_server_stats task loop."""
        logger.error(f"Unhandled error in update_server_stats loop: {error}", exc_info=True)
        await asyncio.sleep(60) # Wait before potentially restarting


    @commands.Cog.listener("on_member_join")
    async def handle_member_join(self, member: discord.Member):
        """Sends a welcome message when a new member joins, using cached config."""
        guild = member.guild
        logger.info(f"Member joined: {member} ({member.id}) in guild {guild.name} ({guild.id})")

        config = await db_utils.get_guild_config(guild.id)

        if config and config.get("welcome_channel_id"):
            channel = guild.get_channel(config["welcome_channel_id"])
            if channel and isinstance(channel, discord.TextChannel):
                message = config.get("welcome_message") or f"Welcome {member.mention} to the server!"
                # Safe replacements
                message = message.replace("{user.mention}", member.mention)
                message = message.replace("{user.name}", member.name)
                message = message.replace("{user.discriminator}", member.discriminator or '0000')
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
                    img_url = str(config["welcome_image"])
                    if img_url.startswith(("http://", "https://")):
                        embed.set_image(url=img_url)
                    else:
                        logger.warning(f"Invalid welcome_image URL for guild {guild.id}: {img_url}")

                try:
                    if channel.permissions_for(guild.me).send_messages and channel.permissions_for(guild.me).embed_links:
                        await channel.send(embed=embed)
                    else:
                         logger.error(f"Missing send/embed permissions for welcome channel {channel.id} in guild {guild.id}")

                except Exception as e:
                    logger.error(f"Failed to send welcome message: {e}")


    @commands.Cog.listener("on_member_remove")
    async def handle_member_remove(self, member: discord.Member):
        """Sends a goodbye message when a member leaves, using cached config."""
        guild = member.guild
        logger.info(f"Member left: {member} ({member.id}) from guild {guild.name} ({guild.id})")

        config = await db_utils.get_guild_config(guild.id)

        if config and config.get("goodbye_channel_id"):
            channel = guild.get_channel(config["goodbye_channel_id"])
            if channel and isinstance(channel, discord.TextChannel):
                message = config.get("goodbye_message") or f"{member.display_name} has left the server."
                message = message.replace("{user.mention}", f"@{member.name}") 
                message = message.replace("{user.name}", member.name)
                message = message.replace("{user.discriminator}", member.discriminator or '0000')
                message = message.replace("{user.id}", str(member.id))
                message = message.replace("{server.name}", guild.name)
                message = message.replace("{member.count}", str(guild.member_count))

                embed = discord.Embed(
                    description=message,
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                avatar_url = member.display_avatar.url if member.display_avatar else None
                embed.set_author(name=f"Goodbye, {member.display_name}.", icon_url=avatar_url)
                if avatar_url:
                     embed.set_thumbnail(url=avatar_url)

                if config.get("goodbye_image"):
                    img_url = str(config["goodbye_image"])
                    if img_url.startswith(("http://", "https://")):
                        embed.set_image(url=img_url)
                    else:
                        logger.warning(f"Invalid goodbye_image URL for guild {guild.id}: {img_url}")

                try:
                    if channel.permissions_for(guild.me).send_messages and channel.permissions_for(guild.me).embed_links:
                        await channel.send(embed=embed)
                    else:
                         logger.error(f"Missing send/embed permissions for goodbye channel {channel.id} in guild {guild.id}")

                except Exception as e:
                    logger.error(f"Failed to send goodbye message: {e}")


async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(MemberEvents(bot))