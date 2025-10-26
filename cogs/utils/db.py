import asyncpg # Use asyncpg for PostgreSQL
import logging
import os
import asyncio # Import asyncio for timeout handling
from contextlib import asynccontextmanager
from typing import Optional, Any, Dict, List, Union

logger = logging.getLogger(__name__)

# Global variable to hold the connection pool
pool: Optional[asyncpg.Pool] = None

async def init_db():
    """Initializes the PostgreSQL database connection pool and schema."""
    global pool
    dsn = os.getenv('POSTGRES_DSN')
    if not dsn:
        logger.critical("POSTGRES_DSN environment variable not set. PostgreSQL connection failed.")
        # Decide how to handle this - raise error, exit, or fallback?
        # For now, we'll prevent the pool from being created.
        return

    try:
        # Lower the statement cache size if connection issues persist (especially on free tiers)
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5, statement_cache_size=50)
        logger.info("PostgreSQL connection pool established successfully.")

        # Ensure the table and columns exist
        async with pool.acquire() as conn:
            # Check if table exists
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'guild_config'
                );
            """)

            # Create table if it doesn't exist
            if not table_exists:
                logger.info("guild_config table not found, creating...")
                await conn.execute("""
                    CREATE TABLE guild_config (
                        guild_id                  BIGINT PRIMARY KEY, -- Use BIGINT for Discord IDs
                        welcome_channel_id        BIGINT,
                        goodbye_channel_id        BIGINT,
                        welcome_message           TEXT,
                        welcome_image             TEXT,
                        goodbye_message           TEXT,
                        goodbye_image             TEXT,
                        stats_category_id         BIGINT,
                        member_count_channel_id   BIGINT, -- Correct name with _id
                        bot_count_channel_id      BIGINT, -- Correct name with _id
                        role_count_channel_id     BIGINT, -- Correct name with _id
                        counting_channel_id       BIGINT,
                        current_count             INTEGER DEFAULT 0,
                        last_counter_id           BIGINT
                    );
                """)
                logger.info("guild_config table created.")
            else:
                 # Table exists, check for old column names and rename if necessary
                logger.info("guild_config table found, verifying schema...")
                existing_columns_rows = await conn.fetch("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'guild_config';
                """)
                existing_column_names = {col['column_name'] for col in existing_columns_rows}

                renames_to_attempt = {
                    "member_count_channel": "member_count_channel_id",
                    "bot_count_channel": "bot_count_channel_id",
                    "role_count_channel": "role_count_channel_id",
                    # Add other potential renames here if needed in the future
                }

                renamed_any = False
                for old_name, new_name in renames_to_attempt.items():
                    if old_name in existing_column_names and new_name not in existing_column_names:
                        try:
                            await conn.execute(f'ALTER TABLE guild_config RENAME COLUMN "{old_name}" TO "{new_name}";')
                            logger.info(f"Renamed column '{old_name}' to '{new_name}'.")
                            existing_column_names.remove(old_name) # Update our set
                            existing_column_names.add(new_name)
                            renamed_any = True
                        except asyncpg.PostgresError as e:
                            logger.error(f"Failed to rename column '{old_name}' to '{new_name}': {e}")
                    elif old_name in existing_column_names and new_name in existing_column_names:
                         # This case is odd, implies both exist. Log a warning.
                         logger.warning(f"Both '{old_name}' and '{new_name}' seem to exist in guild_config. No rename performed for this pair.")

                if renamed_any:
                     logger.info("Attempted schema renaming.")

                # Check for and add missing columns (using the CORRECT names)
                columns_to_ensure = {
                    "guild_id": "BIGINT PRIMARY KEY", # Make sure PK is checked if table exists
                    "welcome_channel_id": "BIGINT",
                    "goodbye_channel_id": "BIGINT",
                    "welcome_message": "TEXT",
                    "welcome_image": "TEXT",
                    "goodbye_message": "TEXT",
                    "goodbye_image": "TEXT",
                    "stats_category_id": "BIGINT",
                    "member_count_channel_id": "BIGINT", # Correct name
                    "bot_count_channel_id": "BIGINT",    # Correct name
                    "role_count_channel_id": "BIGINT",   # Correct name
                    "counting_channel_id": "BIGINT",
                    "current_count": "INTEGER DEFAULT 0",
                    "last_counter_id": "BIGINT"
                    # Add any future columns here with correct names
                }

                added_columns = False
                for col_name, col_type in columns_to_ensure.items():
                     # Skip primary key check, assume it exists if table does
                    if "PRIMARY KEY" in col_type:
                        continue
                    if col_name not in existing_column_names:
                        try:
                            # Add IF NOT EXISTS just in case, though the check above should prevent errors
                            await conn.execute(f"ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS {col_name} {col_type};")
                            logger.info(f"Added missing column: {col_name}")
                            added_columns = True
                        except asyncpg.PostgresError as e:
                             logger.error(f"Error adding column {col_name}: {e}")
                if added_columns:
                     logger.info("Database schema updated with new columns.")
                else:
                     logger.info("Database schema verified, no columns added.")

        logger.info("Database initialization check complete.")

    except (asyncpg.PostgresError, OSError) as e:
        logger.critical(f"Failed to connect to PostgreSQL or initialize schema: {e}", exc_info=True)
        pool = None # Ensure pool is None if connection fails
    except Exception as e:
        logger.critical(f"An unexpected error occurred during database initialization: {e}", exc_info=True)
        pool = None


