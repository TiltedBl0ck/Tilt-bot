Tilt-Bot v2.0.0
Tilt-Bot is a modern, feature-rich, and easy-to-use Discord bot built with the latest discord.py library. It leverages slash commands and an interactive UI for a seamless user experience.

✨ Features
🤖 AI Chat: Have a conversation with the bot using a free Gemini API proxy from Puter.com. Just mention the bot or use the /chat command.

👋 Welcome & Goodbye: Automatically greet new members and say goodbye to those who leave with customizable messages and images.

📊 Server Stats: Set up voice channels that automatically display your server's member and bot counts.

🛠️ Utility Commands: A full suite of tools to manage your server and get information, including /serverinfo, /userinfo, /avatar, and more.

🛡️ Moderation: Simple and effective moderation tools, like /clear to bulk-delete messages.

⚙️ Interactive Setup: Easy-to-use menus, dropdowns, and pop-up forms for configuring the bot without needing to remember complex commands.

📚 Modern Help Command: A new, interactive help menu with dropdowns to easily browse command categories.

🚀 Getting Started
Prerequisites
Python 3.10 or higher

A Discord Bot Token

Installation & Setup
Clone the Repository

git clone [https://github.com/TiltedBl0ck/tilt-bot.git](https://github.com/TiltedBl0ck/tilt-bot.git)
cd tilt-bot

Install Dependencies
It's recommended to use a virtual environment.

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install the required packages
pip install -r requirements.txt

Configure the Bot
The bot uses a .env file to store your bot token.

Find the file named .env.example.

Create a copy of it and rename the copy to .env.

Open the new .env file and add your secret token. Do not use spaces or quotes.

# Correct .env format
BOT_TOKEN=your_discord_bot_token_here

You can get your BOT_TOKEN from the Discord Developer Portal.

Run the Bot

python main.py

The bot should now be online and ready to go! The first time you run it, a Database.db file and a bot.log file will be created.

Slash Command Overview
Here is a list of the main commands available. Use the new /help command in your server for a complete, interactive breakdown!

/help: Shows the main interactive help menu.

/chat <prompt>: Talk to the bot's AI.

/ping: Checks the bot's latency.

/botinfo: Shows stats about Tilt-Bot.

/serverinfo: Displays detailed information about the server.

/userinfo [member]: Shows info about a specific user.

/clear <count>: Deletes a specified number of messages.

/setup <welcome/goodbye/serverstats>: Interactive menus to set up bot features.

/config <welcome/goodbye>: Edit the content of your welcome/goodbye messages.

This project is licensed under the MIT License.