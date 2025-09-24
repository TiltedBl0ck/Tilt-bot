import os
import sqlite3
import discord
from discord.ext import commands
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN must be set in environment variables")

# --- Bot Setup ---
class TiltBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="/", intents=intents)

    async def setup_hook(self):
        """This is called when the bot logs in."""
        print(f"{self.user} is online — loading cogs…")
        # Load cogs
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"Loaded cog: {filename}")
                except Exception as e:
                    print(f"Failed to load cog {filename}: {e}")
        
        # Sync commands to Discord
        await self.tree.sync()
        print("Slash commands synced globally.")

    async def on_ready(self):
        """Event for when the bot is fully ready."""
        print("Bot is ready.")
        pass

bot = TiltBot()

# --- Database Initialization ---
DB_PATH = Path(__file__).parent / "Database.db"

def init_db():
    """Initializes the database schema."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS guild_config (
        guild_id                 INTEGER PRIMARY KEY,
        welcome_channel_id       INTEGER,
        goodbye_channel_id       INTEGER,
        stats_category_id        INTEGER,
        member_count_channel_id  INTEGER,
        bot_count_channel_id     INTEGER,
        role_count_channel_id    INTEGER,
        channel_count_channel_id INTEGER,
        setup_complete           INTEGER DEFAULT 0,
        welcome_message          TEXT,
        welcome_image            TEXT,
        goodbye_message          TEXT,
        goodbye_image            TEXT
    )
    """)
    try:
        cur.execute("ALTER TABLE guild_config ADD COLUMN welcome_message TEXT")
        cur.execute("ALTER TABLE guild_config ADD COLUMN welcome_image TEXT")
        cur.execute("ALTER TABLE guild_config ADD COLUMN goodbye_message TEXT")
        cur.execute("ALTER TABLE guild_config ADD COLUMN goodbye_image TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    bot.run(BOT_TOKEN)

