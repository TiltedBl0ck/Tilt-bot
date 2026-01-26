Tilt-bot Development

This repository contains the source code for the Tilt-bot Discord bot.

🚀 Release Notes

**v1.1.0 - The "Configuration & Logging" Update**

This update focuses on improving the bot's configuration management and logging capabilities.

✨ **New Features & Fixes**

*   **Centralized Configuration:** The `bot_memory.json` and `bot.log` files are now stored in the `configs` directory, providing a cleaner project structure.
*   **Path Fixes:** The bot's code has been updated to correctly locate and use the new paths for configuration and log files.

v1.0.1 - The "Smart & Scheduled" Update

We are excited to announce version 1.0.1, bringing major improvements to stability, intelligence, and server management.

✨ New Features

📢 Advanced Announcement System (/announce):

Recurring Schedules: Set announcements to repeat every minute, hour, day, or month.

Database Persistence: Announcements are stored in PostgreSQL and survive bot restarts.

Management: Easily create, list, preview, and stop announcements via commands.

🧠 Improved AI Chat (/chat):

Web Search Capability: The bot can now fetch real-time information from the web.

Smart Fallback: Automatically switches from Gemini to Perplexity AI if quotas are exceeded or for specific real-time queries.

Enhanced Context: Better memory management for more natural conversations.

⚡ Database Optimizations:

Connection Pooling: Implemented asyncpg connection pooling for high-performance concurrent handling.

Smart Caching: Guild configurations are cached in memory to reduce database load and improve response times.

v1.0.0 - The Foundation

The initial release establishing the core functionality of Tilt-bot.

🛡️ Moderation Suite: Essential tools to keep your server safe (/kick, /ban, /timeout, /clear).

👋 Welcome & Goodbye: Customizable messages and images to greet new members (/setup welcome, /setup goodbye).

📊 Server Statistics: Live counters for Members, Bots, and Roles displayed in voice channel names (/setup serverstats).

ℹ️ Utility Commands: Quick access to user avatars, server info, and bot latency (/avatar, /userinfo, /serverinfo, /ping).

🤖 Basic AI Chat: Early integration with Google Gemini for conversational interactions.

Setup Instructions

1. Prerequisites

Python 3.10+ installed on your system.

A Discord Bot Application created, and a Bot Token obtained.

A Google Gemini API Key (Get one from Google AI Studio).

A PostgreSQL Database (e.g., local install or cloud provider).

2. Virtual Environment Setup (Recommended)

It is highly recommended to use a virtual environment to manage dependencies.

Create the virtual environment:

python3 -m venv .venv


Activate the virtual environment:

Linux/macOS:

source .venv/bin/activate


Windows (Command Prompt):

.venv\Scripts\activate.bat


Windows (PowerShell):

.venv\Scripts\Activate.ps1


3. Install Dependencies

With the virtual environment activated, install the required Python packages:

pip install -r requirements.txt


4. Configuration

Create an environment file to store your sensitive tokens and keys.

Copy the example file:

cp .env.example .env


(On Windows, just copy and rename .env.example to .env)

Edit the newly created .env file and replace the placeholder values with your actual keys:

BOT_TOKEN="YOUR_DISCORD_BOT_TOKEN_HERE"
GEMINI_API_KEY="YOUR_GOOGLE_AI_STUDIO_KEY"
POSTGRES_DSN="postgresql://user:password@localhost/dbname"


5. Running the Bot

With your virtual environment activated and configuration set up, you can run the bot:

python3 main.py
