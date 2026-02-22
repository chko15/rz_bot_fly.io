import discord
from discord.ext import commands
from datetime import timedelta
from collections import defaultdict
import json
import os
import hashlib
import aiohttp

LOG_CHANNEL_ID = 1466507799361229003

TIME_WINDOW_SECONDS = 30
MIN_CHANNEL_SPREAD = 2
TIMEOUT_DURATION = 10
STRIKE_RESET_TIME = 60
MAX_STRIKES = 2

WHITELIST_ROLE_IDS = [
    1427543936829882480,
    1464630512294564030,
    1427554165235646496
]

STRIKE_FILE = "strikes.json"


class AntiSpam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_attachment_history = defaultdict(list)
        self.user_strikes = self.load_json()

    def load_json(self):
        if os.path.exists(STRIKE_FILE):
            with open(STRIKE_FILE, "r") as f:
                return json.load(f)
        return {}

    def save_json(self):
        with open(STRIKE_FILE, "w") as f:
            json.dump(self.user_strikes, f)

    def is_whitelisted(self, member: discord.Member):
        for role in member.roles:
            if role.id in WHITELIST_ROLE_IDS:
                return True
        return False

    async def get_file_hash(self, url):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.read()
                return hashlib.sha256(data).hexdigest()

    @commands.Cog.listener()
    async def on_message(self, message):

        if message.author.bot:
            return

        if self.is_whitelisted(message.author):
            return

        now = discord.utils.utcnow()

        if message.attachments:

            for attachment in message.attachments:
                file_hash = await self.get_file_hash(attachment.url)

                self.user_attachment_history[message.author.id].append({
                    "hash": file_hash,
                    "channel": message.channel.id,
                    "time": now
                })

            self.user_attachment_history[message.author.id] = [
                entry for entry in self.user_attachment_history[message.author.id]
                if now - entry["time"] < timedelta(seconds=TIME_WINDOW_SECONDS)
            ]

            hashes = defaultdict(set)

            for entry in self.user_attachment_history[message.author.id]:
                hashes[entry["hash"]].add(entry["channel"])

            for file_hash, channels in hashes.items():
                if len(channels) >= MIN_CHANNEL_SPREAD:
                    await self.punish_user(message)
                    return

    async def punish_user(self, message):

        now = discord.utils.utcnow()

        try:
            await message.delete()
        except:
            pass

        user_id = str(message.author.id)

        if user_id not in self.user_strikes:
            self.user_strikes[user_id] = []

        self.user_strikes[user_id] = [
            t for t in self.user_strikes[user_id]
            if (now - discord.utils.parse_time(t)) < timedelta(minutes=STRIKE_RESET_TIME)
        ]

        self.user_strikes[user_id].append(now.isoformat())
        strike_count = len(self.user_strikes[user_id])

        self.save_json()

        if strike_count >= MAX_STRIKES:
            await message.guild.ban(message.author, reason="Repeated spam")
            action = "User BANNED"
        else:
            await message.author.timeout(
                timedelta(minutes=TIMEOUT_DURATION),
                reason="Spam detected"
            )
            action = "User timed out"

        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(
                title="🚨 Spam Detected",
                color=discord.Color.red(),
                timestamp=now
            )
            embed.add_field(name="User", value=str(message.author), inline=False)
            embed.add_field(name="Action", value=action, inline=False)
            embed.add_field(name="Strike Count", value=str(strike_count), inline=False)
            await log_channel.send(embed=embed)

    @commands.hybrid_command(name="view_strikes")
    async def view_strikes(self, ctx, member: discord.Member):
        strikes = len(self.user_strikes.get(str(member.id), []))
        await ctx.send(f"{member.mention} has {strikes} strike(s).")


async def setup(bot):
    await bot.add_cog(AntiSpam(bot))
