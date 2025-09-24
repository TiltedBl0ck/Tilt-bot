"""
Management Commands Cog for Tilt-bot

This cog provides server management functionality including welcome/goodbye systems,
server statistics, and configuration management.

Author: TiltedBl0ck
Version: 2.0.0
"""

import logging
import discord
from discord import app_commands
from discord.ext import commands, tasks
from cogs.utils.db import get_db_connection
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# --- UI Components ---

class ChannelSetupView(discord.ui.View):
    """A view to handle setting up welcome/goodbye channels."""

    def __init__(self, setup_type: str):
        super().__init__(timeout=180)
        self.setup_type = setup_type

        self.channel_select = discord.ui.ChannelSelect(
            placeholder=f"Select a channel for {setup_type} messages...",
            channel_types=[discord.ChannelType.text],
            max_values=1
        )

        self.channel_select.callback = self.select_callback
        self.add_item(self.channel_select)

    async def update_database(self, interaction: discord.Interaction, channel_id: int):
        """Asynchronously updates the database with the selected channel ID."""
        conn = await get_db_connection()
        try:
            column = "welcome_channel_id" if self.setup_type == "welcome" else "goodbye_channel_id"
            await conn.execute(f"""
                INSERT INTO guild_config (guild_id, {column}) VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET {column}=excluded.{column}
            """, (interaction.guild.id, channel_id))
            await conn.commit()
        finally:
            await conn.close()

    @discord.ui.button(label='Create a New Channel', style=discord.ButtonStyle.success, row=0)
    async def create_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Creates a new text channel for welcome/goodbye messages."""
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(send_messages=False, view_channel=True),
            interaction.guild.me: discord.PermissionOverwrite(send_messages=True)
        }

        try:
            channel = await interaction.guild.create_text_channel(
                name=f'{self.setup_type}-log',
                overwrites=overwrites,
                reason=f"Tilt-bot {self.setup_type.capitalize()} channel setup"
            )

            await self.update_database(interaction, channel.id)
            await interaction.response.edit_message(
                content=f"✅ Successfully created {channel.mention} and set it as the {self.setup_type} channel.",
                view=None
            )

        except discord.Forbidden:
            await interaction.response.edit_message(content="❌ I don't have permission to create channels.", view=None)
        except Exception as e:
            logger.error(f"Error creating channel: {e}")
            await interaction.response.edit_message(content="❌ An error occurred while creating the channel.", view=None)

    async def select_callback(self, interaction: discord.Interaction):
        """Callback for when a user selects a channel from the dropdown."""
        channel = self.channel_select.values[0]
        await self.update_database(interaction, channel.id)
        await interaction.response.edit_message(
            content=f"✅ Successfully set {channel.mention} as the {self.setup_type} channel.",
            view=None
        )


class WelcomeConfigModal(discord.ui.Modal, title='Configure Welcome Message'):
    message = discord.ui.TextInput(
        label='Welcome Message', style=discord.TextStyle.paragraph,
        placeholder='Variables: {user.mention}, {user.name}, {guild.name}, {member.count}',
        default='Welcome {user.mention} to {guild.name}!', max_length=1024
    )

    image_url = discord.ui.TextInput(
        label='Welcome Image URL (Optional)', placeholder='https://example.com/welcome.png',
        required=False, max_length=512
    )

    async def on_submit(self, interaction: discord.Interaction):
        conn = await get_db_connection()
        try:
            await conn.execute("""
                INSERT INTO guild_config (guild_id, welcome_message, welcome_image) VALUES (?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                welcome_message=excluded.welcome_message,
                welcome_image=excluded.welcome_image
            """, (interaction.guild.id, self.message.value, self.image_url.value))
            await conn.commit()
        finally:
            await conn.close()
        await interaction.response.send_message('✅ Welcome configuration updated!', ephemeral=True)


class GoodbyeConfigModal(discord.ui.Modal, title='Configure Goodbye Message'):
    message = discord.ui.TextInput(
        label='Goodbye Message', style=discord.TextStyle.paragraph,
        placeholder='Variables: {user.name}, {guild.name}, {member.count}',
        default='{user.name} has left {guild.name}.', max_length=1024
    )

    image_url = discord.ui.TextInput(
        label='Goodbye Image URL (Optional)', placeholder='https://example.com/goodbye.png',
        required=False, max_length=512
    )

    async def on_submit(self, interaction: discord.Interaction):
        conn = await get_db_connection()
        try:
            await conn.execute("""
                INSERT INTO guild_config (guild_id, goodbye_message, goodbye_image) VALUES (?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                goodbye_message=excluded.goodbye_message,
                goodbye_image=excluded.goodbye_image
            """, (interaction.guild.id, self.message.value, self.image_url.value))
            await conn.commit()
        finally:
            await conn.close()
        await interaction.response.send_message('✅ Goodbye configuration updated!', ephemeral=True)


class Management(commands.Cog):
    """
    Management commands cog providing server setup and configuration tools.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_server_stats.start()

    def cog_unload(self):
        self.update_server_stats.cancel()

    @tasks.loop(minutes=10)
    async def update_server_stats(self):
        """Update server statistics channels every 10 minutes."""
        conn = None
        try:
            conn = await get_db_connection()
            async with conn.execute("SELECT * FROM guild_config WHERE setup_complete = 1") as cursor:
                configs = await cursor.fetchall()

            for row in configs:
                guild = self.bot.get_guild(row["guild_id"])
                if not guild: 
                    continue

                # Member Count
                if row["member_count_channel_id"]:
                    ch = guild.get_channel(row["member_count_channel_id"])
                    if ch: 
                        try:
                            await ch.edit(name=f"👥 Members: {guild.member_count}", reason="Server stats update")
                        except Exception as e:
                            logger.warning(f"Failed to update member count for {guild.name}: {e}")

                # Bot Count
                if row["bot_count_channel_id"]:
                    ch = guild.get_channel(row["bot_count_channel_id"])
                    bot_count = sum(1 for m in guild.members if m.bot)
                    if ch: 
                        try:
                            await ch.edit(name=f"🤖 Bots: {bot_count}", reason="Server stats update")
                        except Exception as e:
                            logger.warning(f"Failed to update bot count for {guild.name}: {e}")

        except Exception as e:
            logger.error(f"Error in update_server_stats loop: {e}")
        finally:
            if conn:
                await conn.close()

    @update_server_stats.before_loop
    async def before_update_server_stats(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Handle new member joins with welcome messages."""
        conn = None
        try:
            conn = await get_db_connection()
            async with conn.execute("SELECT * FROM guild_config WHERE guild_id = ?", (member.guild.id,)) as cursor:
                row = await cursor.fetchone()

            if row and row["welcome_channel_id"]:
                channel = member.guild.get_channel(row["welcome_channel_id"])
                if channel:
                    message = row["welcome_message"] or f"Welcome to **{member.guild.name}**, {member.mention}!"
                    message = message.replace("{user.mention}", member.mention)\
                                    .replace("{user.name}", member.name)\
                                    .replace("{guild.name}", member.guild.name)\
                                    .replace("{member.count}", str(member.guild.member_count))

                    embed = discord.Embed(
                        title="Welcome! 🎉", 
                        description=message, 
                        color=discord.Color.green(), 
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.set_thumbnail(url=member.display_avatar.url)
                    embed.set_footer(text=f"User ID: {member.id}")

                    if row["welcome_image"]:
                        embed.set_image(url=row["welcome_image"])

                    await channel.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in on_member_join: {e}")
        finally:
            if conn:
                await conn.close()

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Handle member leaves with goodbye messages."""
        conn = None
        try:
            conn = await get_db_connection()
            async with conn.execute("SELECT * FROM guild_config WHERE guild_id = ?", (member.guild.id,)) as cursor:
                row = await cursor.fetchone()

            if row and row["goodbye_channel_id"]:
                channel = member.guild.get_channel(row["goodbye_channel_id"])
                if channel:
                    message = row["goodbye_message"] or f"**{member.display_name}** has left the server."
                    message = message.replace("{user.name}", member.name)\
                                    .replace("{guild.name}", member.guild.name)\
                                    .replace("{member.count}", str(member.guild.member_count))

                    embed = discord.Embed(
                        title="Goodbye 👋", 
                        description=message, 
                        color=discord.Color.red(), 
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.set_thumbnail(url=member.display_avatar.url)
                    embed.set_footer(text=f"User ID: {member.id}")

                    if row["goodbye_image"]:
                        embed.set_image(url=row["goodbye_image"])

                    await channel.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in on_member_remove: {e}")
        finally:
            if conn:
                await conn.close()

    # --- Command Groups ---
    setup_group = app_commands.Group(name="setup", description="Setup commands for Tilt-bot")
    config_group = app_commands.Group(name="config", description="Configure bot settings")

    # --- Setup Commands ---
    @setup_group.command(name="welcome", description="Set up or remove the welcome message channel.")
    @app_commands.describe(action="Choose whether to set up or remove the channel.")
    @app_commands.choices(action=[
        app_commands.Choice(name="Set", value="set"), 
        app_commands.Choice(name="Unset", value="unset")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_welcome(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        if action.value == "set":
            view = ChannelSetupView(setup_type="welcome")
            await interaction.response.send_message("How would you like to set up the welcome channel?", view=view, ephemeral=True)
        else:  # unset
            conn = await get_db_connection()
            try:
                await conn.execute("UPDATE guild_config SET welcome_channel_id = NULL, welcome_message = NULL, welcome_image = NULL WHERE guild_id = ?", (interaction.guild.id,))
                await conn.commit()
            finally:
                await conn.close()
            await interaction.response.send_message("✅ Welcome channel has been successfully unset.", ephemeral=True)

    @setup_group.command(name="goodbye", description="Set up or remove the goodbye message channel.")
    @app_commands.describe(action="Choose whether to set up or remove the channel.")
    @app_commands.choices(action=[
        app_commands.Choice(name="Set", value="set"), 
        app_commands.Choice(name="Unset", value="unset")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_goodbye(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        if action.value == "set":
            view = ChannelSetupView(setup_type="goodbye")
            await interaction.response.send_message("How would you like to set up the goodbye channel?", view=view, ephemeral=True)
        else:  # unset
            conn = await get_db_connection()
            try:
                await conn.execute("UPDATE guild_config SET goodbye_channel_id = NULL, goodbye_message = NULL, goodbye_image = NULL WHERE guild_id = ?", (interaction.guild.id,))
                await conn.commit()
            finally:
                await conn.close()
            await interaction.response.send_message("✅ Goodbye channel has been successfully unset.", ephemeral=True)

    # --- Config Commands ---
    @config_group.command(name="welcome", description="Manage the welcome message and image.")
    @app_commands.describe(action="What do you want to do with the welcome config?")
    @app_commands.choices(action=[
        app_commands.Choice(name="Edit", value="edit"),
        app_commands.Choice(name="View", value="view"),
        app_commands.Choice(name="Delete", value="delete")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def config_welcome(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        conn = await get_db_connection()
        try:
            async with conn.execute("SELECT welcome_message, welcome_image FROM guild_config WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
                config = await cursor.fetchone()

            if action.value == "edit":
                await interaction.response.send_modal(WelcomeConfigModal())
            elif action.value == "view":
                if config and config["welcome_message"]:
                    embed = discord.Embed(title="Welcome Configuration", color=discord.Color.blue())
                    embed.add_field(name="Message", value=config["welcome_message"], inline=False)
                    if config["welcome_image"]:
                        embed.set_image(url=config["welcome_image"])
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message("Welcome message is not configured yet. Use `/config welcome edit` to set it up.", ephemeral=True)
            elif action.value == "delete":
                await conn.execute("UPDATE guild_config SET welcome_message = NULL, welcome_image = NULL WHERE guild_id = ?", (interaction.guild.id,))
                await conn.commit()
                await interaction.response.send_message("✅ Welcome message configuration has been deleted.", ephemeral=True)
        finally:
            await conn.close()

    @config_group.command(name="goodbye", description="Manage the goodbye message and image.")
    @app_commands.describe(action="What do you want to do with the goodbye config?")
    @app_commands.choices(action=[
        app_commands.Choice(name="Edit", value="edit"),
        app_commands.Choice(name="View", value="view"),
        app_commands.Choice(name="Delete", value="delete")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def config_goodbye(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        conn = await get_db_connection()
        try:
            async with conn.execute("SELECT goodbye_message, goodbye_image FROM guild_config WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
                config = await cursor.fetchone()

            if action.value == "edit":
                await interaction.response.send_modal(GoodbyeConfigModal())
            elif action.value == "view":
                if config and config["goodbye_message"]:
                    embed = discord.Embed(title="Goodbye Configuration", color=discord.Color.blue())
                    embed.add_field(name="Message", value=config["goodbye_message"], inline=False)
                    if config["goodbye_image"]:
                        embed.set_image(url=config["goodbye_image"])
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message("Goodbye message is not configured yet. Use `/config goodbye edit` to set it up.", ephemeral=True)
            elif action.value == "delete":
                await conn.execute("UPDATE guild_config SET goodbye_message = NULL, goodbye_image = NULL WHERE guild_id = ?", (interaction.guild.id,))
                await conn.commit()
                await interaction.response.send_message("✅ Goodbye message configuration has been deleted.", ephemeral=True)
        finally:
            await conn.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(Management(bot))
