import aiosqlite
import os
import logging
import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# --- Global Database Connection ---
_db_connection: Optional[aiosqlite.Connection] = None
DB_FILE = "database/local.db"

# --- In-Memory Cache ---
_config_cache: Dict[int, Dict[str, Any]] = {}
_cache_lock = asyncio.Lock()
_cache_ttl = 3600
_cache_timestamps: Dict[int, float] = {}

UTC_PLUS_8 = timezone(timedelta(hours=8))

async def init_db() -> bool:
    """Initializes the SQLite database and schema."""
    global _db_connection, pool
    if _db_connection: return True
    
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    try:
        _db_connection = await aiosqlite.connect(DB_FILE)
        pool = _db_connection  # Set pool to the actual connection for compatibility checks
        await _db_connection.execute("PRAGMA journal_mode=WAL;")
        await _db_connection.execute("PRAGMA foreign_keys=ON;")
        await _db_connection.commit()
        
        async with _db_connection.cursor() as cursor:
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
                    last_counter_id INTEGER,
                    ai_chat_enabled INTEGER DEFAULT 0,
                    ai_chat_channel_id INTEGER
                );
            """)
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
        logger.info(f"SQLite connection established to {DB_FILE} (WAL Mode enabled).")
        return True
    except Exception as e:
        logger.critical(f"DB Init failed: {e}")
        pool = None  # Ensure pool is None if initialization fails
        return False

async def close_pool():
    global _db_connection, pool
    if _db_connection:
        await _db_connection.close()
        _db_connection = None
        pool = None
        logger.info("SQLite connection closed.")

@asynccontextmanager
async def get_db_connection():
    if _db_connection is None: raise ConnectionError("DB not initialized.")
    yield _db_connection

# --- Config Retrieval ---
async def get_config(guild_id: int) -> Optional[Dict[str, Any]]:
    """Fetches guild config with caching."""
    async with _cache_lock:
        if guild_id in _config_cache:
             if (time.time() - _cache_timestamps.get(guild_id, 0)) < _cache_ttl:
                 return _config_cache[guild_id].copy()
            
    try:
        async with _db_connection.execute("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)) as cursor:
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

# Alias for backward compatibility with older cogs
get_guild_config = get_config

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
        async with _cache_lock:
            _config_cache.pop(guild_id, None) # Clear cache
        return True
    except Exception as e:
        logger.error(f"Config update error: {e}")
        return False

# --- Counting Game Specifics ---
async def update_counting_stats(guild_id: int, count: int, user_id: Optional[int]) -> bool:
    """Specialized helper for the counting game."""
    return await set_guild_config_value(guild_id, {
        "current_count": count,
        "last_counter_id": user_id
    })

# --- Announcements ---
def get_next_run_time(frequency: str, anchor_dt: Optional[datetime] = None) -> Optional[datetime]:
    freq_map = {
        "once": timedelta(seconds=0), "1min": timedelta(minutes=1), "3min": timedelta(minutes=3), 
        "5min": timedelta(minutes=5), "10min": timedelta(minutes=10), "15min": timedelta(minutes=15), 
        "30min": timedelta(minutes=30), "1hr": timedelta(hours=1), "3hrs": timedelta(hours=3), 
        "6hrs": timedelta(hours=6), "12hrs": timedelta(hours=12), "1day": timedelta(days=1), 
        "3days": timedelta(days=3), "1week": timedelta(weeks=1), "2weeks": timedelta(weeks=2), 
        "1month": timedelta(days=30),
    }
    delta = freq_map.get(frequency)
    if delta is None: return None
    now_naive = datetime.now(UTC_PLUS_8).replace(tzinfo=None)
    next_run = anchor_dt if anchor_dt else now_naive
    while next_run <= now_naive:
        next_run += delta
    return next_run

async def create_announcement(server_id, channel_id, message, frequency, created_by, manual_next_run=None):
    next_run = manual_next_run.replace(tzinfo=None) if manual_next_run else get_next_run_time(frequency)
    if not next_run: return None
    try:
        cursor = await _db_connection.execute(
            "INSERT INTO announcements (server_id, channel_id, message, frequency, next_run, created_by) VALUES (?, ?, ?, ?, ?, ?)",
            (server_id, channel_id, message, frequency, next_run.isoformat(), created_by)
        )
        await _db_connection.commit()
        return cursor.lastrowid
    except Exception as e:
        logger.error(f"Create ann error: {e}")
        return None

async def create_detail(announcement_id, info):
    try:
        await _db_connection.execute("INSERT INTO details (announcement_id, info) VALUES (?, ?)", (announcement_id, info))
        await _db_connection.commit()
        return True
    except Exception: return False

async def get_detail(announcement_id):
    async with _db_connection.execute("SELECT info FROM details WHERE announcement_id = ?", (announcement_id,)) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else None

async def update_detail(ann_id, info):
    exists = await get_detail(ann_id)
    sql = "UPDATE details SET info = ? WHERE announcement_id = ?" if exists else "INSERT INTO details (info, announcement_id) VALUES (?, ?)"
    await _db_connection.execute(sql, (info, ann_id))
    await _db_connection.commit()

async def get_due_announcements():
    async with _db_connection.execute("SELECT * FROM announcements WHERE is_active = 1") as cursor:
        rows = await cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, [datetime.fromisoformat(v) if k == 'next_run' else v for k, v in zip(cols, r)])) for r in rows]

async def update_announcement_next_run(ann_id, frequency):
    async with _db_connection.execute("SELECT next_run FROM announcements WHERE id = ?", (ann_id,)) as cursor:
        row = await cursor.fetchone()
        if not row: return None
        new_next = get_next_run_time(frequency, anchor_dt=datetime.fromisoformat(row[0]))
        if new_next:
            await _db_connection.execute("UPDATE announcements SET next_run = ? WHERE id = ?", (new_next.isoformat(), ann_id))
            await _db_connection.commit()
        return new_next

async def get_announcement(ann_id, server_id):
    async with _db_connection.execute("SELECT * FROM announcements WHERE id = ? AND server_id = ?", (ann_id, server_id)) as cursor:
        row = await cursor.fetchone()
        if row:
            cols = [d[0] for d in cursor.description]
            data = dict(zip(cols, row))
            data['next_run'] = datetime.fromisoformat(data['next_run'])
            return data
    return None

async def get_announcements_by_server(server_id):
    async with _db_connection.execute("SELECT * FROM announcements WHERE server_id = ? AND is_active = 1", (server_id,)) as cursor:
        rows = await cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, [datetime.fromisoformat(v) if k == 'next_run' else v for k, v in zip(cols, r)])) for r in rows]

async def stop_announcement(ann_id, server_id):
    await _db_connection.execute("UPDATE announcements SET is_active = 0 WHERE id = ? AND server_id = ?", (ann_id, server_id))
    await _db_connection.commit()
    return True

async def mark_announcement_inactive(ann_id):
    await _db_connection.execute("UPDATE announcements SET is_active = 0 WHERE id = ?", (ann_id,))
    await _db_connection.commit()

async def update_announcement_details(ann_id, server_id, updates):
    if 'next_run' in updates and isinstance(updates['next_run'], datetime):
        updates['next_run'] = updates['next_run'].isoformat()
    cols = list(updates.keys())
    sql = f"UPDATE announcements SET {', '.join([f'{c} = ?' for c in cols])} WHERE id = ? AND server_id = ?"
    await _db_connection.execute(sql, list(updates.values()) + [ann_id, server_id])
    await _db_connection.commit()
    return True

# Pool variable for compatibility with code that checks database availability
# Will be set to _db_connection when initialized, None otherwise
pool = None
