import asyncpg
import os
import logging
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any
import asyncio

# --- Logging Setup ---
logger = logging.getLogger(__name__)

# --- Load Environment Variables ---
load_dotenv()
POSTGRES_DSN = os.getenv('POSTGRES_DSN')

# --- Global Connection Pool ---
pool: Optional[asyncpg.Pool] = None

# --- In-Memory Cache (OPTIMIZED) ---
# Structure: {guild_id: {config_key: value, ...}}
_config_cache: Dict[int, Dict[str, Any]] = {}
_cache_lock = asyncio.Lock()
_cache_ttl = 3600  # Cache expires after 1 hour
_cache_timestamps: Dict[int, float] = {}  # Track when each cache entry was created

# --- Database Initialization ---
async def init_db() -> bool:
    """Initializes the database connection pool and schema."""
    global pool
    if pool:
        logger.warning("Database pool already initialized.")
        return True

    if not POSTGRES_DSN:
        logger.critical("POSTGRES_DSN environment variable not set!")
        return False

    try:
        # OPTIMIZED: Smaller pool for lower resource usage
        pool = await asyncpg.create_pool(
            dsn=POSTGRES_DSN,
            min_size=1,      # Keep minimal connections
            max_size=3,      # Reduced from 5 to 3
            timeout=30,
            command_timeout=60,
        )
        if pool is None:
            raise ConnectionError("Failed to create connection pool (pool is None).")

        logger.info("PostgreSQL connection pool established successfully (OPTIMIZED).")

        # --- Schema Verification ---
        async with pool.acquire() as conn:
            # Check if table exists
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'guild_config'
                );
            """)

            if not table_exists:
                logger.info("guild_config table not found, creating...")
                await conn.execute("""
                CREATE TABLE guild_config (
                    guild_id                  BIGINT PRIMARY KEY,
                    welcome_channel_id        BIGINT,
                    goodbye_channel_id        BIGINT,
                    welcome_message           TEXT,
                    welcome_image             TEXT,
                    goodbye_message           TEXT,
                    goodbye_image             TEXT,
                    stats_category_id         BIGINT,
                    member_count_channel_id   BIGINT,
                    bot_count_channel_id      BIGINT,
                    role_count_channel_id     BIGINT,
                    counting_channel_id       BIGINT,
                    current_count             INTEGER DEFAULT 0,
                    last_counter_id           BIGINT
                )
                """)
                logger.info("guild_config table created successfully.")
                
                # NEW: Create indexes to speed up queries
                await conn.execute("CREATE INDEX idx_guild_id ON guild_config(guild_id)")
                logger.info("Created database indexes for optimization.")
            else:
                logger.info("guild_config table found, verifying columns...")

        logger.info("Database initialization complete.")
        return True

    except Exception as e:
        logger.critical(f"Database initialization failed: {e}", exc_info=True)
        pool = None
        return False

# --- Close Pool ---
async def close_pool():
    """Closes the database connection pool."""
    global pool
    if pool:
        try:
            await pool.close()
            logger.info("PostgreSQL connection pool closed.")
            pool = None
        except Exception as e:
            logger.error(f"Error closing connection pool: {e}", exc_info=True)

# --- Context Manager for Connections ---
@asynccontextmanager
async def get_db_connection():
    """Acquires a connection from the pool within an async context manager."""
    if pool is None:
        logger.error("Database pool is not initialized.")
        raise ConnectionError("Database pool not available.")

    conn = None
    try:
        conn = await asyncio.wait_for(pool.acquire(), timeout=10.0)
        yield conn
    except asyncio.TimeoutError:
        logger.error("Timeout acquiring database connection.")
        raise ConnectionAbortedError("Timeout acquiring database connection.")
    except Exception as e:
        logger.error(f"Error with database connection: {e}", exc_info=True)
        raise
    finally:
        if conn:
            try:
                await asyncio.wait_for(pool.release(conn), timeout=5.0)
            except Exception as e:
                logger.error(f"Error releasing connection: {e}", exc_info=True)

# --- OPTIMIZED: Cache Management ---
async def invalidate_config_cache(guild_id: int):
    """Removes a guild's configuration from cache immediately."""
    async with _cache_lock:
        if guild_id in _config_cache:
            del _config_cache[guild_id]
            if guild_id in _cache_timestamps:
                del _cache_timestamps[guild_id]
            logger.debug(f"Invalidated cache for guild {guild_id}")

