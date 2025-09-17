# Tilt-bot

Tilt-bot is a versatile Discord bot providing server statistics, user utilities, moderation tools, and welcome/goodbye messages. It leverages slash commands and PostgreSQL for persistent per-guild configurations.

## Features

- **Server Stats**: Automatically creates and updates voice channels showing member, bot, role, and channel counts every 10 minutes.
- **Utilities**: Commands for server info, user info, role info, avatars, member counts, latency checks, bot stats, emojis, and invite link.
- **Moderation**: Bulk message deletion (`/clear`).
- **Welcome/Goodbye**: Customizable welcome and goodbye message channels with embed formatting.
- **Persistence**: PostgreSQL database with automatic migrations and per-guild settings.

## Requirements

- Python 3.10+
- PostgreSQL database (e.g., Neon, Heroku Postgres)
- Discord Bot application with slash commands enabled

## Setup

1. Clone this repository.
2. Create a `.env` file in the project root:
   ```
   BOT_TOKEN=your_discord_bot_token
   DATABASE_URL=postgres://user:pass@host:port/dbname
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the bot:
   ```bash
   python main.py
   ```

## Commands

### Utility Commands
- `/help` - Display all commands
- `/serverinfo` - Show server details
- `/userinfo [member]` - Show user details
- `/roleinfo <role>` - Show role details
- `/avatar [member]` - Display a user's avatar
- `/membercount` - Show total/humans/bots
- `/ping` - Bot latency
- `/botinfo` - Bot statistics
- `/emojis` - List custom emojis
- `/invite` - Generate invite link

### Moderation
- `/clear <count>` - Delete recent messages (1–100)

### Server Stats
- `/setup serverstats` - Create stats category and counters
- `/config serverstats` - Manage stats (view, delete, reset)

### Configuration
- `/config welcome <channel>` - Set welcome channel
- `/config goodbye <channel>` - Set goodbye channel

## Database

Runs an initialization on startup to create the `guild_config` table. Stores: guild ID, channel IDs, and setup status.

## Contributing

PRs welcome! Please follow standard Python coding conventions and include tests where applicable.

## License

MIT License
