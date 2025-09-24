import aiosqlite
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).parent.parent.parent / "Database.db"

async def init_db():
    """Initializes the database schema if it doesn't exist."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS guild_config (
            guild_id                  INTEGER PRIMARY KEY,
            welcome_channel_id        INTEGER,
            goodbye_channel_id        INTEGER,
            welcome_message           TEXT,
            welcome_image             TEXT,
            goodbye_message           TEXT,
            goodbye_image             TEXT,
            stats_category_id         INTEGER,
            member_count_channel_id   INTEGER,
            bot_count_channel_id      INTEGER,
            role_count_channel_id     INTEGER
        )
        """)
        await conn.commit()
        logger.info("Database has been successfully initialized.")

async def get_db_connection():
    """Opens an asynchronous connection to the SQLite database."""
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    return conn

