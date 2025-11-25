Tilt-bot Development

This repository contains the source code for the Tilt-bot Discord bot.

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
