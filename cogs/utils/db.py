import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "Database.db"

def get_db_connection():
    """Opens a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

