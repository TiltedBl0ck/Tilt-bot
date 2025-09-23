import discord
from discord import app_commands
from discord.ext import commands, tasks
from .utils.db import get_db_connection
from datetime import datetime, timezone

# --- UI Components ---

class ChannelSetupView(discord.ui.View):
    """A view to handle setting up welcome/goodbye channels."""
    def __init__(self, setup_type: str):
        super().__init__(timeout=180)
        self.setup_type = setup_type
        self.channel_select = discord.ui.ChannelSelect(
            placeholder=f"Select an existing channel for {setup_type} messages...",
            channel_types=[discord.ChannelType.text],
            max_values=1
        )
        self.channel_select.callback = self.select_callback
        self.add_item(self.channel_select)

    async def update_database(self, interaction: discord.Interaction, channel_id: int):
        conn = get_db_connection()
        cur = conn.cursor()
        column = "welcome_channel_id" if self.setup_type == "welcome" else "goodbye_channel_id"
        cur.execute(f"""
            INSERT INTO guild_config (guild_id, {column}) VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET {column}=excluded.{column}
        """, (interaction.guild.id, channel_id))
        conn.commit()
        conn.close()

    @discord.ui.button(label='Create a New Channel', style=discord.ButtonStyle.success, row=0)
    async def create_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(send_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(send_messages=True)
        }
        try:
            channel = await interaction.guild.create_text_channel(
                f'{self.setup_type}-messages',
                overwrites=overwrites,
                reason=f"{self.setup_type.capitalize()} channel setup"
            )
            await self.update_database(interaction, channel.id)
            await interaction.response.edit_message(
                content=f"✅ Successfully created {channel.mention} and set it as the {self.setup_type} channel.",
                view=None
            )
        except discord.Forbidden:
            await interaction.response.edit_message(
                content="❌ I don't have permission to create channels.", view=None
            )
        except Exception as e:
            print(f"Error creating channel: {e}")
            await interaction.response.edit_message(
                content="❌ An error occurred while creating the channel.", view=None
            )

    async def select_callback(self, interaction: discord.Interaction):
        channel = self.channel_select.values[0]
        await self.update_database(interaction, channel.id)
        await interaction.response.edit_message(
            content=f"✅ Successfully set {channel.mention} as the {self.setup_type} channel.",
            view=None
        )

class WelcomeConfigModal(discord.ui.Modal, title='Configure Welcome Message'):
    message = discord.ui.TextInput(
        label='Welcome Message',
        style=discord.TextStyle.paragraph,
        placeholder='Use {user.mention}, {user.name}, {guild.name}, {member.count}',
        default='Welcome {user.mention} to {guild.name}!',
        max_length=1024,
    )
    image_url = discord.ui.TextInput(
        label='Welcome Image URL (Optional)',
        placeholder='https://example.com/welcome.png',
        required=False,
        max_length=512,
    )

    async def on_submit(self, interaction: discord.Interaction):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO guild_config (guild_id, welcome_message, welcome_image) VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                welcome_message=excluded.welcome_message,
                welcome_image=excluded.welcome_image
        """, (interaction.guild.id, self.message.value, self.image_url.value))
        conn.commit()
        conn.close()
        await interaction.response.send_message('✅ Welcome configuration updated!', ephemeral=True)

class GoodbyeConfigModal(discord.ui.Modal, title='Configure Goodbye Message'):
    message = discord.ui.TextInput(
        label='Goodbye Message',
        style=discord.TextStyle.paragraph,
        placeholder='Use {user.name}, {guild.name}, {member.count}',
        default='{user.name} has left {guild.name}.',
        max_length=1024,
    )
    image_url = discord.ui.TextInput(
        label='Goodbye Image URL (Optional)',
        placeholder='https://example.com/goodbye.png',
        required=False,
        max_length=512,
    )

    async def on_submit(self, interaction: discord.Interaction):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO guild_config (guild_id, goodbye_message, goodbye_image) VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                goodbye_message=excluded.goodbye_message,
                goodbye_image=excluded.goodbye_image
        """, (interaction.guild.id, self.message.value, self.image_url.value))
        conn.commit()
        conn.close()
        await interaction.response.send_message('✅ Goodbye configuration updated!', ephemeral=True)

