"""
Database Connection Utilities for Tilt-bot

This module provides database connection functionality for the bot's
SQLite database operations.

Author: TiltedBl0ck
Version: 2.0.0
"""

import aiosqlite
from pathlib import Path

# Correctly point the DB path to the root directory of the bot
DB_PATH = Path(__file__).parent.parent.parent / "Database.db"

async def get_db_connection():
    """
    Opens an asynchronous connection to the SQLite database.

    Returns:
        aiosqlite.Connection: The database connection object
    """
    conn = await aiosqlite.connect(DB_PATH)
    # Set the row_factory to access columns by name
    conn.row_factory = aiosqlite.Row
    return conn
