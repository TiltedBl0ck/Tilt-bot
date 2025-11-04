Tilt-bot Development

This repository contains the source code for the Tilt-bot Discord bot.

Setup Instructions

1. Prerequisites

Python 3.10+ installed on your system.

A Discord Bot Application created, and a Bot Token obtained.

A Gemini API Key.

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


Note: You must run this command every time you open a new terminal session to work on the bot. If you see the name (.venv) prefixing your terminal prompt, the environment is active.

3. Install Dependencies

With the virtual environment activated, install the required Python packages:

pip install -r requirements.txt


4. Configuration

Create an environment file to store your sensitive tokens and keys.

Copy the example file:

cp .env.example .env


Edit the newly created .env file and replace the placeholder values with your actual keys:

# .env file content
DISCORD_BOT_TOKEN="YOUR_DISCORD_BOT_TOKEN_HERE"
GEMINI_API_KEY="YOUR_GEMINI_API_KEY_HERE"
# Other configuration variables...


5. Running the Bot

With your virtual environment activated and configuration set up, you can run the bot:

python3 main.py


The contents of this README reflect the current state of the Tilt-bot development branch.