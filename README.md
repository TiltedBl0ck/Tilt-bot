Tilt-bot Development
This repository contains the source code for the Tilt-bot Discord bot.

🚀 Release Notes
v1.3.0 - The "Security, Moderation & Stability" Update
This update improves bot safety, isolates AI memory per guild, and refines moderation behavior for more reliable day-to-day use.

✨ New Features & Fixes
Per-Guild Memory Isolation: AI memory is now stored per server using the guild_memory database table instead of a shared global memory file.

Prompt Hardening: Added safety-prefix enforcement, prompt length limits, and jailbreak-pattern filtering to reduce prompt injection risk.

Web Search Protection: Added SSRF protection for web scraping by blocking private and internal IP ranges and validating redirects.

Database File Hardening: SQLite directory and file permissions were tightened for safer local deployment.

AI Cooldowns: Added per-user cooldowns to AI commands to reduce abuse and spam.

History Controls: Added bounded channel history with cleanup logic to prevent unbounded memory growth.

Safer Prompt Reflection: User prompts shown back in bot replies are now escaped and capped.

Improved /clear Command: /clear can now remove recent messages from other users in server channels when permissions allow.

DM Limitation Handling: In DMs, /clear only deletes the bot's own messages, matching Discord API limitations.

v1.2.1 - The "AI SDK & Dependency Hardening" Update
This update migrates the AI layer to the new Google Gen AI SDK and adds startup dependency validation.

✨ New Features & Fixes
SDK Migration: Replaced the deprecated google-generativeai package with the new google-genai[aiohttp] SDK, enabling native async API calls via client.aio.

Exponential Backoff: Gemini model calls now retry up to 3 times with jitter on rate-limit (429) errors before rotating to the next model.

Async History Locks: Per-channel asyncio.Lock prevents race conditions when multiple users message simultaneously in the same channel.

Safety Settings Fix: Removed BLOCK_NONE from HATE_SPEECH and DANGEROUS_CONTENT categories to comply with Discord ToS and Google API policies.

Dependency Preflight: main.py now validates requirements.txt on startup using importlib.metadata. Set AUTO_INSTALL_DEPS=1 to auto-install missing packages.

UTC Timestamps: System prompt now uses datetime.now(timezone.utc) for deterministic timestamps regardless of host timezone.

Fixed Discord Chunking: Response chunking now accounts for header length to prevent messages exceeding the 2000-character Discord limit.

Removed Fake Model: gemini-3-pro-preview was not a real model and has been removed from the rotation list.

v1.2.0 - The "Security & Stability" Update
This critical update addresses several security vulnerabilities and improves the overall stability of the bot.

✨ New Features & Fixes
Security Hardening: Added administrator permission checks to the announcement system to prevent unauthorized access.

Race Condition Fix: Implemented atomic database updates for the counting game to ensure count accuracy during high traffic.

Database Safety: Added strict column validation and atomic operations to prevent SQL injection and data inconsistencies.

Log Management: Implemented log rotation to prevent log files from consuming excessive disk space.

Improved Error Handling: The /clear command now gracefully handles Discord's 14-day message deletion limit.

v1.1.0 - The "Configuration & Logging" Update
This update focuses on improving the bot's configuration management and logging capabilities.

✨ New Features & Fixes
Centralized Configuration: The bot_memory.json and bot.log files are now stored in the configs directory, providing a cleaner project structure.

Path Fixes: The bot's code has been updated to correctly locate and use the new paths for configuration and log files.

v1.0.1 - The "Smart & Scheduled" Update
We are excited to announce version 1.0.1, bringing major improvements to stability, intelligence, and server management.

✨ New Features
📢 Advanced Announcement System (/announce):

Recurring Schedules: Set announcements to repeat every minute, hour, day, or month.

Database Persistence: Announcements are stored in SQLite and survive bot restarts.

Management: Easily create, list, preview, and stop announcements via commands.

🧠 Improved AI Chat (/chat):

Web Search Capability: The bot can now fetch real-time information from the web.

Smart Fallback: Automatically switches from Gemini to Perplexity AI if quotas are exceeded or for specific real-time queries.

Enhanced Context: Better memory management for more natural conversations.

⚡ Database Optimizations:

Connection Pooling: Implemented async connection handling for high-performance concurrent operations.

Smart Caching: Guild configurations are cached in memory to reduce database load and improve response times.

v1.0.0 - The Foundation
The initial release establishing the core functionality of Tilt-bot.

🛡️ Moderation Suite: Essential tools to keep your server safe (/kick, /ban, /timeout, /clear).

👋 Welcome & Goodbye: Customizable messages and images to greet new members (/setup welcome, /setup goodbye).

📊 Server Statistics: Live counters for Members, Bots, and Roles displayed in voice channel names (/setup serverstats).

ℹ️ Utility Commands: Quick access to user avatars, server info, and bot latency (/avatar, /userinfo, /serverinfo, /ping).

🤖 Basic AI Chat: Early integration with Google Gemini for conversational interactions.

Setup Instructions
Prerequisites
Python 3.10+ installed on your system.

A Discord Bot Application created, and a Bot Token obtained.

A Google Gemini API Key (Get one from Google AI Studio).

(Optional) A Perplexity API key for fallback AI features.

Virtual Environment Setup (Recommended)
It is highly recommended to use a virtual environment to manage dependencies.

Create the virtual environment:

bash
python3 -m venv .venv
Activate the virtual environment:

Linux/macOS:

bash
source .venv/bin/activate
Windows (Command Prompt):

text
.venv\Scripts\activate.bat
Windows (PowerShell):

powershell
.venv\Scripts\Activate.ps1
Install Dependencies
With the virtual environment activated, install the required Python packages:

bash
pip install -r requirements.txt
Note: This project uses the new google-genai[aiohttp] SDK. If upgrading from a previous version, remove the old package first:

bash
pip uninstall google-generativeai -y
Configuration
Create an environment file to store your sensitive tokens and keys.

Copy the example file:

bash
cp .env.example .env
(On Windows, just copy and rename .env.example to .env)

Edit the newly created .env file and replace the placeholder values with your actual keys:

text
BOT_TOKEN="YOUR_DISCORD_BOT_TOKEN_HERE"
GEMINI_API_KEY="YOUR_GOOGLE_AI_STUDIO_KEY"
PERPLEXITY_API_KEY="YOUR_PERPLEXITY_API_KEY"

# Optional: set to 1 to let the bot auto-install missing dependencies on startup
AUTO_INSTALL_DEPS=0
Important Notes
configs/bot_memory.json should not be committed to the repository.

Use configs/bot_memory.example.json as a template only.

Guild-specific AI memory is now stored in the guild_memory database table.

The database file is stored at database/local.db.

Running the Bot
With your virtual environment activated and configuration set up, you can run the bot:

bash
python3 main.py