from discord.ext import commands
import discord
import asyncio
import aiohttp
from discord import Webhook
import time

user_last_message_timegc = {}

class GlobalCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener("on_message")
    async def on_message_global(self, message: discord.Message):
        if message.author.bot:
            return
        if type(message.channel) == discord.DMChannel:
            return
        db = self.bot.async_db["Main"].GlobalChat
        try:
            dbfind = await db.find_one({"Channel": message.channel.id}, {"_id": False})
            if dbfind is None:
                return
        except Exception as e:
            return
        current_time = time.time()
        last_message_time = user_last_message_timegc.get(message.guild.id, 0)
        if current_time - last_message_time < 10:
            return
        user_last_message_timegc[message.guild.id] = current_time
        await self.send_global_chat(message)
        await message.add_reaction("✅")
        
    async def send_global_chat(self, message: discord.Message, ref_msg: discord.Message = None):
        db = self.bot.async_db["Main"].GlobalChat
        channels = db.find({})

        async for channel in channels:
            if channel["Channel"] == message.channel.id:
                continue
            target_channel = self.bot.get_channel(channel["Channel"])
            if target_channel:
                async with aiohttp.ClientSession() as session:
                    webhook_ = Webhook.from_url(channel.get("WebHook"), session=session)
                    await webhook_.send(username="PeyanguBot - Global", avatar_url=self.bot.user.avatar.url, embed=discord.Embed(description=message.content[:50], color=discord.Color.blue())
                                        .set_author(name=message.author.name, icon_url=message.author.avatar.url if message.author.avatar else message.author.default_avatar.url).set_footer(text=f"{message.guild.name} / {message.guild.id}"))
            else:
                print(f"{channel['Channel']} が見つからないため削除します。")
                await db.delete_one({"Channel": channel["Channel"]})
            await asyncio.sleep(1)
        
    @commands.hybrid_group(name="globalchat", fallback="join", description="グローバルチャットに参加します。")
    @commands.cooldown(2, 10, commands.BucketType.guild)
    async def globalchat_join(self, ctx: commands.Context):
        msg = await ctx.reply(embed=discord.Embed(title="グローバルチャットに参加しています・・", color=discord.Color.blue()))
        db = self.bot.database.GlobalChat
        web = await ctx.channel.create_webhook(name="Peyangu-Global")
        await db.replace_one(
            {"Guild": ctx.guild.id, "Channel": ctx.channel.id}, 
            {"Guild": ctx.guild.id, "Channel": ctx.channel.id, "WebHook": web.url}, 
            upsert=True
        )
        await asyncio.sleep(2)
        await msg.reply(embed=discord.Embed(title="グローバルチャットに参加しました。", color=discord.Color.green()))

    @globalchat_join.command(name="leave", description="グローバルチャットから退出します。")
    @commands.cooldown(2, 10, commands.BucketType.guild)
    async def admin_reload(self, ctx: commands.Context):
        msg = await ctx.reply(embed=discord.Embed(title="グローバルチャットから退出しています・・", color=discord.Color.blue()))
        db = self.bot.database.GlobalChat
        await db.delete_one(
            {"Guild": ctx.guild.id, "Channel": ctx.channel.id}
        )
        await asyncio.sleep(2)
        await msg.reply(embed=discord.Embed(title="グローバルチャットから退出しました。", color=discord.Color.green()))

async def setup(bot):
    await bot.add_cog(GlobalCog(bot))
