import asyncpg
import os
import logging
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, Union, Tuple
import asyncio

# --- Logging Setup ---
logger = logging.getLogger(__name__)

# --- Load Environment Variables ---
load_dotenv()
POSTGRES_DSN = os.getenv('POSTGRES_DSN')

# --- Global Connection Pool ---
# Will be initialized by init_db()
pool: Optional[asyncpg.Pool] = None

# --- In-Memory Cache ---
# Structure: {guild_id: {config_key: value, ...}}
_config_cache: Dict[int, Dict[str, Any]] = {}
_cache_lock = asyncio.Lock() # Lock for cache modifications

# --- Database Initialization ---
async def init_db() -> bool:
    """Initializes the database connection pool and schema."""
    global pool
    if pool:
        logger.warning("Database pool already initialized.")
        return True # Indicate already initialized

    if not POSTGRES_DSN:
        logger.critical("POSTGRES_DSN environment variable not set!")
        return False

    try:
        # Create connection pool
        # Increase connection timeout if needed for Neon cold starts
        pool = await asyncpg.create_pool(
            dsn=POSTGRES_DSN,
            min_size=1,
            max_size=5, # Keep pool size modest
            timeout=30, # Connection acquisition timeout
            command_timeout=60 # Timeout for individual commands
        )
        if pool is None: # Check if pool creation actually succeeded
             raise ConnectionError("Failed to create connection pool (pool is None).")

        logger.info("PostgreSQL connection pool established successfully.")

        # --- Schema Verification and Creation/Update ---
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
            else:
                logger.info("guild_config table found, verifying columns...")
                # Get existing columns
                rows = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'guild_config' AND table_schema = 'public';")
                existing_columns = {row['column_name'] for row in rows}

                # Define expected columns and their types (simplified for ADD COLUMN)
                expected_columns = {
                    "guild_id": "BIGINT", "welcome_channel_id": "BIGINT", "goodbye_channel_id": "BIGINT",
                    "welcome_message": "TEXT", "welcome_image": "TEXT", "goodbye_message": "TEXT", "goodbye_image": "TEXT",
                    "stats_category_id": "BIGINT", "member_count_channel_id": "BIGINT", "bot_count_channel_id": "BIGINT",
                    "role_count_channel_id": "BIGINT", "counting_channel_id": "BIGINT",
                    "current_count": "INTEGER DEFAULT 0", "last_counter_id": "BIGINT"
                }

                added_column = False
                renamed_column = False

                # Rename old columns first if they exist
                rename_map = {
                    "member_count_channel": "member_count_channel_id",
                    "bot_count_channel": "bot_count_channel_id",
                    "role_count_channel": "role_count_channel_id",
                    # Add other potential renames here if necessary
                }
                for old_name, new_name in rename_map.items():
                     if old_name in existing_columns and new_name not in existing_columns:
                        try:
                            logger.info(f"Attempting to rename column '{old_name}' to '{new_name}'...")
                            await conn.execute(f'ALTER TABLE guild_config RENAME COLUMN "{old_name}" TO "{new_name}"')
                            logger.info(f"Renamed column '{old_name}' to '{new_name}'.")
                            existing_columns.remove(old_name)
                            existing_columns.add(new_name)
                            renamed_column = True
                        except asyncpg.PostgresError as e:
                            logger.error(f"Failed to rename column '{old_name}' to '{new_name}': {e}")


                # Add missing columns
                for col_name, col_type in expected_columns.items():
                    if col_name not in existing_columns:
                        try:
                            logger.info(f"Adding missing column: {col_name}...")
                            await conn.execute(f'ALTER TABLE guild_config ADD COLUMN "{col_name}" {col_type}')
                            logger.info(f"Added missing column: {col_name}")
                            added_column = True
                        except asyncpg.PostgresError as e:
                            logger.error(f"Failed to add column '{col_name}': {e}")


                if not added_column and not renamed_column:
                    logger.info("Database schema verified.")
                else:
                     logger.info("Database schema updated.")


        logger.info("Database initialization check complete.")
        return True # Indicate success

    except (asyncpg.PostgresError, OSError, ConnectionError) as e:
        logger.critical(f"Database connection/initialization failed: {e}", exc_info=True)
        pool = None # Ensure pool is None if init fails
        return False
    except Exception as e:
        logger.critical(f"An unexpected error occurred during database initialization: {e}", exc_info=True)
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
    else:
        logger.info("Connection pool was not initialized or already closed.")


# --- Context Manager for Connections ---
@asynccontextmanager
async def get_db_connection():
    """
    Acquires a connection from the pool within an async context manager.
    Includes timeout handling.
    """
    if pool is None:
        logger.error("Database pool is not initialized. Cannot get connection.")
        raise ConnectionError("Database pool not available.")

    conn = None
    try:
        # Acquire connection with a timeout
        conn = await asyncio.wait_for(pool.acquire(), timeout=15.0)
        yield conn
    except asyncio.TimeoutError:
        logger.error("Timeout occurred while acquiring database connection from pool.")
        raise ConnectionAbortedError("Timeout acquiring database connection.")
    except (asyncpg.PostgresError, OSError) as e:
         logger.error(f"Error acquiring or using database connection: {e}", exc_info=True)
         raise # Re-raise the original exception
    finally:
        if conn:
            try:
                # Release connection back to the pool
                await asyncio.wait_for(pool.release(conn), timeout=5.0)
            except asyncio.TimeoutError:
                logger.error("Timeout occurred while releasing database connection back to pool.")
            except Exception as e:
                logger.error(f"Error releasing database connection: {e}", exc_info=True)


