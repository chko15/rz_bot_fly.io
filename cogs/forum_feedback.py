import discord
from discord.ext import commands
import asyncio

TAG_IDS = {
    "NEW": 1465992548496441507,
    "UNDER_REVIEW": 1465992598492545039,
    "IN_PROGRESS": 1465992741057200303,
    "ACCEPTED": 1465992644055273677,
    "REJECTED": 1465992682407985283,
    "IMPLEMENTED": 1465992779376234722,
}

STATUS_TAG_IDS = set(TAG_IDS.values())


class ForumFeedback(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # =========================
    # HELPERS
    # =========================

    def get_forum_tag(self, forum: discord.ForumChannel, tag_id: int):
        for tag in forum.available_tags:
            if tag.id == tag_id:
                return tag
        return None

    def split_tags(self, tags):
        user_tags = []
        status_tags = []

        for tag in tags:
            if tag.id in STATUS_TAG_IDS:
                status_tags.append(tag)
            else:
                user_tags.append(tag)

        return user_tags, status_tags

    # =========================
    # AUTO NEW TAG
    # =========================

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        if not isinstance(thread.parent, discord.ForumChannel):
            return

        forum = thread.parent
        new_tag = self.get_forum_tag(forum, TAG_IDS["NEW"])
        if not new_tag:
            return

        await asyncio.sleep(1.5)

        user_tags, status_tags = self.split_tags(thread.applied_tags)

        if not status_tags:
            await thread.edit(applied_tags=user_tags + [new_tag])

    # =========================
    # STATUS SETTER
    # =========================

    async def set_status(
        self,
        interaction: discord.Interaction,
        status_name: str,
        lock: bool | None = None
    ):
        await interaction.response.defer(ephemeral=True)

        thread = interaction.channel

        if not isinstance(thread, discord.Thread):
            await interaction.followup.send(
                "Use this command inside a forum thread.",
                ephemeral=True
            )
            return

        forum = thread.parent
        if not isinstance(forum, discord.ForumChannel):
            return

        perms = thread.permissions_for(thread.guild.me)
        if not perms.manage_threads:
            await interaction.followup.send(
                "Bot does not have permission to manage threads.",
                ephemeral=True
            )
            return

        status_tag = self.get_forum_tag(forum, TAG_IDS[status_name])
        if not status_tag:
            await interaction.followup.send(
                f"{status_name} tag not found.",
                ephemeral=True
            )
            return

        user_tags, _ = self.split_tags(thread.applied_tags)

        kwargs = {"applied_tags": user_tags + [status_tag]}
        if lock is not None:
            kwargs["locked"] = lock

        await thread.edit(**kwargs)

        await interaction.followup.send(
            f"Status set to **{status_name.replace('_', ' ').title()}**.",
            ephemeral=True
        )

    # =========================
    # SLASH COMMANDS
    # =========================

    @discord.app_commands.command(name="accept", description="Accept this post")
    async def accept(self, interaction: discord.Interaction):
        await self.set_status(interaction, "ACCEPTED", lock=False)

    @discord.app_commands.command(name="reject", description="Reject this post")
    async def reject(self, interaction: discord.Interaction):
        await self.set_status(interaction, "REJECTED", lock=True)

    @discord.app_commands.command(name="review", description="Set status to Under Review")
    async def review(self, interaction: discord.Interaction):
        await self.set_status(interaction, "UNDER_REVIEW")

    @discord.app_commands.command(name="progress", description="Set status to In Progress")
    async def progress(self, interaction: discord.Interaction):
        await self.set_status(interaction, "IN_PROGRESS")

    @discord.app_commands.command(name="implemented", description="Set status to Implemented")
    async def implemented(self, interaction: discord.Interaction):
        await self.set_status(interaction, "IMPLEMENTED", lock=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ForumFeedback(bot))