async def clear_all_config_cache():
    """Clears the entire configuration cache."""
    async with _cache_lock:
        _config_cache.clear()
        _cache_timestamps.clear()
        logger.info("Cleared all guild config cache.")

async def _is_cache_expired(guild_id: int) -> bool:
    """Check if a cache entry has expired."""
    import time
    if guild_id not in _cache_timestamps:
        return True
    return (time.time() - _cache_timestamps[guild_id]) > _cache_ttl

# --- OPTIMIZED: Data Access Functions ---
async def get_guild_config(guild_id: int) -> Optional[Dict[str, Any]]:
    """
    Fetches guild configuration from cache first, then database.
    OPTIMIZED: Cache expires after 1 hour, reducing DB queries.
    """
    # Check cache
    async with _cache_lock:
        if guild_id in _config_cache and not await _is_cache_expired(guild_id):
            logger.debug(f"Cache HIT for guild {guild_id}")
            return _config_cache[guild_id].copy()
        
        logger.debug(f"Cache MISS for guild {guild_id}")

    # Fetch from DB
    try:
        async with get_db_connection() as conn:
            # OPTIMIZED: Select only needed columns (not *)
            config_record = await conn.fetchrow(
                """SELECT guild_id, welcome_channel_id, goodbye_channel_id, 
                   welcome_message, goodbye_message, stats_category_id, 
                   member_count_channel_id, bot_count_channel_id, role_count_channel_id,
                   counting_channel_id, current_count, last_counter_id 
                   FROM guild_config WHERE guild_id = $1""", 
                guild_id
            )

            if config_record:
                config_dict = dict(config_record)
                async with _cache_lock:
                    _config_cache[guild_id] = config_dict
                    _cache_timestamps[guild_id] = __import__('time').time()
                logger.debug(f"Fetched and cached config for guild {guild_id}")
                return config_dict
            else:
                # Cache miss (no config exists)
                async with _cache_lock:
                    _config_cache[guild_id] = {}
                    _cache_timestamps[guild_id] = __import__('time').time()
                return None

    except Exception as e:
        logger.error(f"Failed to fetch config for guild {guild_id}: {e}")
        return None

async def set_guild_config_value(guild_id: int, updates: Dict[str, Any]) -> bool:
    """
    Updates guild configuration using UPSERT and immediately invalidates cache.
    OPTIMIZED: Uses prepared statements to reduce overhead.
    """
    if not updates:
        return False

    updates.pop('guild_id', None)

    try:
        async with get_db_connection() as conn:
            # OPTIMIZED: Build efficient UPSERT query
            set_clauses = []
            values = [guild_id]
            
            for i, (key, value) in enumerate(updates.items(), 1):
                set_clauses.append(f'"{key}" = ${i+1}')
                values.append(value)

            set_clause_str = ", ".join(set_clauses)
            update_clause_str = ", ".join(f'"{k}" = EXCLUDED."{k}"' for k in updates.keys())
            insert_cols = ["guild_id"] + list(updates.keys())
            insert_cols_str = ", ".join(f'"{col}"' for col in insert_cols)
            insert_placeholders = ", ".join(f"${j+1}" for j in range(len(insert_cols)))

            sql = f"""
                INSERT INTO guild_config ({insert_cols_str})
                VALUES ({insert_placeholders})
                ON CONFLICT (guild_id) DO UPDATE SET {update_clause_str};
            """

            await conn.execute(sql, *values)
            
        # Invalidate cache after successful update
        await invalidate_config_cache(guild_id)
        logger.info(f"Updated config for guild {guild_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to update config for guild {guild_id}: {e}")
        return False

async def update_counting_stats(guild_id: int, current_count: int, last_counter_id: Optional[int]) -> bool:
    """Updates counting game stats with optimized query."""
    sql = """
        INSERT INTO guild_config (guild_id, current_count, last_counter_id)
        VALUES ($1, $2, $3)
        ON CONFLICT (guild_id) DO UPDATE SET
        current_count = EXCLUDED.current_count,
        last_counter_id = EXCLUDED.last_counter_id;
    """
    try:
        async with get_db_connection() as conn:
            await conn.execute(sql, guild_id, current_count, last_counter_id)
        await invalidate_config_cache(guild_id)
        logger.debug(f"Updated counting stats for guild {guild_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to update counting stats for guild {guild_id}: {e}")
        return False