# --- Cache Management ---
async def invalidate_config_cache(guild_id: int):
    """Removes a guild's configuration from the cache."""
    async with _cache_lock:
        if guild_id in _config_cache:
            del _config_cache[guild_id]
            logger.debug(f"Invalidated cache for guild {guild_id}")

async def clear_all_config_cache():
    """Clears the entire configuration cache."""
    async with _cache_lock:
        _config_cache.clear()
        logger.info("Cleared all guild config cache.")

# --- Data Access Functions ---
async def get_guild_config(guild_id: int) -> Optional[Dict[str, Any]]:
    """
    Fetches guild configuration, using cache first.
    Returns None if fetch fails or no config exists.
    """
    # 1. Check cache
    async with _cache_lock:
        cached_config = _config_cache.get(guild_id)
        if cached_config is not None:
             logger.debug(f"Cache hit for guild {guild_id}")
             # Return a copy to prevent accidental modification of cached dict
             return cached_config.copy()

    logger.debug(f"Cache miss for guild {guild_id}, fetching from DB.")

    # 2. Fetch from DB if not in cache
    try:
        async with get_db_connection() as conn:
            # fetchrow returns None if no row is found
            config_record = await conn.fetchrow("SELECT * FROM guild_config WHERE guild_id = $1", guild_id)

            if config_record:
                # Convert asyncpg.Record to dict and store in cache
                config_dict = dict(config_record)
                async with _cache_lock:
                    _config_cache[guild_id] = config_dict
                logger.debug(f"Fetched and cached config for guild {guild_id}")
                return config_dict # Return the fetched dict
            else:
                # Store an empty dict to indicate we checked and found nothing (avoids repeated DB hits for non-configured guilds)
                # You might choose *not* to cache misses if you expect configs to appear often without bot interaction
                async with _cache_lock:
                    _config_cache[guild_id] = {} # Cache the miss
                logger.debug(f"No config found for guild {guild_id}, cached miss.")
                return None # Explicitly return None if no record found

    except (ConnectionError, asyncpg.PostgresError) as e:
        logger.error(f"Failed to fetch config for guild {guild_id}: {e}")
        return None # Return None on DB error
    except Exception as e:
        logger.error(f"Unexpected error fetching config for guild {guild_id}: {e}", exc_info=True)
        return None

async def set_guild_config_value(guild_id: int, updates: Dict[str, Any]) -> bool:
    """
    Updates specific configuration values for a guild using UPSERT.
    Invalidates the cache for the guild upon successful update.
    Returns True on success, False on failure.
    """
    if not updates:
        logger.warning("set_guild_config_value called with no updates.")
        return False

    # Filter out guild_id from updates if present, it's the conflict target
    updates.pop('guild_id', None)

    set_clauses = []
    values = []
    i = 1 # Start placeholders from $1

    # Conflict target is guild_id ($1)
    values.append(guild_id)

    # Build SET clause and collect values for INSERT/UPDATE
    for key, value in updates.items():
        # Ensure key is a valid column name (basic check)
        if not key.replace('_', '').isalnum():
             logger.error(f"Invalid column name provided for update: {key}")
             return False
        set_clauses.append(f'"{key}" = ${i+1}') # Use EXCLUDED.column for upsert
        values.append(value)
        i += 1

    if not set_clauses: # Should not happen if updates is not empty, but safeguard
        logger.error("No valid update clauses generated.")
        return False

    set_clause_str = ", ".join(set_clauses)
    update_clause_str = ", ".join(f'"{key}" = EXCLUDED."{key}"' for key in updates.keys()) # For ON CONFLICT
    insert_cols = ["guild_id"] + list(updates.keys())
    insert_cols_str = ", ".join(f'"{col}"' for col in insert_cols)
    insert_placeholders = ", ".join(f"${j+1}" for j in range(len(insert_cols)))


    sql = f"""
        INSERT INTO guild_config ({insert_cols_str})
        VALUES ({insert_placeholders})
        ON CONFLICT (guild_id) DO UPDATE SET
        {update_clause_str};
    """

    try:
        async with get_db_connection() as conn:
            await conn.execute(sql, *values)
        # Invalidate cache only after successful DB operation
        await invalidate_config_cache(guild_id)
        logger.info(f"Updated config for guild {guild_id}: {updates.keys()}")
        return True
    except (ConnectionError, asyncpg.PostgresError) as e:
        logger.error(f"Failed to update config for guild {guild_id}: {e}")
        return False
    except Exception as e:
         logger.error(f"Unexpected error updating config for guild {guild_id}: {e}", exc_info=True)
         return False

async def update_counting_stats(guild_id: int, current_count: int, last_counter_id: Optional[int]) -> bool:
    """
    Specifically updates counting game stats and invalidates cache.
    Uses UPSERT to ensure the row exists.
    Returns True on success, False on failure.
    """
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
        # Invalidate cache after successful DB operation
        await invalidate_config_cache(guild_id)
        logger.debug(f"Updated counting stats for guild {guild_id}: count={current_count}, last_counter={last_counter_id}")
        return True
    except (ConnectionError, asyncpg.PostgresError) as e:
        logger.error(f"Failed to update counting stats for guild {guild_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error updating counting stats for guild {guild_id}: {e}", exc_info=True)
        return False

