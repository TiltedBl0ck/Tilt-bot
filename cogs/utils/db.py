import aiosqlite
from pathlib import Path

# Correctly point the DB path to the root directory of the bot.
DB_PATH = Path(__file__).parent.parent.parent / "Database.db"

async def get_db_connection():
    """Opens an asynchronous connection to the SQLite database."""
    conn = await aiosqlite.connect(DB_PATH)
    # Set the row_factory to access columns by name.
    conn.row_factory = aiosqlite.Row
    return conn
