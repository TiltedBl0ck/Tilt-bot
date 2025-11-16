import logging
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


class ServerInfo(commands.Cog):
    """Provides Discord server information to other cogs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_guild_context(self, guild: discord.Guild) -> str:
        """Get comprehensive guild/server information."""
        lines = [
            f"Server Name: {guild.name}",
            f"Server ID: {guild.id}",
            f"Owner: {guild.owner.mention if guild.owner else 'Unknown'}",
            f"Members: {guild.member_count}",
            f"Created: {guild.created_at.strftime('%Y-%m-%d')}",
            ""
        ]

        # Get channels
        channels = {
            "text": [],
            "voice": [],
            "categories": []
        }
        
        for channel in guild.channels:
            if isinstance(channel, discord.CategoryChannel):
                channels["categories"].append(channel.name)
            elif isinstance(channel, discord.TextChannel):
                channels["text"].append(channel.name)
            elif isinstance(channel, discord.VoiceChannel):
                channels["voice"].append(channel.name)

        if channels["categories"]:
            lines.append("Categories:")
            for cat in channels["categories"][:10]:
                lines.append(f"  - {cat}")
            if len(channels["categories"]) > 10:
                lines.append(f"  ... and {len(channels['categories']) - 10} more")

        if channels["text"]:
            lines.append("\nText Channels:")
            for ch in channels["text"][:15]:
                lines.append(f"  - #{ch}")
            if len(channels["text"]) > 15:
                lines.append(f"  ... and {len(channels['text']) - 15} more")

        if channels["voice"]:
            lines.append("\nVoice Channels:")
            for ch in channels["voice"][:10]:
                lines.append(f"  - 🎙️ {ch}")
            if len(channels["voice"]) > 10:
                lines.append(f"  ... and {len(channels['voice']) - 10} more")

        # Get roles
        roles = [role.name for role in guild.roles if role.name != "@everyone"][:10]
        if roles:
            lines.append("\nKey Roles:")
            for role in roles:
                lines.append(f"  - {role}")

        return "\n".join(lines)

    def get_channel_context(self, channel: discord.TextChannel) -> str:
        """Get information about a specific text channel."""
        lines = [
            f"Channel: #{channel.name}",
            f"Channel ID: {channel.id}",
            f"Guild: {channel.guild.name}",
        ]

        if channel.topic:
            lines.append(f"Topic: {channel.topic}")

        if channel.category:
            lines.append(f"Category: {channel.category.name}")

        lines.append(f"Created: {channel.created_at.strftime('%Y-%m-%d')}")

        return "\n".join(lines)

    def get_user_context(self, user: discord.Member, guild: discord.Guild) -> str:
        """Get information about a user in the server."""
        lines = [
            f"User: {user.name}#{user.discriminator}",
            f"User ID: {user.id}",
            f"Joined Server: {user.joined_at.strftime('%Y-%m-%d') if user.joined_at else 'Unknown'}",
            f"Account Created: {user.created_at.strftime('%Y-%m-%d')}",
        ]

        roles = [role.name for role in user.roles if role.name != "@everyone"]
        if roles:
            lines.append(f"Roles: {', '.join(roles)}")

        if user.top_role:
            lines.append(f"Top Role: {user.top_role.name}")

        if user.nick:
            lines.append(f"Nickname: {user.nick}")

        return "\n".join(lines)


async def setup(bot: commands.Bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(ServerInfo(bot))