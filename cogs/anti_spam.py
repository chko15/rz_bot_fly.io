import discord
from discord.ext import commands
from datetime import timedelta
from collections import defaultdict
import json
import os
import hashlib
import aiohttp

# =========================
# CONFIG
# =========================

LOG_CHANNEL_ID = 1466507799361229003

TIME_WINDOW_SECONDS = 30
MIN_CHANNEL_SPREAD = 2        # cross-channel detection
MIN_SAME_CHANNEL_REPEAT = 2   # same-channel detection
TIMEOUT_DURATION = 10
STRIKE_RESET_TIME = 60
MAX_STRIKES = 2

WHITELIST_ROLE_IDS = [
    1427543936829882480,
    1464630512294564030,
    1427554165235646496
]

ALLOWED_ROLE_IDS = [
    1427543936829882480,
    1464630512294564030
]

STRIKE_FILE = "strikes.json"


# =========================
# COG
# =========================

class AntiSpam(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.user_attachment_history = defaultdict(list)
        self.user_strikes = self.load_json()

    # =========================
    # PERMISSION SYSTEM
    # =========================

    def has_permission(self, member: discord.Member) -> bool:
        return any(role.id in ALLOWED_ROLE_IDS for role in member.roles)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            return False

        if not self.has_permission(interaction.user):
            await interaction.response.send_message(
                "You do not have permission to use this command.",
                ephemeral=True
            )
            return False

        return True

    # =========================
    # JSON STORAGE
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

    def is_whitelisted(self, member: discord.Member):
        return any(role.id in WHITELIST_ROLE_IDS for role in member.roles)

    # =========================
    # HASH FILE
    # =========================

    async def get_file_hash(self, url):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.read()
                return hashlib.sha256(data).hexdigest()

    # =========================
    # MESSAGE LISTENER
    # =========================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):

        if message.author.bot:
            return

        if not isinstance(message.author, discord.Member):
            return

        if self.is_whitelisted(message.author):
            return

        if not message.attachments:
            await self.bot.process_commands(message)
            return

        now = discord.utils.utcnow()

        for attachment in message.attachments:
            file_hash = await self.get_file_hash(attachment.url)

            self.user_attachment_history[message.author.id].append({
                "hash": file_hash,
                "channel": message.channel.id,
                "message_id": message.id,
                "time": now
            })

        # Remove expired entries
        self.user_attachment_history[message.author.id] = [
            entry for entry in self.user_attachment_history[message.author.id]
            if now - entry["time"] < timedelta(seconds=TIME_WINDOW_SECONDS)
        ]

        await self.check_spam(message)

        await self.bot.process_commands(message)

    # =========================
    # SPAM CHECK LOGIC
    # =========================

    async def check_spam(self, message: discord.Message):

        user_id = message.author.id
        entries = self.user_attachment_history[user_id]

        hash_channels = defaultdict(set)
        hash_counts = defaultdict(int)

        for entry in entries:
            hash_channels[entry["hash"]].add(entry["channel"])
            hash_counts[entry["hash"]] += 1

        for file_hash in hash_channels:

            # Cross-channel detection
            if len(hash_channels[file_hash]) >= MIN_CHANNEL_SPREAD:
                await self.punish_user(message, file_hash,
                    "Same attachment spammed across multiple channels")
                return

            # Same-channel repeat detection
            if hash_counts[file_hash] >= MIN_SAME_CHANNEL_REPEAT:
                await self.punish_user(message, file_hash,
                    "Same attachment spammed repeatedly in one channel")
                return

    # =========================
    # PUNISH + DELETE ALL COPIES
    # =========================

    async def punish_user(self, message: discord.Message, file_hash: str, reason: str):

        now = discord.utils.utcnow()
        user_id = message.author.id

        related_entries = [
            entry for entry in self.user_attachment_history[user_id]
            if entry["hash"] == file_hash
        ]

        # Delete ALL related spam messages
        for entry in related_entries:
            channel = message.guild.get_channel(entry["channel"])
            if channel:
                try:
                    msg = await channel.fetch_message(entry["message_id"])
                    await msg.delete()
                except Exception as e:
                    print("Failed deleting message:", e)

        # Clear history for that hash
        self.user_attachment_history[user_id] = [
            entry for entry in self.user_attachment_history[user_id]
            if entry["hash"] != file_hash
        ]

        # Strike system
        user_key = str(user_id)

        if user_key not in self.user_strikes:
            self.user_strikes[user_key] = []

        self.user_strikes[user_key] = [
            t for t in self.user_strikes[user_key]
            if (now - discord.utils.parse_time(t)) < timedelta(minutes=STRIKE_RESET_TIME)
        ]

        self.user_strikes[user_key].append(now.isoformat())
        strike_count = len(self.user_strikes[user_key])

        self.save_json()

        # Punishment
        if strike_count >= MAX_STRIKES:
            await message.guild.ban(message.author, reason="Repeated spam")
            action_taken = "User BANNED"
        else:
            await message.author.timeout(
                timedelta(minutes=TIMEOUT_DURATION),
                reason="Spam detected"
            )
            action_taken = f"User timed out ({TIMEOUT_DURATION} minutes)"

        # Logging
        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)

        if log_channel:

            embed = discord.Embed(
                title="🚨 Spam Detected",
                color=discord.Color.red(),
                timestamp=now
            )

            embed.add_field(
                name="User",
                value=f"{message.author} ({message.author.id})",
                inline=False
            )

            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Action", value=action_taken, inline=False)
            embed.add_field(name="Strike Count", value=str(strike_count), inline=False)

            await log_channel.send(embed=embed)

    # =========================
    # SLASH COMMAND
    # =========================

    @discord.app_commands.command(
        name="view_strikes",
        description="View strike count of a user"
    )
    async def view_strikes(
        self,
        interaction: discord.Interaction,
        member: discord.Member
    ):
        await interaction.response.defer(ephemeral=True)

        strikes = len(self.user_strikes.get(str(member.id), []))

        await interaction.followup.send(
            f"{member.mention} has **{strikes} strike(s)**.",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiSpam(bot))
