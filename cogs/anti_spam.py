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

    def is_whitelisted(self, member):
        return any(role.id in WHITELIST_ROLE_IDS for role in member.roles)

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

            # cleanup old
            self.user_attachment_history[message.author.id] = [
                e for e in self.user_attachment_history[message.author.id]
                if now - e["time"] < timedelta(seconds=TIME_WINDOW_SECONDS)
            ]

            hashes = defaultdict(set)
            for entry in self.user_attachment_history[message.author.id]:
                hashes[entry["hash"]].add(entry["channel"])

            for file_hash, channels in hashes.items():
                if len(channels) >= MIN_CHANNEL_SPREAD:
                    await self.punish(message)
                    return

    async def punish(self, message):
        now = discord.utils.utcnow()

        content = message.content or "No text"
        attachments = [a.url for a in message.attachments]
        jump = message.jump_url

        try:
            await message.delete()
        except:
            pass

        uid = str(message.author.id)
        self.user_strikes.setdefault(uid, [])

        self.user_strikes[uid] = [
            t for t in self.user_strikes[uid]
            if (now - discord.utils.parse_time(t)) < timedelta(minutes=STRIKE_RESET_TIME)
        ]

        self.user_strikes[uid].append(now.isoformat())
        strikes = len(self.user_strikes[uid])
        self.save_json()

        if strikes >= MAX_STRIKES:
            await message.guild.ban(message.author)
            action = "BANNED"
        else:
            await message.author.timeout(timedelta(minutes=TIMEOUT_DURATION))
            action = "TIMEOUT"

        log = self.bot.get_channel(LOG_CHANNEL_ID)
        if log:
            embed = discord.Embed(
                title="🚨 Cross-Channel Spam Detected",
                color=discord.Color.red(),
                timestamp=now
            )
            embed.add_field(name="User", value=f"{message.author} ({message.author.id})", inline=False)
            embed.add_field(name="Action", value=action, inline=False)
            embed.add_field(name="Strikes", value=str(strikes), inline=False)
            embed.add_field(name="Message", value=content[:1000], inline=False)

            if attachments:
                embed.add_field(name="Attachments", value="\n".join(attachments), inline=False)

            embed.add_field(name="Jump", value=jump, inline=False)

            await log.send(embed=embed)

    @commands.hybrid_command(name="view_strikes")
    async def view_strikes(self, ctx, member: discord.Member):
        strikes = len(self.user_strikes.get(str(member.id), []))
        await ctx.send(f"{member.mention} has {strikes} strike(s).", ephemeral=True)


async def setup(bot):
    await bot.add_cog(AntiSpam(bot))