async def close_pool():
    """Closes the PostgreSQL connection pool."""
    global pool
    if pool:
        try:
            # Use wait_closed() for graceful shutdown
            await pool.close()
            logger.info("PostgreSQL connection pool closed.")
            pool = None
        except Exception as e:
            logger.error(f"Error closing PostgreSQL pool: {e}", exc_info=True)

@asynccontextmanager
async def get_db_connection() -> asyncpg.Connection:
    """
    Acquires a connection from the pool using an asynchronous context manager.
    Raises an exception if the pool is not initialized.
    """
    if pool is None:
        logger.error("Database pool is not initialized. Cannot acquire connection.")
        raise ConnectionError("Database pool is not initialized.") # Or handle differently

    conn: Optional[asyncpg.Connection] = None
    try:
        # Use a timeout for acquiring connection
        conn = await asyncio.wait_for(pool.acquire(), timeout=10.0)
        yield conn
    except asyncio.TimeoutError:
         logger.error("Timeout occurred while waiting to acquire database connection.")
         raise ConnectionError("Timeout acquiring database connection.")
    except asyncpg.PostgresError as e:
        logger.error(f"Error acquiring or using database connection: {e}", exc_info=True)
        raise # Re-raise database errors
    except ConnectionError as e: # Catch if pool was None initially
         logger.error(f"Connection error: {e}")
         raise
    finally:
        if conn:
            # Use release with a timeout as well
             try:
                await asyncio.wait_for(pool.release(conn), timeout=5.0)
             except asyncio.TimeoutError:
                  logger.warning("Timeout occurred while releasing database connection.")
             except Exception as e:
                  logger.error(f"Error releasing database connection: {e}")


async def get_guild_config(guild_id: int) -> Optional[Dict[str, Any]]:
    """Fetches the configuration for a specific guild from PostgreSQL."""
    if pool is None:
        logger.error("Database pool not initialized, cannot get guild config.")
        return None
    try:
        # Use fetchrow which returns a single Record or None
        # asyncpg Record objects behave like dictionaries
        async with get_db_connection() as conn: # Use the context manager
            record = await conn.fetchrow("SELECT * FROM guild_config WHERE guild_id = $1", guild_id)
            # Convert asyncpg Record to dict before returning
            return dict(record) if record else None
    except asyncpg.PostgresError as e:
        logger.error(f"Error fetching config for guild {guild_id}: {e}", exc_info=True)
        return None
    except ConnectionError as e: # Handle case where pool wasn't initialized or timed out
         logger.error(f"Connection error fetching config for guild {guild_id}: {e}")
         return None


async def set_guild_config_value(guild_id: int, column: str, value: Any):
    """Sets a specific configuration value for a guild in PostgreSQL."""
    if pool is None:
        logger.error("Database pool not initialized, cannot set guild config value.")
        raise ConnectionError("Database pool is not initialized.")

    # Validate column name to prevent SQL injection (important!)
    allowed_columns = [
        "guild_id", # Include primary key if you might update it (unlikely here)
        "welcome_channel_id", "goodbye_channel_id", "welcome_message",
        "welcome_image", "goodbye_message", "goodbye_image", "stats_category_id",
        "member_count_channel_id", "bot_count_channel_id", "role_count_channel_id", # Correct names
        "counting_channel_id", "current_count", "last_counter_id"
    ]
    if column not in allowed_columns:
        logger.error(f"Attempted to set invalid config column: {column} for guild {guild_id}")
        raise ValueError(f"Invalid configuration column specified: {column}")

    try:
        async with get_db_connection() as conn: # Use the context manager
            # Use INSERT ... ON CONFLICT ... DO UPDATE for atomic upsert
            # Note: $1 = guild_id, $2 = value for the specific column
            # Use explicit EXCLUDED.column syntax for clarity and safety
            # Ensure column name is correctly quoted in case it's a reserved keyword
            # Using f-string for column name is safe *because* we validated it against allowed_columns
            sql = f"""
                INSERT INTO guild_config (guild_id, "{column}")
                VALUES ($1, $2)
                ON CONFLICT (guild_id) DO UPDATE SET
                "{column}" = EXCLUDED."{column}";
            """
            await conn.execute(sql, guild_id, value)
            logger.debug(f"Set config for guild {guild_id}: {column} = {value}")
    except asyncpg.PostgresError as e:
        logger.error(f"Error setting config for guild {guild_id} ({column}={value}): {e}", exc_info=True)
        raise # Re-raise database errors
    except ConnectionError as e: # Handle case where pool wasn't initialized or timed out
         logger.error(f"Connection error setting config for guild {guild_id}: {e}")
         raise

