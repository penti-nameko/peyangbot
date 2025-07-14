import discord
from discord.ext import commands
import os
import json
import sys
import subprocess
import motor.motor_asyncio # motorのインポートを追加

# ===== 許可するユーザーID =====
ALLOWED_USER_IDS = [
    1262439270488997991, 1012652131003682837, 1195288310189404251
]

# ===== コマンド制限デコレータ =====
def is_owner_user():
    async def predicate(ctx):
        return ctx.author.id in ALLOWED_USER_IDS
    return commands.check(predicate)

class MyBot(commands.Bot):
    def __init__(self):
        # Intentsを設定
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True

        # commands.Botのコンストラクタを呼び出し
        # デフォルトのヘルプコマンドを無効化 (help.pyで独自のヘルプがある場合)
        super().__init__(command_prefix="z!", intents=intents, help_command=None)

        self.async_db = None # MongoDBクライアント
        self.main_db = None  # 特定のデータベースインスタンス (例: "Main")

    # ボットがDiscordに接続する準備ができたときに呼び出される
    async def setup_hook(self):
        # ここでMongoDBに接続します
        try:
            # ご自身のMongoDB接続文字列に置き換えてください
            # 例: "mongodb://user:password@host:port/"
            # ここではローカルのデフォルトポートを使用
            self.async_db = motor.motor_asyncio.AsyncIOMotorClient("mongodb://localhost:27017/")
            # "Main" はデータベース名です。必要に応じて変更してください。
            self.main_db = self.async_db["Main"]
            print("MongoDBに接続しました！")
        except Exception as e:
            print(f"MongoDBへの接続に失敗しました: {e}")
            # エラー処理を強化することも検討してください（例：ボットを停止するなど）

        # cogsをロード
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"Loaded cog: {filename}")
                except Exception as e:
                    print(f"Failed to load cog {filename}: {e}")

        print('Cogsのロードが完了しました。')

    # ボットが完全に起動し、Discordにログインしたときに呼び出される
    @commands.Cog.listener() # setup_hook() は @bot.event ではなく、このクラス内で定義されるため @commands.Cog.listener() が適切
    async def on_ready(self):
        print(f"Bot is ready. Logged in as {self.user} (ID: {self.user.id})")

# ボットのインスタンスを作成
bot = MyBot()

# Cog管理コマンド群をボットに直接追加
@bot.command(name="load")
@is_owner_user()
async def load_cog(ctx, cog: str):
    try:
        await bot.load_extension(f"cogs.{cog}")
        await ctx.send(f"Successfully loaded {cog}!")
    except Exception as e:
        await ctx.send(f"Error while loading `{cog}`: `{e}`")

@bot.command(name="reload")
@is_owner_user()
async def reload_cog(ctx, cog: str):
    try:
        await bot.reload_extension(f"cogs.{cog}")
        await ctx.send(f"Successfully reloaded {cog}!")
    except Exception as e:
        await ctx.send(f"Error while reloading `{cog}`: `{e}`")

@bot.command(name="unload")
@is_owner_user()
async def unload_cog(ctx, cog: str):
    try:
        await bot.unload_extension(f"cogs.{cog}")
        await ctx.send(f"Successfully unloaded {cog}!")
    except Exception as e:
        await ctx.send(f"Error while unloading `{cog}`: `{e}`")

@bot.command(name="listcogs")
@is_owner_user()
async def list_cogs(ctx):
    loaded = list(bot.extensions.keys())
    if not loaded:
        await ctx.send("No Cogs are currently loaded.")
    else:
        cog_list = "\n".join(f"- {cog}" for cog in loaded)
        await ctx.send(f"Cogs currently loading:\n```\n{cog_list}\n```")

@bot.command(name="shutdown")
@is_owner_user()
async def shutdown_bot(ctx):
    await ctx.send("Shutting down...")
    await bot.close()

@bot.command(name="restart")
@is_owner_user()
async def restart_bot(ctx):
    await ctx.send("Restarting bot...")
    await bot.close()
    subprocess.Popen([sys.executable] + sys.argv)
    return

# ===== 権限エラー時のメッセージ =====
@load_cog.error
@reload_cog.error
@unload_cog.error
@list_cogs.error
async def cog_permission_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("⚠️You don't have permission to execute this command!")
    else:
        raise error

# ===== Bot起動 =====
# TOKENの読み込みはconfig.jsonから一箇所で行う
try:
    with open('config.json') as f:
        config = json.load(f)
        TOKEN = config.get("token") # .get() を使うとキーがない場合でもエラーにならない
        if not TOKEN:
            raise ValueError("Token not found in config.json")
except FileNotFoundError:
    print("エラー: config.jsonが見つかりません。")
    sys.exit(1) # プログラムを終了
except json.JSONDecodeError:
    print("エラー: config.jsonの形式が不正です。")
    sys.exit(1)
except ValueError as e:
    print(f"エラー: {e}")
    sys.exit(1)

bot.run(TOKEN)