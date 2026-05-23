import discord
from discord.ext import commands
from datetime import timedelta
from collections import defaultdict
import json
import os
import hashlib
import aiohttp
import re
import asyncio

LOG_CHANNEL_ID = 1466507799361229003

TIME_WINDOW_SECONDS = 30
MIN_CHANNEL_SPREAD = 2
TIMEOUT_DURATION = 10
STRIKE_RESET_TIME = 86400
MAX_STRIKES = 3

# =========================
# CONFIG
# =========================

ATTACHMENT_LIMIT_CHANNELS = [
    1427520803678851112,
]

ATTACHMENT_COOLDOWN_MINUTES = 2

DUPLICATE_TIME_WINDOW = 20
DUPLICATE_THRESHOLD = 3

WHITELIST_ROLE_IDS = [
    1427543936829882480,
    1450921642568978635,
    1427538203304398878,
    1464630512294564030,
    1427554165235646496,
    1482773092890574989
]

STRIKE_FILE = "strikes.json"

# =========================
# SCAM PATTERNS
# =========================

SCAM_PATTERNS = [
    r"check\s+my\s+b[i1l][o0]",
    r"check\s+my\s+pr[o0]f[i1l]le",
]

SCAM_KEYWORDS = [
    "free nitro",
    "claim reward",
    "steam gift",
    "gift link",
    "airdrop",
    "limited offer",
]

URL_REGEX = r"(https?:\/\/[^\s]+)"

def normalize_text(text: str):
    text = text.lower()
    text = re.sub(r"^#+\s*", "", text)
    text = text.replace("1", "i").replace("0", "o").replace("l", "i")
    return text