class Management(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_server_stats.start()

    def cog_unload(self):
        self.update_server_stats.cancel()

    @tasks.loop(minutes=10)
    async def update_server_stats(self):
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT guild_id, member_count_channel_id, bot_count_channel_id,
                       role_count_channel_id, channel_count_channel_id
                FROM guild_config
                WHERE setup_complete = 1
            """)
            configs = cur.fetchall()
            conn.close()

            for row in configs:
                guild = self.bot.get_guild(row["guild_id"])
                if not guild: continue

                # Update member count
                if row["member_count_channel_id"]:
                    ch = guild.get_channel(row["member_count_channel_id"])
                    if ch:
                        try: await ch.edit(name=f"👥 Members: {guild.member_count}")
                        except: pass
                # ... other counters ...
        except Exception as e:
            print(f"Error in update_server_stats: {e}")
        
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM guild_config WHERE guild_id = ?", (member.guild.id,))
            row = cur.fetchone()
            conn.close()

            if row and row["welcome_channel_id"]:
                channel = member.guild.get_channel(row["welcome_channel_id"])
                if channel:
                    message = row["welcome_message"] or f"Welcome to **{member.guild.name}**, {member.mention}!"
                    message = message.replace("{user.mention}", member.mention).replace("{user.name}", member.name).replace("{guild.name}", member.guild.name).replace("{member.count}", str(member.guild.member_count))
                    embed = discord.Embed(title="Welcome! 🎉", description=message, color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
                    embed.set_thumbnail(url=member.display_avatar.url)
                    embed.set_footer(text=f"User ID: {member.id}")
                    if row["welcome_image"]:
                        embed.set_image(url=row["welcome_image"])
                    await channel.send(embed=embed)
        except Exception as e:
            print(f"Error in on_member_join: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM guild_config WHERE guild_id = ?", (member.guild.id,))
            row = cur.fetchone()
            conn.close()

            if row and row["goodbye_channel_id"]:
                channel = member.guild.get_channel(row["goodbye_channel_id"])
                if channel:
                    message = row["goodbye_message"] or f"**{member.display_name}** has left the server."
                    message = message.replace("{user.name}", member.name).replace("{guild.name}", member.guild.name).replace("{member.count}", str(member.guild.member_count))
                    embed = discord.Embed(title="Goodbye 👋", description=message, color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
                    embed.set_thumbnail(url=member.display_avatar.url)
                    embed.set_footer(text=f"User ID: {member.id}")
                    if row["goodbye_image"]:
                        embed.set_image(url=row["goodbye_image"])
                    await channel.send(embed=embed)
        except Exception as e:
            print(f"Error in on_member_remove: {e}")

    # --- Command Groups ---
    setup_group = app_commands.Group(name="setup", description="Setup commands for Tilt-bot")
    config_group = app_commands.Group(name="config", description="Configure bot settings")

    # --- Setup Commands ---
    @setup_group.command(name="welcome", description="Set up or remove the welcome message channel.")
    @app_commands.describe(action="Choose whether to set up or remove the channel.")
    @app_commands.choices(action=[app_commands.Choice(name="Set", value="set"), app_commands.Choice(name="Unset", value="unset")])
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_welcome(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        if action.value == "set":
            view = ChannelSetupView(setup_type="welcome")
            await interaction.response.send_message("How would you like to set up the welcome channel?", view=view, ephemeral=True)
        elif action.value == "unset":
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("UPDATE guild_config SET welcome_channel_id = NULL, welcome_message = NULL, welcome_image = NULL WHERE guild_id = ?", (interaction.guild.id,))
            conn.commit()
            conn.close()
            await interaction.response.send_message("✅ Welcome channel has been successfully unset.", ephemeral=True)

    @setup_group.command(name="goodbye", description="Set up or remove the goodbye message channel.")
    @app_commands.describe(action="Choose whether to set up or remove the channel.")
    @app_commands.choices(action=[app_commands.Choice(name="Set", value="set"), app_commands.Choice(name="Unset", value="unset")])
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_goodbye(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        if action.value == "set":
            view = ChannelSetupView(setup_type="goodbye")
            await interaction.response.send_message("How would you like to set up the goodbye channel?", view=view, ephemeral=True)
        elif action.value == "unset":
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("UPDATE guild_config SET goodbye_channel_id = NULL, goodbye_message = NULL, goodbye_image = NULL WHERE guild_id = ?", (interaction.guild.id,))
            conn.commit()
            conn.close()
            await interaction.response.send_message("✅ Goodbye channel has been successfully unset.", ephemeral=True)
            
    @setup_group.command(name="serverstats", description="Set up or remove the server stats counters.")
    @app_commands.describe(action="Choose whether to set up or remove the server stats.")
    @app_commands.choices(action=[app_commands.Choice(name="Set", value="set"), app_commands.Choice(name="Unset", value="unset")])
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_serverstats(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        # ... (Full command implementation) ...
        pass

    # --- Config Commands ---
    @config_group.command(name="welcome", description="Manage the welcome message and image.")
    @app_commands.describe(action="Action to perform on the welcome configuration.")
    @app_commands.choices(action=[app_commands.Choice(name="Edit", value="edit"), app_commands.Choice(name="View", value="view"), app_commands.Choice(name="Delete", value="delete")])
    @app_commands.checks.has_permissions(administrator=True)
    async def config_welcome(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        # ... (Full command implementation) ...
        pass

    @config_group.command(name="goodbye", description="Manage the goodbye message and image.")
    @app_commands.describe(action="Action to perform on the goodbye configuration.")
    @app_commands.choices(action=[app_commands.Choice(name="Edit", value="edit"), app_commands.Choice(name="View", value="view"), app_commands.Choice(name="Delete", value="delete")])
    @app_commands.checks.has_permissions(administrator=True)
    async def config_goodbye(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        # ... (Full command implementation) ...
        pass
        
    @config_group.command(name="serverstats", description="Manage server stats system")
    @app_commands.describe(action="Action to perform")
    @app_commands.choices(action=[app_commands.Choice(name="View", value="view"), app_commands.Choice(name="Reset", value="reset")])
    @app_commands.checks.has_permissions(administrator=True)
    async def config_serverstats(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        # ... (Full command implementation) ...
        pass

async def setup(bot: commands.Bot):
    await bot.add_cog(Management(bot))

