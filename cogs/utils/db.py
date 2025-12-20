import aiosqlite
import os
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

# --- Logging Setup ---
logger = logging.getLogger(__name__)

# --- Global Database Connection ---
_db_connection: Optional[aiosqlite.Connection] = None

# Point to the database/local.db file
DB_FILE = "database/local.db"

# --- In-Memory Cache ---
_config_cache: Dict[int, Dict[str, Any]] = {}
_cache_lock = asyncio.Lock()
_cache_ttl = 3600
_cache_timestamps: Dict[int, float] = {}

# --- Timezone Setup ---
# Your bot uses UTC+8 as the primary reference for announcements
UTC_PLUS_8 = timezone(timedelta(hours=8))

# --- Database Initialization ---
async def init_db() -> bool:
    """Initializes the SQLite database and schema."""
    global _db_connection
    
    if _db_connection:
        return True
    
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    
    try:
        _db_connection = await aiosqlite.connect(DB_FILE)
        
        await _db_connection.execute("PRAGMA journal_mode=WAL;")
        await _db_connection.execute("PRAGMA foreign_keys=ON;")
        await _db_connection.commit()
        
        logger.info(f"SQLite connection established to {DB_FILE}.")
        
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

            # Check for old details table schema and migrate if necessary
            await cursor.execute("PRAGMA table_info(details)")
            columns = await cursor.fetchall()
            if columns:
                col_names = [col[1] for col in columns]
                if 'announcement_id' not in col_names or 'info' not in col_names:
                    logger.warning("Detected old 'details' table schema. Dropping and recreating.")
                    await cursor.execute("DROP TABLE details")

            # Create details table (Updated for Announcements)
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS details (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    announcement_id INTEGER NOT NULL,
                    info TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(announcement_id) REFERENCES announcements(id) ON DELETE CASCADE
                );
            """)
            
            await cursor.execute("CREATE INDEX IF NOT EXISTS idx_announcements_server_id ON announcements(server_id)")
            
        await _db_connection.commit()
        logger.info("Database schema initialized.")
        return True
    
    except Exception as e:
        logger.critical(f"Database initialization failed: {e}", exc_info=True)
        return False

async def close_pool():
    """Closes the database connection."""
    global _db_connection
    if _db_connection:
        try:
            await _db_connection.close()
            _db_connection = None
        except Exception as e:
            logger.error(f"Error closing connection: {e}")

@asynccontextmanager
async def get_db_connection():
    if _db_connection is None:
        raise ConnectionError("Database not initialized.")
    yield _db_connection

# --- Config Helpers ---
async def invalidate_config_cache(guild_id: int):
    async with _cache_lock:
        import time
        if guild_id in _config_cache:
             if (time.time() - _cache_timestamps.get(guild_id, 0)) < _cache_ttl:
                 return _config_cache[guild_id].copy()
            
    try:
        async with _db_connection.execute(
            "SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                columns = [d[0] for d in cursor.description]
                config_dict = dict(zip(columns, row))
                async with _cache_lock:
                    _config_cache[guild_id] = config_dict
                    _cache_timestamps[guild_id] = time.time()
                return config_dict
    except Exception as e:
        logger.error(f"Config fetch error: {e}")
    return None

async def set_guild_config_value(guild_id: int, updates: Dict[str, Any]) -> bool:
    if not updates: return False
    updates.pop('guild_id', None)
    try:
        columns = list(updates.keys())
        placeholders = ", ".join(["?"] * (len(columns) + 1))
        update_set = ", ".join([f"{col}=excluded.{col}" for col in columns])
        col_names = ", ".join(["guild_id"] + columns)
        values = [guild_id] + list(updates.values())
        
        sql = f"INSERT INTO guild_config ({col_names}) VALUES ({placeholders}) ON CONFLICT(guild_id) DO UPDATE SET {update_set}"
        await _db_connection.execute(sql, values)
        await _db_connection.commit()
        await invalidate_config_cache(guild_id)
        return True
    except Exception as e:
        logger.error(f"Config update error: {e}")
        return False

# --- Announcements ---
def get_next_run_time(frequency: str, anchor_dt: Optional[datetime] = None) -> Optional[datetime]:
    """Calculates next run time, maintaining schedule drift correction."""
    freq_map = {
        "once": timedelta(seconds=0), # Special case
        "1min": timedelta(minutes=1), "3min": timedelta(minutes=3), "5min": timedelta(minutes=5),
        "10min": timedelta(minutes=10), "15min": timedelta(minutes=15), "30min": timedelta(minutes=30),
        "1hr": timedelta(hours=1), "3hrs": timedelta(hours=3), "6hrs": timedelta(hours=6),
        "12hrs": timedelta(hours=12), "1day": timedelta(days=1), "3days": timedelta(days=3),
        "1week": timedelta(weeks=1), "2weeks": timedelta(weeks=2), "1month": timedelta(days=30),
    }
    delta = freq_map.get(frequency)
    if delta is None: return None
    if frequency == "once": return anchor_dt # Or None? Logic handled elsewhere usually

    now_naive = datetime.now(UTC_PLUS_8).replace(tzinfo=None)
    next_run = anchor_dt if anchor_dt else now_naive

    while next_run <= now_naive:
        next_run += delta
    return next_run

async def create_announcement(
    server_id: int, 
    channel_id: int, 
    message: str, 
    frequency: str, 
    created_by: int,
    manual_next_run: Optional[datetime] = None
) -> Optional[int]:
    """
    Creates a new announcement. 
    """
    if manual_next_run:
        next_run = manual_next_run.replace(tzinfo=None)
    else:
        next_run = get_next_run_time(frequency)
        
    if not next_run: return None
    
    try:
        cursor = await _db_connection.execute(
            """INSERT INTO announcements (server_id, channel_id, message, frequency, next_run, created_by)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (server_id, channel_id, message, frequency, next_run.isoformat(), created_by)
        )
        await _db_connection.commit()
        return cursor.lastrowid
    except Exception as e:
        logger.error(f"Failed to create announcement: {e}")
        return None

