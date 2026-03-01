import discord
from discord.ext import commands
import os
import asyncio
from aiohttp import web

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("TOKEN environment variable is missing!")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ======================
# Dummy HTTP Server
# ======================

async def handle(request):
    return web.Response(text="Bot is running")

async def start_webserver():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

# ======================
# Discord Events
# ======================

@bot.event
async def on_ready():
    print(f"Bot connected as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Globally synced {len(synced)} commands")
    except Exception as e:
        print("Slash sync failed:", e)

async def load_extensions():
    await bot.load_extension("cogs.anti_spam")
    await bot.load_extension("cogs.forum_feedback")

async def main():
    await start_webserver()  # ← IMPORTANT
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
