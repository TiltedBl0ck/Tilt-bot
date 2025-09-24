"""
Professional Help Command Cog for Tilt-bot

This module implements a dynamic, self-updating help command that uses introspection
to automatically discover and display all registered slash commands. The implementation
follows enterprise-grade architectural patterns with proper error handling, logging,
and configuration management.

Author: TiltedBl0ck
Version: 2.0.0
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

import discord
from discord import app_commands
from discord.ext import commands

# Configure module-level logger
logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Custom exception for configuration-related errors."""
    pass


class Help(commands.Cog):
    """
    Dynamic Help Command Cog for Tilt-bot.

    This cog provides a sophisticated, self-updating help command that dynamically
    introspects the bot's command tree to display available commands. It loads
    configuration from external files and implements enterprise-grade error handling.

    Attributes:
        bot (commands.Bot): The Discord bot instance
        config (Dict[str, Any]): Loaded configuration data
        config_path (Path): Path to the configuration file
    """

    def __init__(self, bot: commands.Bot) -> None:
        """
        Initialize the Help cog with configuration loading and validation.

        Args:
            bot (commands.Bot): The Discord bot instance

        Raises:
            ConfigurationError: If configuration file cannot be loaded or is invalid
        """
        self.bot: commands.Bot = bot
        self.config_path: Path = Path(__file__).parent.parent / "config.json"
        self.config: Dict[str, Any] = {}

        # Load configuration on initialization
        self._load_configuration()

        logger.info(f"Help cog initialized successfully for {self.config['bot']['name']}")

    def _load_configuration(self) -> None:
        """
        Load and validate configuration from config.json.

        Raises:
            ConfigurationError: If configuration file is missing or invalid
        """
        try:
            if not self.config_path.exists():
                # Create default config if it doesn't exist
                default_config = {
                    "bot": {
                        "name": "Tilt-bot",
                        "version": "2.0.0",
                        "description": "A comprehensive Discord bot providing moderation, utility, AI chat, and server management features.",
                        "repository_url": "https://github.com/TiltedBl0ck/Tilt-bot",
                        "author": "TiltedBl0ck",
                        "support_server": "https://discord.gg/example"
                    }
                }
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, indent=4)
                logger.info("Created default configuration file")

            with open(self.config_path, 'r', encoding='utf-8') as config_file:
                self.config = json.load(config_file)

            # Validate required configuration keys
            required_keys = ['bot']
            for key in required_keys:
                if key not in self.config:
                    raise ConfigurationError(f"Missing required configuration key: {key}")

            # Validate bot configuration
            bot_config = self.config['bot']
            required_bot_keys = ['name', 'version', 'description']
            for key in required_bot_keys:
                if key not in bot_config:
                    raise ConfigurationError(f"Missing required bot configuration key: {key}")

            logger.info("Configuration loaded and validated successfully")

        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in configuration file: {e}")
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration: {e}")

    def _get_command_tree_commands(self) -> List[app_commands.AppCommand]:
        """
        Introspect the bot's command tree to get all registered global slash commands.

        Returns:
            List[app_commands.AppCommand]: List of registered application commands
        """
        try:
            commands = []

            # Get all global commands from the command tree
            if hasattr(self.bot.tree, '_global_commands'):
                for command in self.bot.tree._global_commands.values():
                    # Filter out owner-only or private commands if needed
                    if not getattr(command, '_private', False):
                        commands.append(command)

            # Sort commands alphabetically by name
            commands.sort(key=lambda x: x.name)

            logger.debug(f"Discovered {len(commands)} commands via introspection")
            return commands

        except Exception as e:
            logger.warning(f"Failed to introspect command tree: {e}")
            return []

    def _format_commands_list(self, commands: List[app_commands.AppCommand]) -> str:
        """
        Format the list of commands into a readable string for the embed.

        Args:
            commands (List[app_commands.AppCommand]): List of commands to format

        Returns:
            str: Formatted command list string
        """
        if not commands:
            return "No commands available."

        formatted_commands = []

        # Group commands by category
        utility_commands = []
        moderation_commands = []
        setup_commands = []
        config_commands = []
        ai_commands = []
        other_commands = []

        for command in commands[:25]:  # Limit to prevent embed size issues
            command_name = command.name
            description = command.description or "No description available"

            if command_name in ['serverinfo', 'userinfo', 'avatar', 'ping', 'botinfo', 'invite']:
                utility_commands.append(f"**`/{command_name}`** - {description}")
            elif command_name in ['clear']:
                moderation_commands.append(f"**`/{command_name}`** - {description}")
            elif command_name.startswith('setup'):
                setup_commands.append(f"**`/{command_name}`** - {description}")
            elif command_name.startswith('config'):
                config_commands.append(f"**`/{command_name}`** - {description}")
            elif command_name in ['chat']:
                ai_commands.append(f"**`/{command_name}`** - {description}")
            else:
                other_commands.append(f"**`/{command_name}`** - {description}")

        result_parts = []

        if utility_commands:
            result_parts.append("**🛠️ Utility Commands**\n" + "\n".join(utility_commands))

        if moderation_commands:
            result_parts.append("**🛡️ Moderation Commands**\n" + "\n".join(moderation_commands))

        if setup_commands:
            result_parts.append("**⚙️ Setup Commands**\n" + "\n".join(setup_commands))

        if config_commands:
            result_parts.append("**🔧 Configuration Commands**\n" + "\n".join(config_commands))

        if ai_commands:
            result_parts.append("**🤖 AI Commands**\n" + "\n".join(ai_commands))

        if other_commands:
            result_parts.append("**📋 Other Commands**\n" + "\n".join(other_commands))

        return "\n\n".join(result_parts)

    def _create_help_embed(self) -> discord.Embed:
        """
        Create a sophisticated help embed with dynamic content.

        Returns:
            discord.Embed: The constructed help embed
        """
        bot_config = self.config['bot']

        # Create embed with dynamic title
        embed = discord.Embed(
            title=f"📚 {self.bot.user.name} Help & Commands",
            description=bot_config['description'],
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )

        # Set thumbnail to bot's avatar
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        # Add version field
        embed.add_field(
            name="🔧 Version",
            value=f"`{bot_config['version']}`",
            inline=True
        )

        # Add author field if available
        if 'author' in bot_config:
            embed.add_field(
                name="👨‍💻 Developer", 
                value=bot_config['author'],
                inline=True
            )

        # Add server count
        embed.add_field(
            name="🌐 Servers",
            value=f"`{len(self.bot.guilds)}`",
            inline=True
        )

        # Dynamically generate commands list
        commands = self._get_command_tree_commands()
        commands_text = self._format_commands_list(commands)

        embed.add_field(
            name=f"📋 Available Commands ({len(commands)})",
            value=commands_text,
            inline=False
        )

        # Add repository link if available
        if 'repository_url' in bot_config:
            embed.add_field(
                name="📖 Links",
                value=f"[GitHub Repository]({bot_config['repository_url']})",
                inline=True
            )

        # Add support server if available
        if 'support_server' in bot_config:
            embed.add_field(
                name="💬 Support",
                value=f"[Join Support Server]({bot_config['support_server']})",
                inline=True
            )

        # Add latency to footer
        latency_ms = round(self.bot.latency * 1000)
        embed.set_footer(
            text=f"Responding in {latency_ms}ms • {bot_config['name']} v{bot_config['version']}",
            icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None
        )

        return embed

    @app_commands.command(
        name="help",
        description="Display information about the bot and available commands"
    )
    async def help_command(self, interaction: discord.Interaction) -> None:
        """
        Dynamic help slash command that displays bot information and available commands.

        This command uses introspection to automatically discover all registered
        slash commands and presents them in a professional embed format. The command
        is ephemeral to prevent channel spam and includes comprehensive error handling.

        Args:
            interaction (discord.Interaction): The Discord interaction object

        Returns:
            None: Sends an ephemeral response to the user
        """
        try:
            logger.info(f"Help command invoked by {interaction.user} ({interaction.user.id})")

            # Create the dynamic help embed
            embed = self._create_help_embed()

            # Send ephemeral response to prevent channel spam
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )

            logger.info(f"Help command successfully responded to {interaction.user}")

        except discord.HTTPException as e:
            logger.error(f"Discord HTTP error in help command: {e}")

            # Attempt to send a simplified error message
            try:
                await interaction.response.send_message(
                    "❌ An error occurred while generating the help message. "
                    "Please try again later or contact support.",
                    ephemeral=True
                )
            except discord.HTTPException:
                logger.critical("Failed to send error message to user")

        except Exception as e:
            logger.error(f"Unexpected error in help command: {e}", exc_info=True)

            # Attempt to send a generic error message
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An unexpected error occurred. Please contact the bot administrator.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ An unexpected error occurred. Please contact the bot administrator.",
                        ephemeral=True
                    )
            except Exception:
                logger.critical("Complete failure in error handling for help command")

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Event listener that runs when the cog is ready."""
        logger.info(f"Help cog is ready - {len(self._get_command_tree_commands())} commands discovered")


async def setup(bot: commands.Bot) -> None:
    """
    Setup function to load the Help cog.

    Args:
        bot (commands.Bot): The Discord bot instance

    Raises:
        ConfigurationError: If the cog cannot be initialized due to configuration issues
    """
    try:
        await bot.add_cog(Help(bot))
        logger.info("Help cog loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load Help cog: {e}")
        raise
