import os
import logging
import json
import asyncpg

# Global variable to hold the connection pool instance
pool = None
logger = logging.getLogger(__name__)

# --- Database Initialization ---

async def init_db() -> None:
    """Initializes the PostgreSQL connection pool and creates tables."""
    global pool

    # Load config to find the database DSN environment variable name
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
            dsn_env_var = config.get("database", {}).get("dsn_env_var", "POSTGRES_DSN")
    except (FileNotFoundError, json.JSONDecodeError):
        logger.error("Configuration file (config.json) not found or invalid.")
        return

    # Fetch the connection string (DSN)
    dsn = os.getenv(dsn_env_var)
    if not dsn:
        logger.critical(f"Database DSN environment variable ('{dsn_env_var}') not set. PostgreSQL connection failed.")
        return

    logger.info("Attempting to connect to PostgreSQL database...")

    try:
        # Create a connection pool using the DSN
        pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=1,  # Minimum connections to keep open
            max_size=10  # Maximum concurrent connections
        )
        logger.info("PostgreSQL connection pool established successfully.")

        # Execute table creation queries
        await create_tables()

    except Exception as e:
        logger.critical(f"Failed to connect to PostgreSQL or initialize tables: {e}")


async def create_tables() -> None:
    """Creates the necessary tables if they do not already exist."""
    if pool is None:
        logger.error("Cannot create tables: Database pool is not initialized.")
        return

    # Use a connection from the pool to execute the creation schema
    async with pool.acquire() as conn:
        # Guild Configuration Table (for welcome, stats, etc.)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id BIGINT PRIMARY KEY,
                welcome_channel_id BIGINT DEFAULT NULL,
                welcome_message TEXT DEFAULT 'Welcome {member} to {guild}!',
                goodbye_channel_id BIGINT DEFAULT NULL,
                goodbye_message TEXT DEFAULT 'Goodbye {member}. We will miss you!',
                member_count_channel BIGINT DEFAULT NULL,
                bot_count_channel BIGINT DEFAULT NULL,
                counting_channel_id BIGINT DEFAULT NULL,
                counting_next_number INTEGER DEFAULT 1,
                counting_last_user_id BIGINT DEFAULT NULL
            );
        """)
        
        # User Configuration Table (e.g., for user-specific settings, though this example uses guild context)
        # You would typically add more specific tables here based on bot features.
        
        logger.info("Database tables verified and created if necessary.")

# --- Helper Functions (Example usage, replace existing db interaction logic with this pattern) ---

async def get_guild_config(guild_id: int):
    """Fetches a guild's configuration from the database."""
    if pool is None:
        return None
    
    query = "SELECT * FROM guild_config WHERE guild_id = $1;"
    # fetchrow returns a single record as a record object (like a dict)
    record = await pool.fetchrow(query, guild_id)
    return record


async def update_welcome_channel(guild_id: int, channel_id: int):
    """Inserts or updates the welcome channel ID for a guild."""
    if pool is None:
        return

    # Use ON CONFLICT DO UPDATE to handle both inserts and updates efficiently
    query = """
        INSERT INTO guild_config (guild_id, welcome_channel_id) 
        VALUES ($1, $2)
        ON CONFLICT (guild_id) DO UPDATE SET 
            welcome_channel_id = $2;
    """
    await pool.execute(query, guild_id, channel_id)


# Function to close the pool gracefully on shutdown (use in main.py)
async def close_pool():
    """Closes the PostgreSQL connection pool."""
    global pool
    if pool:
        await pool.close()
        logger.info("PostgreSQL connection pool closed.")
        pool = None

# You will now replace all uses of aiosqlite in other cogs/files 
# with calls to the global 'pool' object (e.g., pool.fetchval, pool.execute).