async def create_detail(announcement_id: int, info: str) -> bool:
    """Creates a detail record linked to an announcement."""
    try:
        await _db_connection.execute(
            "INSERT INTO details (announcement_id, info) VALUES (?, ?)",
            (announcement_id, info)
        )
        await _db_connection.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to create detail: {e}")
        return False

async def get_detail(announcement_id: int) -> Optional[str]:
    """Fetches the detail info for a given announcement."""
    try:
        async with _db_connection.execute("SELECT info FROM details WHERE announcement_id = ?", (announcement_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None
    except Exception as e:
        logger.error(f"Failed to get detail: {e}")
        return None

async def update_detail(announcement_id: int, info: str) -> bool:
    """Updates or inserts the detail record for an announcement."""
    try:
        # Check if exists
        exists = await get_detail(announcement_id)
        if exists is not None:
            await _db_connection.execute("UPDATE details SET info = ? WHERE announcement_id = ?", (info, announcement_id))
        else:
            await _db_connection.execute("INSERT INTO details (announcement_id, info) VALUES (?, ?)", (announcement_id, info))
        await _db_connection.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to update detail: {e}")
        return False

async def get_due_announcements() -> List[Dict[str, Any]]:
    try:
        async with _db_connection.execute("SELECT * FROM announcements WHERE is_active = 1") as cursor:
            rows = await cursor.fetchall()
            columns = [d[0] for d in cursor.description]
            results = []
            for row in rows:
                data = dict(zip(columns, row))
                if data['next_run']:
                    data['next_run'] = datetime.fromisoformat(data['next_run'])
                results.append(data)
            return results
    except Exception as e:
        logger.error(f"Due check error: {e}")
        return []

async def update_announcement_next_run(ann_id: int, frequency: str) -> Optional[datetime]:
    try:
        async with _db_connection.execute("SELECT next_run FROM announcements WHERE id = ?", (ann_id,)) as cursor:
            row = await cursor.fetchone()
            if not row or not row[0]: return None
            last_run = datetime.fromisoformat(row[0])

        new_next = get_next_run_time(frequency, anchor_dt=last_run)
        if new_next:
            await _db_connection.execute("UPDATE announcements SET next_run = ? WHERE id = ?", (new_next.isoformat(), ann_id))
            await _db_connection.commit()
        return new_next
    except Exception as e:
        logger.error(f"Update run time error: {e}")
        return None

async def get_announcement(ann_id: int, server_id: int) -> Optional[Dict[str, Any]]:
    try:
        async with _db_connection.execute(
            "SELECT * FROM announcements WHERE id = ? AND server_id = ?", (ann_id, server_id)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                columns = [d[0] for d in cursor.description]
                data = dict(zip(columns, row))
                if data['next_run']: data['next_run'] = datetime.fromisoformat(data['next_run'])
                return data
    except Exception as e:
        logger.error(f"Get announcement error: {e}")
    return None

async def get_announcements_by_server(server_id: int) -> List[Dict[str, Any]]:
    try:
        async with _db_connection.execute(
            "SELECT * FROM announcements WHERE server_id = ? AND is_active = 1", (server_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            columns = [d[0] for d in cursor.description]
            results = []
            for row in rows:
                data = dict(zip(columns, row))
                if data['next_run']: data['next_run'] = datetime.fromisoformat(data['next_run'])
                results.append(data)
            return results
    except Exception as e:
        logger.error(f"Server list fetch error: {e}")
        return []

async def stop_announcement(ann_id: int, server_id: int) -> bool:
    try:
        await _db_connection.execute("UPDATE announcements SET is_active = 0 WHERE id = ? AND server_id = ?", (ann_id, server_id))
        await _db_connection.commit()
        return True
    except Exception as e:
        logger.error(f"Stop error: {e}")
        return False

async def delete_announcement(ann_id: int, server_id: int) -> bool:
    try:
        await _db_connection.execute("DELETE FROM announcements WHERE id = ? AND server_id = ?", (ann_id, server_id))
        await _db_connection.commit()
        return True
    except Exception as e:
        logger.error(f"Delete error: {e}")
        return False

async def mark_announcement_inactive(ann_id: int) -> bool:
    try:
        await _db_connection.execute("UPDATE announcements SET is_active = 0 WHERE id = ?", (ann_id,))
        await _db_connection.commit()
        return True
    except Exception as e:
        logger.error(f"Mark inactive error: {e}")
        return False

async def update_announcement_details(ann_id: int, server_id: int, updates: Dict[str, Any]) -> bool:
    if not updates: return False
    if 'next_run' in updates and isinstance(updates['next_run'], datetime):
        updates['next_run'] = updates['next_run'].isoformat()
    try:
        cols = list(updates.keys())
        set_parts = [f"{col} = ?" for col in cols]
        values = list(updates.values()) + [ann_id, server_id]
        sql = f"UPDATE announcements SET {', '.join(set_parts)} WHERE id = ? AND server_id = ?"
        await _db_connection.execute(sql, values)
        await _db_connection.commit()
        return True
    except Exception as e:
        logger.error(f"Update details error: {e}")
        return False

# Compatibility shim
pool = "SQLiteConnected"