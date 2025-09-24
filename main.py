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

# --- Bot Version ---
# Central location for the bot's version number.
BOT_VERSION = "v1.1.0"

# --- Bot Setup ---
class TiltBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="/", intents=intents)
        
        # Store the version number on the bot instance so cogs can access it.
        self.version = BOT_VERSION

    async def setup_hook(self):
        """This is called when the bot logs in."""
        print(f"{self.user} is online — loading cogs…")
        # Use pathlib for a cleaner way to find cogs
        cogs_dir = Path("./cogs")
        for entry in cogs_dir.iterdir():
            # Check if it's a python file and not a special file
            if entry.is_file() and entry.suffix == ".py" and not entry.name.startswith("_"):
                try:
                    await self.load_extension(f'cogs.{entry.stem}')
                    print(f"Loaded cog: {entry.name}")
                except Exception as e:
                    print(f"Failed to load cog {entry.name}: {e}")
        
        # Sync commands to Discord
        await self.tree.sync()
        print("Slash commands synced globally.")

    async def on_ready(self):
        """Event for when the bot is fully ready."""
        print(f"Bot is ready. Version: {self.version}")
        # You can set a custom status here if you like
        await self.change_presence(activity=discord.Game(name="/help for commands"))

bot = TiltBot()

# --- Database Initialization (Synchronous part is okay here) ---
DB_PATH = Path(__file__).parent / "Database.db"

def init_db():
    """Initializes the database schema if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # A single, improved CREATE TABLE statement
    cur.execute("""
    CREATE TABLE IF NOT EXISTS guild_config (
        guild_id                  INTEGER PRIMARY KEY,
        welcome_channel_id        INTEGER,
        goodbye_channel_id        INTEGER,
        stats_category_id         INTEGER,
        member_count_channel_id   INTEGER,
        bot_count_channel_id      INTEGER,
        role_count_channel_id     INTEGER,
        channel_count_channel_id  INTEGER,
        setup_complete            INTEGER DEFAULT 0,
        welcome_message           TEXT,
        welcome_image             TEXT,
        goodbye_message           TEXT,
        goodbye_image             TEXT
    )
    """)
    # Check and add columns if they don't exist to prevent errors
    table_info = cur.execute("PRAGMA table_info(guild_config)").fetchall()
    column_names = [info[1] for info in table_info]
    
    columns_to_add = {
        "welcome_message": "TEXT",
        "welcome_image": "TEXT",
        "goodbye_message": "TEXT",
        "goodbye_image": "TEXT"
    }

    for col_name, col_type in columns_to_add.items():
        if col_name not in column_names:
            cur.execute(f"ALTER TABLE guild_config ADD COLUMN {col_name} {col_type}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    bot.run(BOT_TOKEN)
