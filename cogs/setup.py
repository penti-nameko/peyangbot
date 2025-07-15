# cogs/setup.py

import discord
from discord.ext import commands
import sqlite3
import json
import os

# SQLiteデータベースファイル名 (main.pyと一致させる)
DATABASE_FILE = 'monebot_bot_data.db'

def get_db_connection():
    """データベース接続を取得するヘルパー関数 (main.pyと同じ)"""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row # カラム名をキーとしてアクセスできるようにする
    return conn

class SetupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="setup")
    @commands.has_permissions(administrator=True) # 管理者権限を持つユーザーのみ実行可能
    async def setup_server(self, ctx):
        """
        このサーバーのMoneBot設定ファイルをデータベースに作成します。
        既に設定が存在する場合は、その旨を通知します。
        """
        guild_id = str(ctx.guild.id) # コマンドが実行されたギルドのID

        # データベース接続を非同期で実行するためにasyncio.to_threadを使用
        # 同期的なDB操作を別スレッドで実行
        def _setup_db_sync():
            with get_db_connection() as conn:
                cursor = conn.cursor()
                # 既存の設定があるか確認
                cursor.execute("SELECT guild_id FROM server_settings WHERE guild_id = ?", (guild_id,))
                existing_setting = cursor.fetchone()

                if existing_setting:
                    return False # 既に設定が存在する

                # デフォルト設定を挿入
                default_settings = {
                    "prefix": "z!", # ボットのデフォルトプレフィックス
                    "welcome_message": "",
                    "enable_fun_commands": 0, # SQLiteではBOOLEANはINTEGER (0=False, 1=True)
                    "mute_role_id": "",
                    "banned_words": json.dumps([]), # JSON文字列として保存
                    "enable_anti_spam": 0,
                    "log_channel_id": "",
                    "log_types": json.dumps([]) # JSON文字列として保存
                }

                cursor.execute('''
                    INSERT INTO server_settings (
                        guild_id, prefix, welcome_message, enable_fun_commands,
                        mute_role_id, banned_words, enable_anti_spam,
                        log_channel_id, log_types
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    guild_id,
                    default_settings["prefix"],
                    default_settings["welcome_message"],
                    default_settings["enable_fun_commands"],
                    default_settings["mute_role_id"],
                    default_settings["banned_words"],
                    default_settings["enable_anti_spam"],
                    default_settings["log_channel_id"],
                    default_settings["log_types"]
                ))
                conn.commit()
                return True # 新しい設定が作成された

        try:
            # 同期DB操作を非同期で実行
            settings_created = await self.bot.loop.run_in_executor(None, _setup_db_sync)

            if settings_created:
                await ctx.send(
                    f"✅ このサーバーのMoneBot設定が初期化されました！\n"
                    f"ウェブコンソール (`{os.getenv('WEB_CONSOLE_URL', 'ウェブコンソールURL')}/dashboard`) から設定をカスタマイズできます。"
                )
            else:
                await ctx.send("ℹ️ このサーバーのMoneBot設定は既に存在します。")
        except Exception as e:
            print(f"Error during setup command for guild {guild_id}: {e}")
            await ctx.send(f"❌ 設定の初期化中にエラーが発生しました: `{e}`")

    @setup_server.error
    async def setup_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("⚠️ このコマンドを実行するには管理者権限が必要です。")
        else:
            # その他の予期せぬエラーをログに記録し、ユーザーに通知
            print(f"Unhandled error in setup command: {error}")
            await ctx.send(f"❌ コマンドの実行中に予期せぬエラーが発生しました: `{error}`")

async def setup(bot):
    """Cogをロードするためのセットアップ関数"""
    await bot.add_cog(SetupCog(bot))
