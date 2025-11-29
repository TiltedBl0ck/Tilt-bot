import aiosqlite
import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

# --- Logging Setup ---
logger = logging.getLogger(__name__)

# --- Global Database Connection ---
_db_connection: Optional[aiosqlite.Connection] = None

# CHANGED: Point to the new location inside the 'database' folder
DB_FILE = "database/local.db"

# --- In-Memory Cache ---
_config_cache: Dict[int, Dict[str, Any]] = {}
_cache_lock = asyncio.Lock()
_cache_ttl = 3600
_cache_timestamps: Dict[int, float] = {}

# --- Database Initialization ---
async def init_db() -> bool:
    """Initializes the SQLite database and schema."""
    global _db_connection
    
    if _db_connection:
        return True
    
    # Ensure the 'database' directory exists before connecting
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    
    try:
        # Connect to file in database/local.db
        _db_connection = await aiosqlite.connect(DB_FILE)
        
        # Enable Write-Ahead Logging (WAL) for better concurrency
        await _db_connection.execute("PRAGMA journal_mode=WAL;")
        await _db_connection.execute("PRAGMA foreign_keys=ON;")
        await _db_connection.commit()
        
        logger.info(f"SQLite connection established to {DB_FILE} (WAL Mode enabled).")
        
        # --- Create Tables ---
        async with _db_connection.cursor() as cursor:
            # Create guild_config table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS guild_config (
                    guild_id INTEGER PRIMARY KEY,
                    welcome_channel_id INTEGER,
                    goodbye_channel_id INTEGER,
                    welcome_message TEXT,
                    welcome_image TEXT,
                    goodbye_message TEXT,
                    goodbye_image TEXT,
                    stats_category_id INTEGER,
                    member_count_channel_id INTEGER,
                    bot_count_channel_id INTEGER,
                    role_count_channel_id INTEGER,
                    counting_channel_id INTEGER,
                    current_count INTEGER DEFAULT 0,
                    last_counter_id INTEGER
                );
            """)
            
            # Create announcements table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS announcements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    frequency TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    next_run TEXT NOT NULL,
                    created_by INTEGER NOT NULL,
                    is_active INTEGER DEFAULT 1
                );
            """)
            
            # Create Indexes
            await cursor.execute("CREATE INDEX IF NOT EXISTS idx_announcements_server_id ON announcements(server_id)")
            
        await _db_connection.commit()
        logger.info("Database schema initialized.")
        return True
    
    except Exception as e:
        logger.critical(f"Database initialization failed: {e}", exc_info=True)
        return False

# --- Close Connection ---
async def close_pool():
    """Closes the database connection."""
    global _db_connection
    if _db_connection:
        try:
            await _db_connection.close()
            logger.info("SQLite connection closed.")
            _db_connection = None
        except Exception as e:
            logger.error(f"Error closing connection: {e}", exc_info=True)

# --- Context Manager ---
@asynccontextmanager
async def get_db_connection():
    """Yields the persistent connection."""
    if _db_connection is None:
        raise ConnectionError("Database not initialized.")
    yield _db_connection

# --- Cache Helpers ---
async def invalidate_config_cache(guild_id: int):
    async with _cache_lock:
        _config_cache.pop(guild_id, None)
        _cache_timestamps.pop(guild_id, None)

async def _is_cache_expired(guild_id: int) -> bool:
    import time
    if guild_id not in _cache_timestamps:
        return True
    return (time.time() - _cache_timestamps[guild_id]) > _cache_ttl