class AntiSpam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_attachment_history = defaultdict(list)
        self.user_message_history = defaultdict(list)
        self.user_strikes = self.load_json()
        self.user_last_attachment_time = {}

    # =========================
    # JSON
    # =========================

    def load_json(self):
        if os.path.exists(STRIKE_FILE):
            with open(STRIKE_FILE, "r") as f:
                return json.load(f)
        return {}

    def save_json(self):
        with open(STRIKE_FILE, "w") as f:
            json.dump(self.user_strikes, f)

    # =========================
    # WHITELIST
    # =========================

    def is_whitelisted(self, member):
        return any(role.id in WHITELIST_ROLE_IDS for role in member.roles)

    # =========================
    # HASH
    # =========================

    async def get_file_hash(self, url):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.read()
                return hashlib.sha256(data).hexdigest()

    # =========================
    # LOG FUNCTION
    # =========================

    async def send_log(self, message, action, strikes, spam_type):

        now = discord.utils.utcnow()

        content = message.content or "No text"
        attachments = [a.url for a in message.attachments]
        jump = message.jump_url

        log = self.bot.get_channel(LOG_CHANNEL_ID)

        if log:
            embed = discord.Embed(
                title=f"🚨 {spam_type}",
                color=discord.Color.red(),
                timestamp=now
            )

            embed.add_field(
                name="User",
                value=f"{message.author} ({message.author.id})",
                inline=False
            )

            embed.add_field(
                name="Reason",
                value=spam_type,
                inline=False
            )

            embed.add_field(
                name="Action",
                value=action,
                inline=False
            )

            embed.add_field(
                name="Strike Count",
                value=str(strikes),
                inline=False
            )

            embed.add_field(
                name="Message Content",
                value=content[:1000],
                inline=False
            )

            if attachments:
                embed.add_field(
                    name="Attachment URLs",
                    value="\n".join(attachments),
                    inline=False
                )

            embed.add_field(
                name="Jump Link",
                value=jump,
                inline=False
            )

            await log.send(embed=embed)

    # =========================
    # MAIN MESSAGE EVENT
    # =========================

    @commands.Cog.listener()
    async def on_message(self, message):

        if message.author.bot:
            return

        if self.is_whitelisted(message.author):
            return

        now = discord.utils.utcnow()

        # =========================
        # SCAM TEXT DETECTION
        # =========================

        if message.content:

            normalized = normalize_text(message.content)

            for pattern in SCAM_PATTERNS:
                if re.search(pattern, normalized):
                    await self.punish_text_scam(
                        message,
                        "Scam Bio/Profile Detected"
                    )
                    return

            for keyword in SCAM_KEYWORDS:
                if keyword in normalized:
                    await self.punish_text_scam(
                        message,
                        "Scam Keyword Detected"
                    )
                    return

        # =========================
        # OFF-TOPIC ATTACHMENT LIMIT
        # =========================

        if (
            message.channel.id in ATTACHMENT_LIMIT_CHANNELS
            and message.attachments
        ):

            last_time = self.user_last_attachment_time.get(
                message.author.id
            )

            if (
                last_time
                and (now - last_time)
                < timedelta(minutes=ATTACHMENT_COOLDOWN_MINUTES)
            ):

                try:
                    await message.delete()
                except:
                    pass

                await message.channel.send(
                    f"{message.author.mention} No Spam Attachment.",
                    delete_after=5
                )

                return

            self.user_last_attachment_time[
                message.author.id
            ] = now

        # =========================
        # DUPLICATE DETECTION
        # =========================

        content_key = message.content.strip().lower()

        attachment_hashes = []

        if message.attachments:
            for att in message.attachments:
                h = await self.get_file_hash(att.url)
                attachment_hashes.append(h)

        key = (
            content_key
            if content_key
            else "|".join(attachment_hashes)
        )

        if key:
            self.user_message_history[
                message.author.id
            ].append({
                "key": key,
                "time": now,
                "channel": message.channel.id,
                "message_id": message.id
            })

        self.user_message_history[
            message.author.id
        ] = [
            e for e in self.user_message_history[
                message.author.id
            ]
            if now - e["time"]
            < timedelta(seconds=DUPLICATE_TIME_WINDOW)
        ]

        duplicates = [
            e for e in self.user_message_history[
                message.author.id
            ]
            if (
                e["key"] == key
                and e["channel"] == message.channel.id
            )
        ]

        if len(duplicates) >= DUPLICATE_THRESHOLD:
            await self.punish_duplicate(message, duplicates)
            return

        # =========================
        # CROSS CHANNEL DETECTION
        # =========================

        if message.attachments:

            for h in attachment_hashes:

                self.user_attachment_history[
                    message.author.id
                ].append({
                    "hash": h,
                    "channel": message.channel.id,
                    "time": now,
                    "message_id": message.id
                })

            self.user_attachment_history[
                message.author.id
            ] = [
                e for e in self.user_attachment_history[
                    message.author.id
                ]
                if now - e["time"]
                < timedelta(seconds=TIME_WINDOW_SECONDS)
            ]

            hashes = defaultdict(set)

            for entry in self.user_attachment_history[
                message.author.id
            ]:
                hashes[entry["hash"]].add(entry["channel"])

            for h, channels in hashes.items():

                if len(channels) >= MIN_CHANNEL_SPREAD:
                    await self.punish_cross(message, h)
                    return

    # =========================
    # TEXT SCAM
    # =========================

    async def punish_text_scam(self, message, reason):

        now = discord.utils.utcnow()

        try:
            await message.delete()
        except:
            pass

        uid = str(message.author.id)

        self.user_strikes.setdefault(uid, [])

        self.user_strikes[uid].append(now.isoformat())

        strikes = len(self.user_strikes[uid])

        self.save_json()

        if strikes >= MAX_STRIKES:

            await message.guild.ban(message.author)

            action = "BANNED"

        else:

            await message.author.timeout(
                timedelta(minutes=TIMEOUT_DURATION)
            )

            action = "TIMEOUT"

        await self.send_log(
            message,
            action,
            strikes,
            reason
        )

    # =========================
    # DUPLICATE SPAM
    # =========================

    async def punish_duplicate(self, message, duplicates):

        now = discord.utils.utcnow()

        user_id = message.author.id

        for entry in duplicates:

            channel = message.guild.get_channel(
                entry["channel"]
            )

            if channel:

                try:
                    msg = await channel.fetch_message(
                        entry["message_id"]
                    )

                    await msg.delete()

                except:
                    pass

        uid = str(user_id)

        self.user_strikes.setdefault(uid, [])

        self.user_strikes[uid].append(now.isoformat())

        strikes = len(self.user_strikes[uid])

        self.save_json()

        if strikes >= MAX_STRIKES:

            await message.guild.ban(message.author)

            action = "BANNED"

        else:

            await message.author.timeout(
                timedelta(minutes=TIMEOUT_DURATION)
            )

            action = "TIMEOUT"

        await self.send_log(
            message,
            action,
            strikes,
            "Duplicate Spam Detected"
        )

    # =========================
    # CROSS CHANNEL SPAM
    # =========================

    async def punish_cross(self, message, file_hash):

        now = discord.utils.utcnow()

        user_id = message.author.id

        related = [
            e for e in self.user_attachment_history[user_id]
            if e["hash"] == file_hash
        ]

        for entry in related:

            channel = message.guild.get_channel(
                entry["channel"]
            )

            if channel:

                try:
                    msg = await channel.fetch_message(
                        entry["message_id"]
                    )

                    await msg.delete()

                except:
                    pass

        uid = str(user_id)

        self.user_strikes.setdefault(uid, [])

        self.user_strikes[uid].append(now.isoformat())

        strikes = len(self.user_strikes[uid])

        self.save_json()

        if strikes >= MAX_STRIKES:

            await message.guild.ban(message.author)

            action = "BANNED"

        else:

            await message.author.timeout(
                timedelta(minutes=TIMEOUT_DURATION)
            )

            action = "TIMEOUT"

        await self.send_log(
            message,
            action,
            strikes,
            "Cross-Channel Spam Detected"
        )

    # =========================
    # MANUAL TIMEOUT LOG
    # =========================

    @commands.Cog.listener()
    async def on_member_update(self, before, after):

        before_timeout = before.timed_out_until
        after_timeout = after.timed_out_until

        if (
            before_timeout != after_timeout
            and after_timeout is not None
        ):

            # wait audit logs
            await asyncio.sleep(2)

            moderator = "Unknown"

            try:

                async for entry in after.guild.audit_logs(
                    limit=10,
                    action=discord.AuditLogAction.member_update
                ):

                    if entry.target.id != after.id:
                        continue

                    if hasattr(entry.after, "timed_out_until"):

                        moderator = (
                            f"{entry.user} "
                            f"({entry.user.id})"
                        )

                        break

            except:
                pass

            now = discord.utils.utcnow()

            duration_minutes = 0

            if after_timeout:

                remaining = after_timeout - now

                duration_minutes = max(
                    1,
                    int(remaining.total_seconds() // 60)
                )

            log = self.bot.get_channel(LOG_CHANNEL_ID)

            if log:

                embed = discord.Embed(
                    title="⏳ User Timed Out",
                    color=discord.Color.orange(),
                    timestamp=now
                )

                embed.add_field(
                    name="User",
                    value=f"{after} ({after.id})",
                    inline=False
                )

                embed.add_field(
                    name="Timed Out By",
                    value=moderator,
                    inline=False
                )

                embed.add_field(
                    name="Duration",
                    value=f"{duration_minutes} minute(s)",
                    inline=False
                )

                await log.send(embed=embed)

    # =========================
    # MANUAL BAN LOG
    # =========================

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):

        # wait audit logs
        await asyncio.sleep(2)

        moderator = "Unknown"

        try:

            async for entry in guild.audit_logs(
                limit=10,
                action=discord.AuditLogAction.ban
            ):

                if entry.target.id == user.id:

                    moderator = (
                        f"{entry.user} "
                        f"({entry.user.id})"
                    )

                    break

        except:
            pass

        log = self.bot.get_channel(LOG_CHANNEL_ID)

        if log:

            embed = discord.Embed(
                title="🔨 User Banned",
                color=discord.Color.dark_red(),
                timestamp=discord.utils.utcnow()
            )

            embed.add_field(
                name="User",
                value=f"{user} ({user.id})",
                inline=False
            )

            embed.add_field(
                name="Banned By",
                value=moderator,
                inline=False
            )

            await log.send(embed=embed)

    # =========================
    # VIEW STRIKES
    # =========================

    @commands.hybrid_command(name="view_strikes")
    async def view_strikes(
        self,
        ctx,
        member: discord.Member
    ):

        strikes = len(
            self.user_strikes.get(
                str(member.id),
                []
            )
        )

        await ctx.send(
            f"{member.mention} has {strikes} strike(s).",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(AntiSpam(bot))
