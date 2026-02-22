import discord
from discord.ext import commands
import os
import asyncio
 
TOKEN = os.getenv("TOKEN")
GUILD_ID = 1174287094630326352  # Your server ID

if not TOKEN:
    raise ValueError("TOKEN environment variable is missing!")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot connected as {bot.user}")

    try:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        print("Slash sync failed:", e)

async def load_extensions():
    await bot.load_extension("cogs.anti_spam")
    await bot.load_extension("cogs.forum_feedback")

async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)
