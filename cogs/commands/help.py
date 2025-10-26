import discord
from discord import app_commands
from discord.ext import commands
import logging
# No database interaction needed in this version of help, so db import is removed

logger = logging.getLogger(__name__)

# --- Views for Help Command ---

class HelpDropdown(discord.ui.Select):
    def __init__(self, bot: commands.Bot, mapping: dict):
        self.bot = bot
        self.mapping = mapping
        options = [
            discord.SelectOption(label="Home", description="Return to the main help overview.", emoji="🏠")
        ]
        # Add options for each cog with commands
        for cog, commands_list in mapping.items():
            if cog and commands_list: # Check if cog exists and has commands
                cog_name = cog.qualified_name if hasattr(cog, 'qualified_name') else "Uncategorized"
                emoji = getattr(cog, 'COG_EMOJI', '❓') # Use COG_EMOJI if defined in cog
                options.append(discord.SelectOption(label=cog_name, description=f"Commands in {cog_name}", emoji=emoji))

        super().__init__(placeholder="Choose a category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_label = self.values[0]
        embed = discord.Embed(title="Help Center", color=discord.Color.blue())

        if selected_label == "Home":
            embed.description = (
                f"Welcome to **{self.bot.user.name}'s** Help Center!\n\n"
                f"Use the dropdown menu below to explore command categories.\n"
                f"My prefix is `!` but I primarily use Slash Commands (type `/`).\n\n"
                f"**Need more help?**\n"
                f"[Support Server](https://discord.gg/your_invite_link_here) | [GitHub Repository](https://github.com/TiltedBl0ck/Tilt-bot)" # TODO: Replace placeholder link
            )
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        else:
            # Find the selected cog
            target_cog = None
            for cog, commands_list in self.mapping.items():
                 if cog and commands_list:
                    cog_name = cog.qualified_name if hasattr(cog, 'qualified_name') else "Uncategorized"
                    if cog_name == selected_label:
                        target_cog = cog
                        break
            
            if target_cog:
                cog_name = target_cog.qualified_name
                embed.title = f"{getattr(target_cog, 'COG_EMOJI', '❓')} {cog_name} Commands"
                description = target_cog.description or "No description provided."
                
                command_list_str = ""
                # Get slash commands specifically (app_commands) associated with this cog
                cog_commands = [cmd for cmd in self.bot.tree.get_commands() if cmd.binding == target_cog]
                
                # Also include traditional commands if any are in the cog (though slash is preferred)
                prefix_commands = target_cog.get_commands()

                if cog_commands:
                    command_list_str += "**Slash Commands:**\n"
                    for cmd in cog_commands:
                        command_list_str += f"`/{cmd.name}` - {cmd.description}\n"
                    command_list_str += "\n"

                if prefix_commands:
                    command_list_str += "**Prefix Commands (Legacy):**\n"
                    for cmd in prefix_commands:
                         command_list_str += f"`!{cmd.name}` - {cmd.short_doc or 'No description'}\n"
                
                embed.description = f"{description}\n\n{command_list_str or 'No commands found in this category.'}"
            else:
                 embed.description = "Could not find information for the selected category."


        # Respond or edit the original message
        try:
            # Edit original if possible
            await interaction.response.edit_message(embed=embed)
        except discord.InteractionResponded:
            # Fallback if edit fails (e.g., initial response)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error updating help message: {e}")
            await interaction.followup.send("An error occurred while updating the help message.", ephemeral=True)


class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot, mapping: dict):
        super().__init__(timeout=180) # Timeout after 3 minutes
        self.add_item(HelpDropdown(bot, mapping))

# --- Help Command Cog ---
class HelpCog(commands.Cog, name="Help"):
    """Shows this help message."""
    COG_EMOJI = "ℹ️"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Displays the interactive help menu.")
    async def help_slash(self, interaction: discord.Interaction):
        """Shows the main interactive help embed."""
        mapping = self.bot.cogs # Get cog mapping

        embed = discord.Embed(
            title="Help Center",
            description=(
                f"Welcome to **{self.bot.user.name}'s** Help Center!\n\n"
                f"Use the dropdown menu below to explore command categories.\n"
                f"My prefix is `!` but I primarily use Slash Commands (type `/`).\n\n"
                f"**Need more help?**\n"
                 f"[Support Server](https://discord.gg/your_invite_link_here) | [GitHub Repository](https://github.com/TiltedBl0ck/Tilt-bot)" # TODO: Replace placeholder link
            ),
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text=f"Bot Version: {self.bot.version}")

        view = HelpView(self.bot, mapping)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
    # Remove the old help command if it exists to avoid conflicts
    bot.remove_command('help')
