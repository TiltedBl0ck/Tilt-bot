import discord
from discord.ext import commands, tasks
import logging
# Updated import - Added set_guild_config_value
from cogs.utils.db import pool, get_guild_config, set_guild_config_value

logger = logging.getLogger(__name__)

class MemberEventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_stats.start() # Start the background task

    def cog_unload(self):
        self.update_stats.cancel() # Stop the task when cog is unloaded

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        # Use the new helper function
        config = await get_guild_config(guild.id)

        # --- Welcome Message ---
        if config and config.get('welcome_channel_id'): # Use .get for safety
            channel_id = config['welcome_channel_id']
            channel = guild.get_channel(channel_id)
            if channel and isinstance(channel, discord.TextChannel): # Check if channel exists and is text
                welcome_message = config.get('welcome_message') or "Welcome {member} to {guild}!" # Default message
                try:
                    # Format the message (handle potential errors if keys are missing)
                    formatted_message = welcome_message.format(
                        member=member.mention,
                        user=member.display_name, # Alias for member
                        guild=guild.name,
                        member_count=guild.member_count
                    )
                    await channel.send(formatted_message)
                    logger.info(f"Sent welcome message for {member} in {guild.name}")
                except KeyError as e:
                     logger.warning(f"Invalid placeholder in welcome message for guild {guild.id}: {e}")
                     # Send a fallback message
                     await channel.send(f"Welcome {member.mention}!")
                except discord.Forbidden:
                    logger.warning(f"Missing permissions to send welcome message in {channel.name} (Guild: {guild.id})")
                except Exception as e:
                    logger.error(f"Error sending welcome message for {member} in {guild.name}: {e}")
            elif channel_id: # Only log warning if an ID was actually set but channel not found/valid
                 logger.warning(f"Welcome channel ID {channel_id} not found or not a text channel in guild {guild.id}.")
        
        # --- Update Stats (Trigger immediate update) ---
        await self.update_guild_stats(guild)


    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        # Use the new helper function
        config = await get_guild_config(guild.id)

        # --- Goodbye Message ---
        if config and config.get('goodbye_channel_id'): # Use .get for safety
            channel_id = config['goodbye_channel_id']
            channel = guild.get_channel(channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                goodbye_message = config.get('goodbye_message') or "Goodbye {member}. We'll miss you!"
                try:
                    formatted_message = goodbye_message.format(
                        member=member.display_name, # Can't mention user after they left
                        user=member.display_name, # Alias
                        guild=guild.name,
                        member_count=guild.member_count # Member count *before* they left
                    )
                    await channel.send(formatted_message)
                    logger.info(f"Sent goodbye message for {member} in {guild.name}")
                except KeyError as e:
                     logger.warning(f"Invalid placeholder in goodbye message for guild {guild.id}: {e}")
                     await channel.send(f"Goodbye {member.display_name}.")
                except discord.Forbidden:
                    logger.warning(f"Missing permissions to send goodbye message in {channel.name} (Guild: {guild.id})")
                except Exception as e:
                    logger.error(f"Error sending goodbye message for {member} in {guild.name}: {e}")
            elif channel_id: # Only log warning if an ID was actually set but channel not found/valid
                 logger.warning(f"Goodbye channel ID {channel_id} not found or not a text channel in guild {guild.id}.")

        # --- Update Stats (Trigger immediate update) ---
        await self.update_guild_stats(guild)


    # --- Server Stats Background Task ---
    @tasks.loop(minutes=10) # Update every 10 minutes
    async def update_stats(self):
        """Periodically updates the server stats channels for all configured guilds."""
        # Check if pool is ready before iterating
        if pool is None:
            logger.debug("Database pool not ready, skipping periodic stats update.")
            return
            
        logger.info("Running periodic server stats update...")
        # Make sure bot is ready and has guilds before proceeding
        if not self.bot.is_ready() or not self.bot.guilds:
             logger.info("Bot not ready or no guilds found, skipping periodic stats update cycle.")
             return
             
        for guild in self.bot.guilds:
            await self.update_guild_stats(guild)
        logger.info("Finished periodic server stats update.")

    @update_stats.before_loop
    async def before_update_stats(self):
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()
        logger.info("Starting background task: update_stats")


    async def update_guild_stats(self, guild: discord.Guild):
        """Updates the member and bot count channels for a specific guild."""
        if pool is None: # Check if db pool is ready
             logger.warning(f"Database pool not ready, skipping stats update for {guild.name} ({guild.id})")
             return

        # Use the new helper function
        config = await get_guild_config(guild.id)

        # If config is None (error fetching) or doesn't exist yet, we can't proceed
        if config is None:
            logger.debug(f"No config found or error fetching for guild {guild.name} ({guild.id}), skipping stats update.")
            return

        member_channel_id = config.get('member_count_channel')
        bot_channel_id = config.get('bot_count_channel')

        # Update Member Count Channel
        if member_channel_id:
            channel = guild.get_channel(member_channel_id)
            if channel and isinstance(channel, discord.VoiceChannel):
                try:
                    # Use guild.member_count which is usually cached and efficient
                    current_member_count = guild.member_count
                    if current_member_count is None: # Fallback if somehow not cached
                        current_member_count = len(guild.members)
                        
                    new_name = f"📊 Members: {current_member_count}"
                    if channel.name != new_name:
                         await channel.edit(name=new_name, reason="Update server stats")
                         logger.debug(f"Updated member count for {guild.name} to {current_member_count}")
                except discord.Forbidden:
                    logger.warning(f"Missing permissions to edit member stats channel {channel.id} in {guild.name}. Removing from config.")
                    await set_guild_config_value(guild.id, 'member_count_channel', None) # Remove invalid channel
                except discord.HTTPException as e:
                     logger.error(f"Failed to update member count channel for {guild.name}: {e}")
                except Exception as e: # Catch broader errors during edit
                    logger.error(f"Unexpected error updating member count channel {channel.id} for {guild.name}: {e}")
            else:
                 logger.warning(f"Member count channel {member_channel_id} not found or not a voice channel in {guild.name}. Removing from config.")
                 await set_guild_config_value(guild.id, 'member_count_channel', None) # Remove invalid channel


        # Update Bot Count Channel
        if bot_channel_id:
            channel = guild.get_channel(bot_channel_id)
            if channel and isinstance(channel, discord.VoiceChannel):
                try:
                    # Efficiently count bots using guild.members if available
                    bot_count = sum(1 for m in guild.members if m.bot)
                    new_name = f"🤖 Bots: {bot_count}"
                    if channel.name != new_name:
                        await channel.edit(name=new_name, reason="Update server stats")
                        logger.debug(f"Updated bot count for {guild.name} to {bot_count}")
                except discord.Forbidden:
                     logger.warning(f"Missing permissions to edit bot stats channel {channel.id} in {guild.name}. Removing from config.")
                     await set_guild_config_value(guild.id, 'bot_count_channel', None) # Remove invalid channel
                except discord.HTTPException as e:
                     logger.error(f"Failed to update bot count channel for {guild.name}: {e}")
                except Exception as e: # Catch broader errors during edit
                    logger.error(f"Unexpected error updating bot count channel {channel.id} for {guild.name}: {e}")
            else:
                 logger.warning(f"Bot count channel {bot_channel_id} not found or not a voice channel in {guild.name}. Removing from config.")
                 await set_guild_config_value(guild.id, 'bot_count_channel', None) # Remove invalid channel


async def setup(bot: commands.Bot):
    await bot.add_cog(MemberEventsCog(bot))

