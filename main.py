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
# DUMMY WEB SERVER (IMPORTANT FOR FLY)
# ======================

async def health(request):
    return web.Response(text="OK")

async def start_webserver():
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

# ======================
# READY EVENT
# ======================

@bot.event
async def on_ready():
    print(f"Bot connected as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print("Slash sync failed:", e)

# ======================
# LOAD COGS
# ======================

async def load_extensions():
    await bot.load_extension("cogs.anti_spam")
    print("Loaded anti_spam")

    await bot.load_extension("cogs.forum_feedback")
    print("Loaded forum_feedback")

# ======================
# MAIN
# ======================

async def main():
    await start_webserver()
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
