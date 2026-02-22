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
    def __init__(self, bot):
        self.bot = bot

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

    @commands.hybrid_command(name="accept")
    async def accept(self, ctx):
        await self.set_status(ctx, "ACCEPTED", lock=False)

    async def set_status(self, ctx, status_name, lock=None):

        thread = ctx.channel
        if not isinstance(thread, discord.Thread):
            await ctx.send("Use inside forum thread.")
            return

        forum = thread.parent
        status_tag = self.get_forum_tag(forum, TAG_IDS[status_name])

        user_tags, _ = self.split_tags(thread.applied_tags)

        kwargs = {"applied_tags": user_tags + [status_tag]}
        if lock is not None:
            kwargs["locked"] = lock

        await thread.edit(**kwargs)
        await ctx.send(f"Status set to {status_name}.")


async def setup(bot):
    await bot.add_cog(ForumFeedback(bot))
