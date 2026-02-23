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

ALLOWED_ROLE_IDS = [
    1427543936829882480,
    1464630512294564030
]

STRIKE_FILE = "strikes.json"


class AntiSpam(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.user_attachment_history = defaultdict(list)
        self.user_strikes = self.load_json()

    # =========================
    # PERMISSION CHECK
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

        now = discord.utils.utcnow()

        if message.attachments:

            for attachment in message.attachments:
                file_hash = await self.get_file_hash(attachment.url)

                self.user_attachment_history[message.author.id].append({
                    "hash": file_hash,
                    "channel": message.channel.id,
                    "time": now
                })

            # Remove old entries
            self.user_attachment_history[message.author.id] = [
                entry for entry in self.user_attachment_history[message.author.id]
                if now - entry["time"] < timedelta(seconds=TIME_WINDOW_SECONDS)
            ]

            hashes = defaultdict(set)

            for entry in self.user_attachment_history[message.author.id]:
                hashes[entry["hash"]].add(entry["channel"])

            for file_hash, channels in hashes.items():
                if len(channels) >= MIN_CHANNEL_SPREAD:
                    await self.punish_user(
                        message,
                        "Same attachment spammed across multiple channels"
                    )
                    return

        await self.bot.process_commands(message)

    # =========================
    # PUNISH + LOG
    # =========================

    async def punish_user(self, message: discord.Message, reason: str):

        now = discord.utils.utcnow()

        message_content = message.content or "No text"
        attachment_links = [att.url for att in message.attachments]
        jump_link = message.jump_url

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
            action_taken = "User BANNED"
        else:
            await message.author.timeout(
                timedelta(minutes=TIMEOUT_DURATION),
                reason="Spam detected"
            )
            action_taken = f"User timed out ({TIMEOUT_DURATION} minutes)"

        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)

        if log_channel:
            embed = discord.Embed(
                title="🚨 Cross-Channel Spam Detected",
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

            embed.add_field(
                name="Message Content",
                value=message_content[:1000],
                inline=False
            )

            if attachment_links:
                embed.add_field(
                    name="Attachment URLs",
                    value="\n".join(attachment_links),
                    inline=False
                )

            embed.add_field(
                name="Jump Link",
                value=jump_link,
                inline=False
            )

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
