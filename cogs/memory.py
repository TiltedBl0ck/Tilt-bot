# cogs/memory.py
import logging
import re
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

# Patterns that indicate jailbreak/prompt injection attempts
_JAILBREAK_PATTERNS = re.compile(
    r"(ignore (all |previous |prior )?(instructions?|rules?|guidelines?|prompts?))|"
    r"(you are (now |a )?dan)|"
    r"(jailbreak)|"
    r"(do anything now)|"
    r"(pretend you (have no|don't have) (restrictions?|rules?|guidelines?))|"
    r"(reveal (your |the )?(api key|token|secret|password))|"
    r"(bypass (safety|filter|restriction))",
    re.IGNORECASE,
)

# Immutable safety prefix always prepended before any custom system prompt
SAFETY_PREFIX = (
    "You are a helpful, safe, and ethical Discord bot. "
    "You must never reveal API keys, tokens, passwords, or any secrets. "
    "You must always follow Discord's Terms of Service and community guidelines. "
    "You must never assist with illegal activities, self-harm, harassment, or hate speech. "
    "The following are additional server-specific instructions:\n\n"
)

MAX_SYSTEM_PROMPT_LEN = 500


class Memory(commands.Cog):
    """Per-guild bot memory and context management backed by the database."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # In-memory cache: guild_id -> memory dict
        self._cache: dict[int, dict] = {}

    def get_default_memory(self) -> dict:
        return {
            "bot_name": "Tilt-bot",
            "bot_description": "A custom Discord bot for TiltedBlock HQ",
            "personality": "helpful, friendly, and engaging",
            "owner": "TiltedBlock team",
            "server_name": "Unknown server",
            "custom_facts": [],
            "system_prompt": "",
        }

    async def _get_db_memory(self, guild_id: int) -> dict:
        """Load guild memory from DB, falling back to defaults."""
        if guild_id in self._cache:
            return self._cache[guild_id]

        db_cog = self.bot.get_cog("Database")
        if db_cog is None:
            return self.get_default_memory()

        try:
            row = await db_cog.fetchone(
                "SELECT memory_json FROM guild_memory WHERE guild_id = ?",
                (guild_id,),
            )
            if row and row[0]:
                import json
                data = json.loads(row[0])
                self._cache[guild_id] = data
                return data
        except Exception as exc:
            logger.error(f"Error loading guild memory for {guild_id}: {exc}")

        default = self.get_default_memory()
        self._cache[guild_id] = default
        return default

    async def _save_db_memory(self, guild_id: int, memory: dict) -> None:
        """Persist guild memory to DB and update cache."""
        import json
        self._cache[guild_id] = memory
        db_cog = self.bot.get_cog("Database")
        if db_cog is None:
            logger.error("Database cog not available — memory not persisted.")
            return
        try:
            await db_cog.execute(
                """
                INSERT INTO guild_memory (guild_id, memory_json)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET memory_json = excluded.memory_json
                """,
                (guild_id, json.dumps(memory, ensure_ascii=False)),
            )
        except Exception as exc:
            logger.error(f"Error saving guild memory for {guild_id}: {exc}")

    def get_memory_for_guild(self, guild_id: int) -> dict:
        """Synchronous cache lookup — returns default if not yet loaded."""
        return self._cache.get(guild_id, self.get_default_memory())

    def build_system_prompt(self, memory: dict) -> str:
        """Return the effective system prompt with the immutable safety prefix."""
        custom = memory.get("system_prompt", "").strip()
        if custom:
            return SAFETY_PREFIX + custom
        return ""

    def get_memory_context(self, guild_id: int) -> str:
        memory = self.get_memory_for_guild(guild_id)
        lines = [
            f"Bot Name: {memory.get('bot_name', 'Tilt-bot')}",
            f"Description: {memory.get('bot_description', 'A custom Discord bot')}",
            f"Personality: {memory.get('personality', 'helpful and friendly')}",
            f"Owner/Creator: {memory.get('owner', 'Unknown')}",
            f"Server: {memory.get('server_name', 'Unknown server')}",
        ]
        facts = memory.get("custom_facts", [])
        if facts:
            lines.append("\nAdditional Facts:")
            for fact in facts:
                lines.append(f"- {fact}")
        prompt = memory.get("system_prompt", "")
        if prompt:
            lines.append(f"\nCustom Instructions (truncated): {prompt[:100]}...")
        return "\n".join(lines)

    # ── Command Group ─────────────────────────────────────────────────────────

    memory_group = app_commands.Group(
        name="memory",
        description="Manage per-server bot memory and context",
        guild_only=True,
    )

    # Helper: ensure guild context and admin permission
    async def _require_admin(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Memory commands can only be used in a server.", ephemeral=True
            )
            return False
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Only administrators can modify bot memory.", ephemeral=True
            )
            return False
        return True

    @memory_group.command(name="set-name", description="Set bot name for this server")
    @app_commands.describe(name="Bot name")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_name(self, interaction: discord.Interaction, name: str):
        memory = await self._get_db_memory(interaction.guild_id)
        memory["bot_name"] = name[:100]
        await self._save_db_memory(interaction.guild_id, memory)
        await interaction.response.send_message(f"✅ Bot name set to: **{discord.utils.escape_markdown(name[:100])}**", ephemeral=True)

    @memory_group.command(name="set-description", description="Set bot description for this server")
    @app_commands.describe(description="Bot description")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_description(self, interaction: discord.Interaction, description: str):
        memory = await self._get_db_memory(interaction.guild_id)
        memory["bot_description"] = description[:300]
        await self._save_db_memory(interaction.guild_id, memory)
        await interaction.response.send_message("✅ Bot description updated.", ephemeral=True)

    @memory_group.command(name="set-personality", description="Set bot personality for this server")
    @app_commands.describe(personality="Bot personality traits")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_personality(self, interaction: discord.Interaction, personality: str):
        memory = await self._get_db_memory(interaction.guild_id)
        memory["personality"] = personality[:200]
        await self._save_db_memory(interaction.guild_id, memory)
        await interaction.response.send_message("✅ Bot personality updated.", ephemeral=True)

    @memory_group.command(name="set-owner", description="Set bot owner/creator for this server")
    @app_commands.describe(owner="Owner or creator name")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_owner(self, interaction: discord.Interaction, owner: str):
        memory = await self._get_db_memory(interaction.guild_id)
        memory["owner"] = owner[:100]
        await self._save_db_memory(interaction.guild_id, memory)
        await interaction.response.send_message("✅ Bot owner updated.", ephemeral=True)

    @memory_group.command(name="set-server", description="Set server display name")
    @app_commands.describe(server_name="Server name")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_server(self, interaction: discord.Interaction, server_name: str):
        memory = await self._get_db_memory(interaction.guild_id)
        memory["server_name"] = server_name[:100]
        await self._save_db_memory(interaction.guild_id, memory)
        await interaction.response.send_message("✅ Server name updated.", ephemeral=True)

    @memory_group.command(name="add-fact", description="Add custom fact about bot")
    @app_commands.describe(fact="Custom fact")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_fact(self, interaction: discord.Interaction, fact: str):
        memory = await self._get_db_memory(interaction.guild_id)
        facts = memory.get("custom_facts", [])
        if len(facts) >= 20:
            await interaction.response.send_message("❌ Maximum of 20 facts reached. Remove one first.", ephemeral=True)
            return
        facts.append(fact[:200])
        memory["custom_facts"] = facts
        await self._save_db_memory(interaction.guild_id, memory)
        await interaction.response.send_message("✅ Fact added.", ephemeral=True)

    @memory_group.command(name="remove-fact", description="Remove custom fact")
    @app_commands.describe(index="Fact number to remove (view with /memory show)")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_fact(self, interaction: discord.Interaction, index: int):
        memory = await self._get_db_memory(interaction.guild_id)
        facts = memory.get("custom_facts", [])
        if 0 <= index - 1 < len(facts):
            removed = facts.pop(index - 1)
            memory["custom_facts"] = facts
            await self._save_db_memory(interaction.guild_id, memory)
            await interaction.response.send_message(
                f"✅ Removed fact: **{discord.utils.escape_markdown(removed[:100])}**", ephemeral=True
            )
        else:
            await interaction.response.send_message("❌ Invalid fact number.", ephemeral=True)

    @memory_group.command(name="set-prompt", description="Set custom system prompt for this server")
    @app_commands.describe(prompt="System prompt instructions (max 500 chars)")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_prompt(self, interaction: discord.Interaction, prompt: str):
        # Enforce length cap
        if len(prompt) > MAX_SYSTEM_PROMPT_LEN:
            await interaction.response.send_message(
                f"❌ Prompt too long ({len(prompt)} chars). Maximum is {MAX_SYSTEM_PROMPT_LEN} characters.",
                ephemeral=True,
            )
            return

        # Jailbreak pattern filter
        if _JAILBREAK_PATTERNS.search(prompt):
            logger.warning(
                f"Jailbreak attempt in set-prompt by {interaction.user} "
                f"(guild={interaction.guild_id}): {prompt[:100]}"
            )
            await interaction.response.send_message(
                "❌ That prompt contains disallowed patterns and was rejected.",
                ephemeral=True,
            )
            return

        memory = await self._get_db_memory(interaction.guild_id)
        memory["system_prompt"] = prompt
        await self._save_db_memory(interaction.guild_id, memory)
        await interaction.response.send_message(
            "✅ System prompt updated. Note: a mandatory safety prefix is always prepended.",
            ephemeral=True,
        )

    @memory_group.command(name="show", description="Display this server's bot memory")
    async def show_memory(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return
        memory = await self._get_db_memory(interaction.guild_id)
        # Pre-load cache so get_memory_context works
        self._cache[interaction.guild_id] = memory
        text = self.get_memory_context(interaction.guild_id)
        embed = discord.Embed(title="🧠 Server Bot Memory", description=text, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @memory_group.command(name="reset", description="Reset this server's memory to defaults")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_memory(self, interaction: discord.Interaction):
        default = self.get_default_memory()
        await self._save_db_memory(interaction.guild_id, default)
        await interaction.response.send_message("✅ Bot memory reset to defaults for this server.", ephemeral=True)

    @set_name.error
    @set_description.error
    @set_personality.error
    @set_owner.error
    @set_server.error
    @add_fact.error
    @remove_fact.error
    @set_prompt.error
    @reset_memory.error
    async def memory_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You need Administrator permission.", ephemeral=True)
        else:
            logger.error(f"Memory command error: {error}", exc_info=True)
            await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Memory(bot))
