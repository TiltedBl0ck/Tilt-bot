import aiosqlite
from pathlib import Path
import logging
from contextlib import asynccontextmanager

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
            role_count_channel_id     INTEGER,
            counting_channel_id       INTEGER,
            current_count             INTEGER DEFAULT 0,
            last_counter_id           INTEGER
        )
        """)
        
        # Add new columns if they don't exist to avoid errors on existing databases.
        try:
            await conn.execute("ALTER TABLE guild_config ADD COLUMN counting_channel_id INTEGER")
            await conn.execute("ALTER TABLE guild_config ADD COLUMN current_count INTEGER DEFAULT 0")
            await conn.execute("ALTER TABLE guild_config ADD COLUMN last_counter_id INTEGER")
            logger.info("Successfully added counting game columns to the database schema.")
        except aiosqlite.OperationalError:
            # This error means the columns already exist, which is fine.
            pass
            
        await conn.commit()
        logger.info("Database has been successfully initialized.")

@asynccontextmanager
async def get_db_connection():
    """
    Opens an asynchronous connection to the SQLite database as a context manager.
    This ensures the connection is always closed properly.
    """
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    try:
        yield conn
    finally:
        await conn.close()
