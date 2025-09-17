
# Discord Bot

A Discord bot built with discord.py that supports slash commands, background tasks, and PostgreSQL database persistence.

## Features

- Slash command `/ping` to check bot latency.
- Hourly background task logging bot status and guild count.
- PostgreSQL database initialization and guild configuration storage.
- Secure environment variable management for tokens and database URL.

## Prerequisites

- Python 3.10 or higher
- PostgreSQL database instance
- Discord bot application with a token
- `main.py` and `requirements.txt` in the project root

## Installation

1. Clone the repository or download the files.
2. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Create a `.env` file in the project root with the following variables:

```ini
BOT_TOKEN=your_discord_bot_token_here
DATABASE_URL=your_postgresql_connection_string_here
```

- `BOT_TOKEN`: The token for your Discord bot.
- `DATABASE_URL`: The PostgreSQL connection string, including user, password, host, port, and database name. For example:
  ```
  postgresql://user:password@host:5432/database_name
  ```

## Usage

Run the bot with:

```bash
python main.py
```

Upon startup, the bot will:

- Initialize database tables if they do not exist.
- Log into Discord and print ready status.
- Start an hourly background task that logs the current time and number of guilds the bot is in.

## Commands

- `/ping`: Responds with `Pong! Latency: Xms` to check bot latency.

## Customization

- **Adding More Commands:** Use the `@bot.slash_command` decorator.
- **Adjusting Task Interval:** Modify `@tasks.loop(hours=1)` to desired interval.
- **Database Schema Updates:** Update `init_db()` function in `main.py`.

## Deployment

### Docker

1. Create a `Dockerfile`:
   ```dockerfile
   FROM python:3.11-slim
   WORKDIR /app
   COPY . .
   RUN pip install --no-cache-dir -r requirements.txt
   CMD ["python", "main.py"]
   ```

2. Build and run:
   ```bash
   docker build -t discord-bot .
   docker run --env-file .env discord-bot
   ```

### Hosting Platforms

- **Wispbyte**: Use free tier with `.env` file or console `export` commands.
- **Render**: Define environment variables in dashboard; set start command `python main.py`.
- **Fly.io / Docker**: Deploy via Docker image and secrets.

## License

This project is released under the MIT License.
