# cogs/global.py

import discord
from discord.ext import commands
import sqlite3
import json
from datetime import datetime, timezone
import asyncio
import aiohttp
from discord import Webhook
import time

# SQLiteデータベースファイル名 (main.pyと一致させる)
DATABASE_FILE = 'monebot_bot_data.db'

# グローバルチャットのクールダウン管理
user_last_message_timegc = {}

def get_db_connection():
    """データベース接続を取得するヘルパー関数 (main.pyと同じ)"""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row # カラム名をキーとしてアクセスできるようにする
    return conn

class GlobalChatCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._ensure_global_chat_table()

    def _ensure_global_chat_table(self):
        """グローバルチャット用のテーブルが存在することを確認"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS global_chat_settings (
                    guild_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    webhook_url TEXT NOT NULL, -- Webhook URLを追加
                    enabled INTEGER DEFAULT 1 -- 0=False, 1=True
                )
            ''')
            conn.commit()

    @commands.Cog.listener("on_message")
    async def on_message_global(self, message: discord.Message):
        if message.author.bot:
            return
        if isinstance(message.channel, discord.DMChannel): # type(message.channel) == discord.DMChannel の代わりに推奨
            return

        guild_id = str(message.guild.id)
        channel_id = str(message.channel.id)

        def _get_global_chat_settings_sync():
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT webhook_url, enabled FROM global_chat_settings WHERE guild_id = ? AND channel_id = ? AND enabled = 1",
                    (guild_id, channel_id)
                )
                row = cursor.fetchone()
                return row # rowがあればグローバルチャットチャンネルとして有効

        # このチャンネルがグローバルチャットとして設定されているか確認
        global_chat_settings = await self.bot.loop.run_in_executor(None, _get_global_chat_settings_sync)

        if global_chat_settings:
            current_time = time.time()
            last_message_time = user_last_message_timegc.get(message.guild.id, 0)
            if current_time - last_message_time < 10: # 10秒のクールダウン
                return
            user_last_message_timegc[message.guild.id] = current_time

            await self.send_global_chat(message)
            await message.add_reaction("✅")

    async def send_global_chat(self, message: discord.Message, ref_msg: discord.Message = None):
        def _get_all_global_chat_channels_sync():
            channels_to_send = []
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT guild_id, channel_id, webhook_url FROM global_chat_settings WHERE enabled = 1")
                for row in cursor.fetchall():
                    channels_to_send.append(dict(row)) # 辞書として取得
            return channels_to_send

        all_global_channels = await self.bot.loop.run_in_executor(None, _get_all_global_chat_channels_sync)

        # メッセージを埋め込み形式で送信
        # Discordの埋め込みの文字数制限に注意 (descriptionは2048文字)
        embed_description = message.content
        if len(embed_description) > 2048:
            embed_description = embed_description[:2045] + "..." # 制限を超えないように切り詰める

        embed = discord.Embed(
            description=embed_description,
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        # message.author.avatar.url が None の場合があるため、default_avatar.url をフォールバック
        author_avatar_url = message.author.avatar.url if message.author.avatar else message.author.default_avatar.url
        embed.set_author(name=f"{message.author.display_name} ({message.author.id})", icon_url=author_avatar_url)
        embed.set_footer(text=f"From {message.guild.name} (ID: {message.guild.id})")

        for channel_data in all_global_channels:
            target_guild_id = channel_data['guild_id']
            target_channel_id = channel_data['channel_id']
            webhook_url = channel_data['webhook_url']

            # 元のチャンネルには送信しない
            if target_guild_id == str(message.guild.id) and target_channel_id == str(message.channel.id):
                continue

            target_channel = self.bot.get_channel(int(target_channel_id))
            if target_channel:
                try:
                    async with aiohttp.ClientSession() as session:
                        webhook_ = Webhook.from_url(webhook_url, session=session)
                        await webhook_.send(
                            username=message.author.display_name, # 送信者の表示名を使用
                            avatar_url=author_avatar_url, # 送信者のアバターを使用
                            embed=embed
                        )
                except discord.NotFound: # Webhookが見つからない場合
                    print(f"Webhook for channel {target_channel_id} not found. Deleting from DB.")
                    def _delete_webhook_sync():
                        with get_db_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM global_chat_settings WHERE channel_id = ?", (target_channel_id,))
                            conn.commit()
                    await self.bot.loop.run_in_executor(None, _delete_webhook_sync)
                except discord.Forbidden:
                    print(f"Bot lacks permissions to send to webhook in channel {target_channel.name} in {target_channel.guild.name}")
                except Exception as e:
                    print(f"Error sending global chat message to {target_channel.name} in {target_channel.guild.name}: {e}")
            else:
                print(f"Channel {target_channel_id} not found. Deleting from DB.")
                def _delete_channel_sync():
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM global_chat_settings WHERE channel_id = ?", (target_channel_id,))
                        conn.commit()
                await self.bot.loop.run_in_executor(None, _delete_channel_sync)

            await asyncio.sleep(1) # 送信レート制限のため

    @commands.hybrid_group(name="globalchat", fallback="join", description="グローバルチャットに参加します。")
    @commands.cooldown(2, 10, commands.BucketType.guild)
    @commands.has_permissions(manage_webhooks=True) # Webhook作成権限が必要
    async def globalchat_join(self, ctx: commands.Context):
        msg = await ctx.reply(embed=discord.Embed(title="グローバルチャットに参加しています・・", color=discord.Color.blue()))
        
        guild_id = str(ctx.guild.id)
        channel_id = str(ctx.channel.id)

        # Webhookを作成
        try:
            web = await ctx.channel.create_webhook(name="MoneBot-GlobalChat")
            webhook_url = web.url
        except discord.Forbidden:
            await msg.edit(embed=discord.Embed(title="❌ Webhookを作成する権限がありません。", description="グローバルチャットに参加するには、ボットに`Webhookの管理`権限が必要です。", color=discord.Color.red()))
            return
        except Exception as e:
            await msg.edit(embed=discord.Embed(title="❌ Webhook作成中にエラーが発生しました", description=f"エラー: `{e}`", color=discord.Color.red()))
            return

        def _join_global_chat_sync():
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO global_chat_settings (guild_id, channel_id, webhook_url, enabled) VALUES (?, ?, ?, ?)",
                    (guild_id, channel_id, webhook_url, 1) # enabledを1 (True) に設定
                )
                conn.commit()
            return True

        try:
            await self.bot.loop.run_in_executor(None, _join_global_chat_sync)
            await asyncio.sleep(2)
            await msg.edit(embed=discord.Embed(title="✅ グローバルチャットに参加しました。", color=discord.Color.green()))
        except Exception as e:
            print(f"Error joining global chat for guild {guild_id}: {e}")
            await msg.edit(embed=discord.Embed(title="❌ グローバルチャットへの参加中にエラーが発生しました", description=f"エラー: `{e}`", color=discord.Color.red()))
            # エラーが発生した場合は作成したWebhookを削除する
            try:
                await web.delete()
            except Exception as delete_e:
                print(f"Error deleting webhook after failed join: {delete_e}")

    @globalchat_join.command(name="leave", description="グローバルチャットから退出します。")
    @commands.cooldown(2, 10, commands.BucketType.guild)
    @commands.has_permissions(manage_webhooks=True) # Webhook削除権限が必要
    async def globalchat_leave(self, ctx: commands.Context): # 関数名をglobalchat_leaveに変更
        msg = await ctx.reply(embed=discord.Embed(title="グローバルチャットから退出しています・・", color=discord.Color.blue()))
        
        guild_id = str(ctx.guild.id)
        channel_id = str(ctx.channel.id)

        # データベースからWebhook URLを取得
        def _get_webhook_url_sync():
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT webhook_url FROM global_chat_settings WHERE guild_id = ? AND channel_id = ?",
                    (guild_id, channel_id)
                )
                row = cursor.fetchone()
                return row['webhook_url'] if row else None

        webhook_url = await self.bot.loop.run_in_executor(None, _get_webhook_url_sync)

        # データベースから設定を削除
        def _delete_global_chat_sync():
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM global_chat_settings WHERE guild_id = ? AND channel_id = ?",
                    (guild_id, channel_id)
                )
                conn.commit()
            return cursor.rowcount > 0

        try:
            deleted = await self.bot.loop.run_in_executor(None, _delete_global_chat_sync)
            if not deleted:
                await msg.edit(embed=discord.Embed(title="ℹ️ このチャンネルはグローバルチャットに参加していません。", color=discord.Color.orange()))
                return

            # Webhookを削除
            if webhook_url:
                try:
                    async with aiohttp.ClientSession() as session:
                        webhook_ = Webhook.from_url(webhook_url, session=session)
                        await webhook_.delete()
                        print(f"Webhook for channel {channel_id} deleted.")
                except discord.NotFound:
                    print(f"Webhook for channel {channel_id} already deleted or not found.")
                except discord.Forbidden:
                    print(f"Bot lacks permissions to delete webhook for channel {channel_id}.")
                except Exception as e:
                    print(f"Error deleting webhook for channel {channel_id}: {e}")

            await asyncio.sleep(2)
            await msg.edit(embed=discord.Embed(title="✅ グローバルチャットから退出しました。", color=discord.Color.green()))
        except Exception as e:
            print(f"Error leaving global chat for guild {guild_id}: {e}")
            await msg.edit(embed=discord.Embed(title="❌ グローバルチャットからの退出中にエラーが発生しました", description=f"エラー: `{e}`", color=discord.Color.red()))

    @globalchat_join.error
    @globalchat_leave.error
    async def globalchat_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⚠️ このコマンドはクールダウン中です。あと`{error.retry_after:.1f}`秒待ってください。", ephemeral=True)
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("⚠️ このコマンドを実行するには`Webhookの管理`権限が必要です。", ephemeral=True)
        elif isinstance(error, commands.BadArgument):
            await ctx.send("⚠️ 無効な引数が指定されました。", ephemeral=True)
        else:
            print(f"Unhandled error in globalchat command: {error}")
            await ctx.send(f"❌ コマンドの実行中に予期せぬエラーが発生しました: `{error}`", ephemeral=True)


async def setup(bot):
    await bot.add_cog(GlobalChatCog(bot))
