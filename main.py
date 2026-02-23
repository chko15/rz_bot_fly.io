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
        synced = await bot.tree.sync()
        print(f"Globally synced {len(synced)} commands")
    except Exception as e:
        print("Slash sync failed:", e)

@bot.tree.error
async def on_app_command_error(interaction, error):
    print("Slash Error:", error)
    if interaction.response.is_done():
        await interaction.followup.send("Error occurred.", ephemeral=True)
    else:
        await interaction.response.send_message("Error occurred.", ephemeral=True)

async def load_extensions():
    await bot.load_extension("cogs.anti_spam")
    await bot.load_extension("cogs.forum_feedback")

async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
