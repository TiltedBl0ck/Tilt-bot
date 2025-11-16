import logging
import discord
from discord import app_commands
from discord.ext import commands
import json
import os

logger = logging.getLogger(__name__)

# Memory file path
MEMORY_FILE = "bot_memory.json"

class Memory(commands.Cog):
    """Bot personal memory and context management."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.memory = self.load_memory()

    def load_memory(self) -> dict:
        """Load bot memory from file."""
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                    logger.info(f"Loaded bot memory from {MEMORY_FILE}")
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading memory: {e}")
                return self.get_default_memory()
        return self.get_default_memory()

    def get_default_memory(self) -> dict:
        """Get default memory structure."""
        return {
            "bot_name": "Tilt-bot",
            "bot_description": "A custom Discord bot for TiltedBlock HQ",
            "personality": "helpful, friendly, and engaging",
            "owner": "TiltedBlock team",
            "server_name": "TiltedBlock HQ",
            "custom_facts": [],
            "system_prompt": ""
        }

    def save_memory(self):
        """Save bot memory to file."""
        try:
            with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.memory, f, indent=4, ensure_ascii=False)
            logger.info("Bot memory saved successfully")
        except Exception as e:
            logger.error(f"Error saving memory: {e}")

    def get_memory_context(self) -> str:
        """Build memory context string for AI."""
        lines = []
        
        lines.append(f"Bot Name: {self.memory.get('bot_name', 'Tilt-bot')}")
        lines.append(f"Description: {self.memory.get('bot_description', 'A custom Discord bot')}")
        lines.append(f"Personality: {self.memory.get('personality', 'helpful and friendly')}")
        lines.append(f"Owner/Creator: {self.memory.get('owner', 'Unknown')}")
        lines.append(f"Server: {self.memory.get('server_name', 'Unknown server')}")
        
        custom_facts = self.memory.get('custom_facts', [])
        if custom_facts:
            lines.append("\nAdditional Facts:")
            for fact in custom_facts:
                lines.append(f"- {fact}")
        
        system_prompt = self.memory.get('system_prompt', '')
        if system_prompt:
            lines.append(f"\nCustom Instructions: {system_prompt}")
        
        return "\n".join(lines)

    # Memory Management Commands
    @app_commands.group(name="memory", description="Manage bot memory and personal context")
    async def memory_group(self, interaction: discord.Interaction):
        """Memory management commands."""
        pass

    @memory_group.command(name="set-name", description="Set bot name")
    @app_commands.describe(name="Bot name")
    async def set_name(self, interaction: discord.Interaction, name: str):
        """Set the bot's name."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only admins can modify bot memory.", ephemeral=True)
            return
        
        self.memory['bot_name'] = name
        self.save_memory()
        await interaction.response.send_message(f"✅ Bot name set to: **{name}**", ephemeral=True)

    @memory_group.command(name="set-description", description="Set bot description")
    @app_commands.describe(description="Bot description")
    async def set_description(self, interaction: discord.Interaction, description: str):
        """Set the bot's description."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only admins can modify bot memory.", ephemeral=True)
            return
        
        self.memory['bot_description'] = description
        self.save_memory()
        await interaction.response.send_message(f"✅ Bot description updated: **{description}**", ephemeral=True)

    @memory_group.command(name="set-personality", description="Set bot personality")
    @app_commands.describe(personality="Bot personality traits")
    async def set_personality(self, interaction: discord.Interaction, personality: str):
        """Set the bot's personality."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only admins can modify bot memory.", ephemeral=True)
            return
        
        self.memory['personality'] = personality
        self.save_memory()
        await interaction.response.send_message(f"✅ Bot personality set to: **{personality}**", ephemeral=True)

    @memory_group.command(name="set-owner", description="Set bot owner/creator")
    @app_commands.describe(owner="Owner or creator name")
    async def set_owner(self, interaction: discord.Interaction, owner: str):
        """Set the bot's owner."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only admins can modify bot memory.", ephemeral=True)
            return
        
        self.memory['owner'] = owner
        self.save_memory()
        await interaction.response.send_message(f"✅ Bot owner set to: **{owner}**", ephemeral=True)

    @memory_group.command(name="set-server", description="Set server name")
    @app_commands.describe(server_name="Server name")
    async def set_server(self, interaction: discord.Interaction, server_name: str):
        """Set the server name."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only admins can modify bot memory.", ephemeral=True)
            return
        
        self.memory['server_name'] = server_name
        self.save_memory()
        await interaction.response.send_message(f"✅ Server name set to: **{server_name}**", ephemeral=True)

    @memory_group.command(name="add-fact", description="Add custom fact about bot")
    @app_commands.describe(fact="Custom fact")
    async def add_fact(self, interaction: discord.Interaction, fact: str):
        """Add a custom fact."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only admins can modify bot memory.", ephemeral=True)
            return
        
        self.memory['custom_facts'].append(fact)
        self.save_memory()
        await interaction.response.send_message(f"✅ Fact added: **{fact}**", ephemeral=True)

    @memory_group.command(name="remove-fact", description="Remove custom fact")
    @app_commands.describe(index="Fact number to remove (view with /memory show)")
    async def remove_fact(self, interaction: discord.Interaction, index: int):
        """Remove a custom fact by index."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only admins can modify bot memory.", ephemeral=True)
            return
        
        facts = self.memory['custom_facts']
        if 0 <= index - 1 < len(facts):
            removed = facts.pop(index - 1)
            self.save_memory()
            await interaction.response.send_message(f"✅ Removed fact: **{removed}**", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Invalid fact number.", ephemeral=True)

    @memory_group.command(name="set-prompt", description="Set custom system prompt")
    @app_commands.describe(prompt="System prompt instructions")
    async def set_prompt(self, interaction: discord.Interaction, prompt: str):
        """Set custom system prompt for AI."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only admins can modify bot memory.", ephemeral=True)
            return
        
        self.memory['system_prompt'] = prompt
        self.save_memory()
        await interaction.response.send_message(f"✅ System prompt updated.", ephemeral=True)

    @memory_group.command(name="show", description="Display bot memory")
    async def show_memory(self, interaction: discord.Interaction):
        """Display current bot memory."""
        memory_text = self.get_memory_context()
        
        embed = discord.Embed(
            title="🧠 Bot Memory",
            description=memory_text,
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @memory_group.command(name="reset", description="Reset memory to defaults")
    async def reset_memory(self, interaction: discord.Interaction):
        """Reset memory to default values."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only admins can modify bot memory.", ephemeral=True)
            return
        
        self.memory = self.get_default_memory()
        self.save_memory()
        await interaction.response.send_message("✅ Bot memory reset to defaults.", ephemeral=True)


async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(Memory(bot))