# bot.py

import os
from dotenv import load_dotenv
import discord
from discord.ext import commands

load_dotenv()  # loads the .env file

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("Environment variable DISCORD_TOKEN is not set. Create a .env file or set the variable.")

# Use explicit intents and enable message content if you need command/message content access
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

bot.run(TOKEN)