# --- Guild Config Functions ---
async def get_guild_config(guild_id: int) -> Optional[Dict[str, Any]]:
    async with _cache_lock:
        if guild_id in _config_cache and not await _is_cache_expired(guild_id):
            return _config_cache[guild_id].copy()
            
    try:
        async with _db_connection.execute(
            """SELECT * FROM guild_config WHERE guild_id = ?""",
            (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            
            if row:
                columns = [description[0] for description in cursor.description]
                config_dict = dict(zip(columns, row))
                
                async with _cache_lock:
                    _config_cache[guild_id] = config_dict
                    _cache_timestamps[guild_id] = __import__('time').time()
                return config_dict
            else:
                async with _cache_lock:
                    _config_cache[guild_id] = {}
                    _cache_timestamps[guild_id] = __import__('time').time()
                return None
    except Exception as e:
        logger.error(f"Failed to fetch config for guild {guild_id}: {e}")
        return None

async def set_guild_config_value(guild_id: int, updates: Dict[str, Any]) -> bool:
    if not updates:
        return False
    
    updates.pop('guild_id', None)
    
    try:
        columns = list(updates.keys())
        placeholders = ", ".join(["?"] * (len(columns) + 1))
        update_set = ", ".join([f"{col}=excluded.{col}" for col in columns])
        col_names = ", ".join(["guild_id"] + columns)
        
        values = [guild_id] + list(updates.values())
        
        sql = f"""
            INSERT INTO guild_config ({col_names})
            VALUES ({placeholders})
            ON CONFLICT(guild_id) DO UPDATE SET {update_set}
        """
        
        await _db_connection.execute(sql, values)
        await _db_connection.commit()
        await invalidate_config_cache(guild_id)
        return True
    except Exception as e:
        logger.error(f"Failed to update config for guild {guild_id}: {e}")
        return False

async def update_counting_stats(guild_id: int, current_count: int, last_counter_id: Optional[int]) -> bool:
    sql = """
        INSERT INTO guild_config (guild_id, current_count, last_counter_id)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
        current_count = excluded.current_count,
        last_counter_id = excluded.last_counter_id
    """
    try:
        await _db_connection.execute(sql, (guild_id, current_count, last_counter_id))
        await _db_connection.commit()
        
        async with _cache_lock:
            if guild_id in _config_cache:
                _config_cache[guild_id]['current_count'] = current_count
                _config_cache[guild_id]['last_counter_id'] = last_counter_id
                
        return True
    except Exception as e:
        logger.error(f"Failed to update counting stats: {e}")
        return False

# --- Announcements Functions ---
def get_next_run_time(frequency: str) -> datetime:
    now = datetime.now()
    freq_map = {
        "1min": timedelta(minutes=1), "3min": timedelta(minutes=3),
        "5min": timedelta(minutes=5), "10min": timedelta(minutes=10),
        "15min": timedelta(minutes=15), "30min": timedelta(minutes=30),
        "1hr": timedelta(hours=1), "3hrs": timedelta(hours=3),
        "6hrs": timedelta(hours=6), "12hrs": timedelta(hours=12),
        "1day": timedelta(days=1), "3days": timedelta(days=3),
        "1week": timedelta(weeks=1), "2weeks": timedelta(weeks=2),
        "1month": timedelta(days=30),
    }
    delta = freq_map.get(frequency)
    return now + delta if delta else None

async def create_announcement(server_id: int, channel_id: int, message: str, frequency: str, created_by: int) -> Optional[int]:
    next_run = get_next_run_time(frequency)
    if not next_run: return None
    
    next_run_str = next_run.isoformat()
    
    try:
        cursor = await _db_connection.execute(
            """INSERT INTO announcements 
            (server_id, channel_id, message, frequency, next_run, created_by)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (server_id, channel_id, message, frequency, next_run_str, created_by)
        )
        await _db_connection.commit()
        return cursor.lastrowid
    except Exception as e:
        logger.error(f"Failed to create announcement: {e}")
        return None

async def get_announcements_by_server(server_id: int) -> List[Dict[str, Any]]:
    try:
        async with _db_connection.execute(
            """SELECT id, channel_id, frequency, next_run, message
            FROM announcements
            WHERE server_id = ? AND is_active = 1
            ORDER BY id DESC LIMIT 10""",
            (server_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                next_run_dt = datetime.fromisoformat(row[3]) if row[3] else None
                results.append({
                    'id': row[0], 'channel_id': row[1],
                    'frequency': row[2], 'next_run': next_run_dt,
                    'message': row[4]
                })
            return results
    except Exception as e:
        logger.error(f"Error fetching announcements: {e}")
        return []

async def get_due_announcements() -> List[Dict[str, Any]]:
    try:
        async with _db_connection.execute(
            """SELECT id, server_id, channel_id, message, frequency, created_by, next_run
            FROM announcements WHERE is_active = 1"""
        ) as cursor:
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                next_run_dt = datetime.fromisoformat(row[6]) if row[6] else None
                results.append({
                    'id': row[0], 'server_id': row[1], 'channel_id': row[2],
                    'message': row[3], 'frequency': row[4],
                    'created_by': row[5], 'next_run': next_run_dt
                })
            return results
    except Exception as e:
        logger.error(f"Error fetching due announcements: {e}")
        return []

async def update_announcement_next_run(ann_id: int, frequency: str) -> bool:
    next_run = get_next_run_time(frequency)
    if not next_run: return False
    next_run_str = next_run.isoformat()
    
    try:
        await _db_connection.execute(
            "UPDATE announcements SET next_run = ? WHERE id = ?",
            (next_run_str, ann_id)
        )
        await _db_connection.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to update announcement {ann_id}: {e}")
        return False

async def stop_announcement(ann_id: int, server_id: int) -> bool:
    try:
        await _db_connection.execute(
            "UPDATE announcements SET is_active = 0 WHERE id = ? AND server_id = ?",
            (ann_id, server_id)
        )
        await _db_connection.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to stop announcement: {e}")
        return False

async def get_announcement(ann_id: int, server_id: int) -> Optional[Dict[str, Any]]:
    try:
        async with _db_connection.execute(
            "SELECT id, message, frequency, next_run FROM announcements WHERE id = ? AND server_id = ?",
            (ann_id, server_id)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                 return {
                     'id': row[0], 'message': row[1],
                     'frequency': row[2], 'next_run': row[3]
                 }
            return None
    except Exception as e:
        logger.error(f"Error fetching announcement: {e}")
        return None

async def mark_announcement_inactive(ann_id: int) -> bool:
    try:
        await _db_connection.execute(
            "UPDATE announcements SET is_active = 0 WHERE id = ?",
            (ann_id,)
        )
        await _db_connection.commit()
        return True
    except Exception as e:
        logger.error(f"Error marking inactive: {e}")
        return False

# Re-export pool for compatibility with other files checking for `db_utils.pool`
pool = "DummyValueForCompatibility"