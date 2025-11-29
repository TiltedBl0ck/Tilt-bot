import sqlite3
import json
import os

# Configuration: Files are expected in the 'database' folder relative to this script
DB_PATH = "database/local.db"
GUILD_CONFIG_JSON = "database/guild_config.json"
ANNOUNCEMENTS_JSON = "database/announcements.json"

def get_data_list(json_data):
    """Helper to extract list of records from various JSON export structures."""
    if isinstance(json_data, list):
        return json_data
    if isinstance(json_data, dict):
        # Check for common wrapper keys often used in DB exports
        for key in ['rows', 'data', 'records', 'result', 'items']:
            if key in json_data and isinstance(json_data[key], list):
                print(f"   (Detected wrapper key: '{key}')")
                return json_data[key]
        # If no wrapper, assume it's a dict of objects (like Firebase)
        return list(json_data.values())
    return []

def migrate_guild_config(cursor):
    if not os.path.exists(GUILD_CONFIG_JSON):
        print(f"⚠️ {GUILD_CONFIG_JSON} not found. Skipping.")
        return

    print(f"📄 Processing {GUILD_CONFIG_JSON}...")
    try:
        with open(GUILD_CONFIG_JSON, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        data = get_data_list(raw_data)
        print(f"   Found {len(data)} potential entries.")

        if not data:
            print("   ⚠️ No data found to migrate.")
            return

        count = 0
        for entry in data:
            if not isinstance(entry, dict): continue
            
            # 1. Get Guild ID (Handle 'id' vs 'guild_id' mismatch)
            guild_id = entry.get('guild_id') or entry.get('id')
            
            if guild_id is None:
                print(f"   ⚠️ Skipping entry without ID: {entry}")
                continue

            # 2. Explicitly cast to int for SQLite
            try:
                guild_id = int(guild_id)
            except ValueError:
                print(f"   ⚠️ Skipping invalid ID: {guild_id}")
                continue

            # 3. Prepare Columns
            columns = [
                'guild_id', 'welcome_channel_id', 'goodbye_channel_id',
                'welcome_message', 'welcome_image', 'goodbye_message', 'goodbye_image',
                'stats_category_id', 'member_count_channel_id', 'bot_count_channel_id',
                'role_count_channel_id', 'counting_channel_id', 'current_count', 'last_counter_id'
            ]
            
            values = [guild_id]
            # Start loop from 1 since we handled guild_id manually
            for col in columns[1:]:
                val = entry.get(col)
                values.append(val)

            placeholders = ", ".join(["?"] * len(columns))
            sql = f"INSERT OR REPLACE INTO guild_config ({', '.join(columns)}) VALUES ({placeholders})"
            
            cursor.execute(sql, values)
            count += 1
            
        print(f"✅ Migrated {count} guild configs.")

    except Exception as e:
        print(f"❌ Error in guild config migration: {e}")

def migrate_announcements(cursor):
    if not os.path.exists(ANNOUNCEMENTS_JSON):
        print(f"⚠️ {ANNOUNCEMENTS_JSON} not found. Skipping.")
        return

    print(f"📄 Processing {ANNOUNCEMENTS_JSON}...")
    try:
        with open(ANNOUNCEMENTS_JSON, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            
        data = get_data_list(raw_data)
        print(f"   Found {len(data)} potential entries.")

        count = 0
        for entry in data:
            if not isinstance(entry, dict): continue

            columns = [
                'server_id', 'channel_id', 'message', 'frequency', 
                'created_at', 'next_run', 'created_by', 'is_active'
            ]
            
            values = []
            for col in columns:
                val = entry.get(col)
                # Handle boolean to int conversion for SQLite
                if col == 'is_active' and isinstance(val, bool):
                    val = 1 if val else 0
                values.append(val)

            placeholders = ", ".join(["?"] * len(columns))
            sql = f"INSERT INTO announcements ({', '.join(columns)}) VALUES ({placeholders})"
            
            cursor.execute(sql, values)
            count += 1

        print(f"✅ Migrated {count} announcements.")

    except Exception as e:
        print(f"❌ Error in announcements migration: {e}")

def main():
    print(f"🚀 Starting Migration to {DB_PATH}")
    
    # Ensure database directory exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    # Connect to database (creates it if missing)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Ensure Tables Exist (Schema Sync)
    cursor.execute("""
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
    
    cursor.execute("""
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
    
    migrate_guild_config(cursor)
    migrate_announcements(cursor)
    
    conn.commit()
    conn.close()
    print("✨ Database migration finished.")

if __name__ == "__main__":
    main()