# main.py (Discord Bot with SQLite and API)
import os
import json
import sys
import subprocess
import asyncio
import threading
import sqlite3 # SQLiteをインポート
from datetime import datetime, timezone # datetimeとtimezoneをインポート
from flask import Flask, request, jsonify # Flaskをインポート
import discord # ここに import discord を追加
from discord.ext import commands
# import motor.motor_asyncio # MongoDBは使用しないため削除

# .envファイルを読み込む
from dotenv import load_dotenv
load_dotenv()

# Discordボットのトークンを環境変数から取得
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
# APIサーバーがリッスンするポート
API_PORT = int(os.getenv('BOT_API_PORT', 5001)) # ウェブコンソールとは別のポート

# --- SQLiteデータベース設定 ---
DATABASE_FILE = 'monebot_bot_data.db' # ボット用のデータベースファイル名

def get_db_connection():
    """データベース接続を取得するヘルパー関数"""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row # カラム名をキーとしてアクセスできるようにする
    return conn

def init_db_bot():
    """ボット側のデータベーステーブルを初期化する"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # サーバー設定テーブル (ウェブコンソールと共通のスキーマ)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS server_settings (
                guild_id TEXT PRIMARY KEY,
                prefix TEXT,
                welcome_message TEXT,
                enable_fun_commands INTEGER,
                mute_role_id TEXT,
                banned_words TEXT, -- JSON文字列として保存
                enable_anti_spam INTEGER,
                log_channel_id TEXT,
                log_types TEXT -- JSON文字列として保存
            )
        ''')
        # ボット参加ギルドテーブル (ウェブコンソールと共通のスキーマ)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_joined_guilds (
                guild_id TEXT PRIMARY KEY,
                joined INTEGER,
                timestamp TEXT -- ISOフォーマットの文字列として保存
            )
        ''')
        conn.commit()
    print(f"SQLite database initialized for bot: {DATABASE_FILE}")

# Flask APIサーバーのセットアップ
api_app = Flask(__name__)

# ===== 許可するユーザーID (ボットのコマンド用) =====
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
        intents.members = True # on_member_joinのために必要

        # commands.Botのコンストラクタを呼び出し
        super().__init__(command_prefix="z!", intents=intents, help_command=None)

        # self.async_db = None # MongoDBは使用しないため削除
        # self.main_db = None  # MongoDBは使用しないため削除

    # ボットがDiscordに接続する準備ができたときに呼び出される
    async def setup_hook(self):
        # ここでSQLiteデータベースを初期化します
        init_db_bot()
        print("Bot setup_hook completed.")

        # cogsをロード
        if os.path.exists('./cogs') and os.path.isdir('./cogs'):
            for filename in os.listdir('./cogs'):
                if filename.endswith('.py'):
                    try:
                        await self.load_extension(f'cogs.{filename[:-3]}')
                        print(f"Loaded cog: {filename}")
                    except Exception as e:
                        print(f"Failed to load cog {filename}: {e}")
        else:
            print("Cogsディレクトリが見つかりません。")

        print('Cogsのロードが完了しました。')

    # ボットが完全に起動し、Discordにログインしたときに呼び出される
    @commands.Cog.listener()
    async def on_ready(self):
        print(f"Bot is ready. Logged in as {self.user} (ID: {self.user.id})")
        print("Syncing current guilds with SQLite...")
        await self.sync_guilds_with_db()
        print("Guild sync complete.")

    async def sync_guilds_with_db(self):
        """ボットが現在参加しているギルドをSQLiteと同期する"""
        current_guild_ids = {str(guild.id) for guild in self.guilds}
        
        db_guild_ids = set()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT guild_id FROM bot_joined_guilds")
            for row in cursor.fetchall():
                db_guild_ids.add(row['guild_id'])

            # SQLiteに存在しないがボットが参加しているギルドを追加
            for guild_id in current_guild_ids:
                if guild_id not in db_guild_ids:
                    cursor.execute(
                        "INSERT OR REPLACE INTO bot_joined_guilds (guild_id, joined, timestamp) VALUES (?, ?, ?)",
                        (guild_id, 1, datetime.now(timezone.utc).isoformat())
                    )
                    print(f"SQLite: Bot joined guild {guild_id} (set to true).")

            # SQLiteには存在するがボットが参加していないギルドを削除
            for guild_id in db_guild_ids:
                if guild_id not in current_guild_ids:
                    cursor.execute("DELETE FROM bot_joined_guilds WHERE guild_id = ?", (guild_id,))
                    print(f"SQLite: Bot left guild {guild_id} (deleted).")
            conn.commit()


    # --- ギルド参加/退出イベントリスナー ---
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        print(f"Joined a new guild: {guild.name} (ID: {guild.id})")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO bot_joined_guilds (guild_id, joined, timestamp) VALUES (?, ?, ?)",
                (str(guild.id), 1, datetime.now(timezone.utc).isoformat())
            )
            conn.commit()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        print(f"Left a guild: {guild.name} (ID: {guild.id})")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM bot_joined_guilds WHERE guild_id = ?", (str(guild.id),))
            conn.commit()

    # --- メンバー参加イベントリスナー (ウェルカムメッセージ) ---
    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.bot:
            return

        guild = member.guild
        print(f"Member {member.name} joined guild {guild.name} (ID: {guild.id})")

        # SQLiteからこのギルドのサーバー設定を取得
        settings = {}
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM server_settings WHERE guild_id = ?", (str(guild.id),))
            row = cursor.fetchone()
            if row:
                settings = dict(row)
                # JSON文字列として保存されたフィールドをデコード
                if settings.get('banned_words'):
                    settings['banned_words'] = json.loads(settings['banned_words'])
                else:
                    settings['banned_words'] = []
                if settings.get('log_types'):
                    settings['log_types'] = json.loads(settings['log_types'])
                else:
                    settings['log_types'] = []
                # INTEGERとして保存されたBOOLEAN値をPythonのboolに変換
                settings['enable_fun_commands'] = bool(settings.get('enable_fun_commands', 0))
                settings['enable_anti_spam'] = bool(settings.get('enable_anti_spam', 0))
            else:
                print(f"No settings found in SQLite for guild {guild.id}. Using default settings for welcome message.")
                settings = {
                    "prefix": "!",
                    "welcome_message": "",
                    "enable_fun_commands": False,
                    "mute_role_id": "",
                    "banned_words": [],
                    "enable_anti_spam": False,
                    "log_channel_id": "",
                    "log_types": []
                }
        
        welcome_message_template = settings.get('welcome_message')
        log_channel_id = settings.get('log_channel_id')

        if welcome_message_template:
            message_to_send = welcome_message_template.replace('{user}', member.mention).replace('{guild}', guild.name)
            
            if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
                try:
                    await guild.system_channel.send(message_to_send)
                    print(f"Sent welcome message to {guild.system_channel.name} in {guild.name}.")
                except discord.Forbidden:
                    print(f"Bot does not have permission to send messages to system channel in {guild.name}.")
                except Exception as e:
                    print(f"Error sending welcome message to system channel in {guild.name}: {e}")
            elif log_channel_id:
                log_channel = guild.get_channel(int(log_channel_id))
                if log_channel and isinstance(log_channel, discord.TextChannel) and log_channel.permissions_for(guild.me).send_messages:
                    try:
                        await log_channel.send(message_to_send)
                        print(f"Sent welcome message to log channel {log_channel.name} in {guild.name}.")
                    except discord.Forbidden:
                        print(f"Bot does not have permission to send messages to log channel in {guild.name}.")
                    except Exception as e:
                        print(f"Error sending welcome message to log channel in {guild.name}: {e}")
                else:
                    print(f"Log channel {log_channel_id} not found or bot lacks permissions in {guild.name}.")
            else:
                print(f"No suitable channel found to send welcome message in {guild.name}.")
        else:
            print(f"No welcome message configured for guild {guild.name}.")


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

# --- Flask APIエンドポイント (ボット内で実行) ---
# 注意: Flaskルートはasyncioのイベントループとは異なるスレッドで実行されるため、
# Discord.pyのasync/await関数を直接呼び出す場合は注意が必要です。
# ここでは、asyncio.to_thread を使用して安全に呼び出します。

@api_app.route('/api/bot/joined_guilds', methods=['GET'])
async def get_bot_joined_guilds_api():
    """ボットが参加しているギルドのIDリストを返すAPI"""
    def _get_joined_guilds_sync():
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT guild_id FROM bot_joined_guilds WHERE joined = 1")
            return [row['guild_id'] for row in cursor.fetchall()]
    
    try:
        guild_ids = await asyncio.to_thread(_get_joined_guilds_sync)
        return jsonify(guild_ids), 200
    except Exception as e:
        print(f"Error fetching joined guilds from SQLite: {e}")
        return jsonify({"message": "Failed to fetch joined guilds"}), 500

@api_app.route('/api/bot/server_settings/<guild_id>', methods=['GET'])
async def get_server_settings_api(guild_id):
    """指定されたギルドのサーバー設定を返すAPI"""
    def _get_server_settings_sync():
        settings = {}
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM server_settings WHERE guild_id = ?", (guild_id,))
            row = cursor.fetchone()
            if row:
                settings = dict(row)
                # JSON文字列として保存されたフィールドをデコード
                if settings.get('banned_words'):
                    settings['banned_words'] = json.loads(settings['banned_words'])
                else:
                    settings['banned_words'] = [] # Noneの場合は空リスト
                if settings.get('log_types'):
                    settings['log_types'] = json.loads(settings['log_types'])
                else:
                    settings['log_types'] = [] # Noneの場合は空リスト
                # INTEGERとして保存されたBOOLEAN値をPythonのboolに変換
                settings['enable_fun_commands'] = bool(settings.get('enable_fun_commands', 0))
                settings['enable_anti_spam'] = bool(settings.get('enable_anti_spam', 0))
            else:
                print(f"No settings found in DB for guild {guild_id}. Returning default.")
                # デフォルト設定
                settings = {
                    "prefix": "!",
                    "welcome_message": "",
                    "enable_fun_commands": False,
                    "mute_role_id": "",
                    "banned_words": [],
                    "enable_anti_spam": False,
                    "log_channel_id": "",
                    "log_types": []
                }
        return settings

    try:
        settings = await asyncio.to_thread(_get_server_settings_sync)
        return jsonify(settings), 200
    except Exception as e:
        print(f"Error fetching server settings from SQLite for {guild_id}: {e}")
        return jsonify({"message": "Failed to fetch server settings"}), 500

@api_app.route('/api/bot/server_settings/<guild_id>', methods=['POST'])
async def update_server_settings_api(guild_id):
    """指定されたギルドのサーバー設定を更新するAPI"""
    def _update_server_settings_sync(data):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 既存の設定を読み込み、新しいデータで更新
            # まず既存のデータを取得し、存在しない場合はデフォルトで初期化
            cursor.execute("SELECT * FROM server_settings WHERE guild_id = ?", (guild_id,))
            existing_row = cursor.fetchone()
            if existing_row:
                existing_settings = dict(existing_row)
                # JSON文字列をデコード
                if existing_settings.get('banned_words'):
                    existing_settings['banned_words'] = json.loads(existing_settings['banned_words'])
                else:
                    existing_settings['banned_words'] = []
                if existing_settings.get('log_types'):
                    existing_settings['log_types'] = json.loads(existing_settings['log_types'])
                else:
                    existing_settings['log_types'] = []
                existing_settings['enable_fun_commands'] = bool(existing_settings.get('enable_fun_commands', 0))
                existing_settings['enable_anti_spam'] = bool(existing_settings.get('enable_anti_spam', 0))
            else:
                existing_settings = {
                    "prefix": "!",
                    "welcome_message": "",
                    "enable_fun_commands": False,
                    "mute_role_id": "",
                    "banned_words": [],
                    "enable_anti_spam": False,
                    "log_channel_id": "",
                    "log_types": []
                }

            # 受け取ったデータで既存の設定を上書き
            for key, value in data.items():
                if key in ['enable_fun_commands', 'enable_anti_spam']:
                    existing_settings[key] = bool(value) # boolで受け取ってboolで保存
                elif key in ['banned_words', 'log_types']:
                    existing_settings[key] = value # リストとして受け取ってそのまま保存（後でdumps）
                else:
                    existing_settings[key] = value

            # 保存前にJSON文字列にエンコード
            banned_words_json = json.dumps(existing_settings.get('banned_words', []))
            log_types_json = json.dumps(existing_settings.get('log_types', []))
            
            # ブール値はINTEGERに変換
            enable_fun_commands_int = int(existing_settings.get('enable_fun_commands', False))
            enable_anti_spam_int = int(existing_settings.get('enable_anti_spam', False))

            # INSERT OR REPLACE を使用して、存在すれば更新、なければ挿入
            cursor.execute('''
                INSERT OR REPLACE INTO server_settings (
                    guild_id, prefix, welcome_message, enable_fun_commands, 
                    mute_role_id, banned_words, enable_anti_spam, 
                    log_channel_id, log_types
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                guild_id,
                existing_settings.get('prefix'),
                existing_settings.get('welcome_message'),
                enable_fun_commands_int,
                existing_settings.get('mute_role_id'),
                banned_words_json,
                enable_anti_spam_int,
                existing_settings.get('log_channel_id'),
                log_types_json
            ))
            conn.commit()
        return {"message": "Settings updated successfully", "status": "success"}

    try:
        data = request.get_json()
        print(f"API: Received update for guild {guild_id}: {data}")
        result = await asyncio.to_thread(_update_server_settings_sync, data)
        return jsonify(result), 200
    except Exception as e:
        print(f"Error updating server settings in SQLite for {guild_id}: {e}")
        return jsonify({"message": "Failed to update settings", "status": "error"}), 500

# Flask APIサーバーを別スレッドで実行する関数
def run_api_server():
    # Flaskのデバッグモードは本番ではFalseに
    api_app.run(host='0.0.0.0', port=API_PORT, debug=False)

# ===== Bot起動 =====
if __name__ == '__main__':
    if not DISCORD_BOT_TOKEN:
        print("Error: DISCORD_BOT_TOKEN environment variable not set.")
        sys.exit(1)

    # Flask APIサーバーを別スレッドで開始
    api_thread = threading.Thread(target=run_api_server)
    api_thread.daemon = True # メインスレッド終了時に一緒に終了
    api_thread.start()
    print(f"Flask API server started on port {API_PORT} in a separate thread.")

    # Discordボットを実行
    try:
        bot.run(DISCORD_BOT_TOKEN)
    except discord.LoginFailure:
        print("Error: Invalid Discord bot token. Please check DISCORD_BOT_TOKEN in your .env file.")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred during bot execution: {e}")
        sys.exit(1)

```

はい、ご提示いただいた`main.py`の実行結果と`NameError: name 'discord' is not defined`のエラーについて承知いたしました。

このエラーは、`main.py`が実行される際に`discord`という名前が定義されていない、つまり`discord.py`ライブラリがPython環境に正しくインポートされていないために発生しています。これは通常、ライブラリがその環境にインストールされていない場合に起こります。

Canvasの`main.py (SQLiteボット with API - DeprecationWarning修正)`ドキュメントを見ると、`discord.ext import commands`という行がありますが、その前に`import discord`がありません。

### `main.py` の修正

`main.py`の先頭に `import discord` を追加することで、`discord`モジュールが利用可能になり、エラーが解消されます。


```python
# main.py (Discord Bot with SQLite and API)
import os
import json
import sys
import subprocess
import asyncio
import threading
import sqlite3 # SQLiteをインポート
from datetime import datetime, timezone # datetimeとtimezoneをインポート
from flask import Flask, request, jsonify # Flaskをインポート
import discord # ここに import discord を追加
from discord.ext import commands
# import motor.motor_asyncio # MongoDBは使用しないため削除

# .envファイルを読み込む
from dotenv import load_dotenv
load_dotenv()

# Discordボットのトークンを環境変数から取得
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
# APIサーバーがリッスンするポート
API_PORT = int(os.getenv('BOT_API_PORT', 5001)) # ウェブコンソールとは別のポート

# --- SQLiteデータベース設定 ---
DATABASE_FILE = 'monebot_bot_data.db' # ボット用のデータベースファイル名

def get_db_connection():
    """データベース接続を取得するヘルパー関数"""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row # カラム名をキーとしてアクセスできるようにする
    return conn

def init_db_bot():
    """ボット側のデータベーステーブルを初期化する"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # サーバー設定テーブル (ウェブコンソールと共通のスキーマ)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS server_settings (
                guild_id TEXT PRIMARY KEY,
                prefix TEXT,
                welcome_message TEXT,
                enable_fun_commands INTEGER,
                mute_role_id TEXT,
                banned_words TEXT, -- JSON文字列として保存
                enable_anti_spam INTEGER,
                log_channel_id TEXT,
                log_types TEXT -- JSON文字列として保存
            )
        ''')
        # ボット参加ギルドテーブル (ウェブコンソールと共通のスキーマ)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_joined_guilds (
                guild_id TEXT PRIMARY KEY,
                joined INTEGER,
                timestamp TEXT -- ISOフォーマットの文字列として保存
            )
        ''')
        conn.commit()
    print(f"SQLite database initialized for bot: {DATABASE_FILE}")

# Flask APIサーバーのセットアップ
api_app = Flask(__name__)

# ===== 許可するユーザーID (ボットのコマンド用) =====
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
        intents.members = True # on_member_joinのために必要

        # commands.Botのコンストラクタを呼び出し
        super().__init__(command_prefix="z!", intents=intents, help_command=None)

        # self.async_db = None # MongoDBは使用しないため削除
        # self.main_db = None  # MongoDBは使用しないため削除

    # ボットがDiscordに接続する準備ができたときに呼び出される
    async def setup_hook(self):
        # ここでSQLiteデータベースを初期化します
        init_db_bot()
        print("Bot setup_hook completed.")

        # cogsをロード
        if os.path.exists('./cogs') and os.path.isdir('./cogs'):
            for filename in os.listdir('./cogs'):
                if filename.endswith('.py'):
                    try:
                        await self.load_extension(f'cogs.{filename[:-3]}')
                        print(f"Loaded cog: {filename}")
                    except Exception as e:
                        print(f"Failed to load cog {filename}: {e}")
        else:
            print("Cogsディレクトリが見つかりません。")

        print('Cogsのロードが完了しました。')

    # ボットが完全に起動し、Discordにログインしたときに呼び出される
    @commands.Cog.listener()
    async def on_ready(self):
        print(f"Bot is ready. Logged in as {self.user} (ID: {self.user.id})")
        print("Syncing current guilds with SQLite...")
        await self.sync_guilds_with_db()
        print("Guild sync complete.")

    async def sync_guilds_with_db(self):
        """ボットが現在参加しているギルドをSQLiteと同期する"""
        current_guild_ids = {str(guild.id) for guild in self.guilds}
        
        db_guild_ids = set()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT guild_id FROM bot_joined_guilds")
            for row in cursor.fetchall():
                db_guild_ids.add(row['guild_id'])

            # SQLiteに存在しないがボットが参加しているギルドを追加
            for guild_id in current_guild_ids:
                if guild_id not in db_guild_ids:
                    cursor.execute(
                        "INSERT OR REPLACE INTO bot_joined_guilds (guild_id, joined, timestamp) VALUES (?, ?, ?)",
                        (guild_id, 1, datetime.now(timezone.utc).isoformat())
                    )
                    print(f"SQLite: Bot joined guild {guild_id} (set to true).")

            # SQLiteには存在するがボットが参加していないギルドを削除
            for guild_id in db_guild_ids:
                if guild_id not in current_guild_ids:
                    cursor.execute("DELETE FROM bot_joined_guilds WHERE guild_id = ?", (guild_id,))
                    print(f"SQLite: Bot left guild {guild_id} (deleted).")
            conn.commit()


    # --- ギルド参加/退出イベントリスナー ---
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        print(f"Joined a new guild: {guild.name} (ID: {guild.id})")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO bot_joined_guilds (guild_id, joined, timestamp) VALUES (?, ?, ?)",
                (str(guild.id), 1, datetime.now(timezone.utc).isoformat())
            )
            conn.commit()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        print(f"Left a guild: {guild.name} (ID: {guild.id})")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM bot_joined_guilds WHERE guild_id = ?", (str(guild.id),))
            conn.commit()

    # --- メンバー参加イベントリスナー (ウェルカムメッセージ) ---
    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.bot:
            return

        guild = member.guild
        print(f"Member {member.name} joined guild {guild.name} (ID: {guild.id})")

        # SQLiteからこのギルドのサーバー設定を取得
        settings = {}
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM server_settings WHERE guild_id = ?", (str(guild.id),))
            row = cursor.fetchone()
            if row:
                settings = dict(row)
                # JSON文字列として保存されたフィールドをデコード
                if settings.get('banned_words'):
                    settings['banned_words'] = json.loads(settings['banned_words'])
                else:
                    settings['banned_words'] = []
                if settings.get('log_types'):
                    settings['log_types'] = json.loads(settings['log_types'])
                else:
                    settings['log_types'] = []
                # INTEGERとして保存されたBOOLEAN値をPythonのboolに変換
                settings['enable_fun_commands'] = bool(settings.get('enable_fun_commands', 0))
                settings['enable_anti_spam'] = bool(settings.get('enable_anti_spam', 0))
            else:
                print(f"No settings found in SQLite for guild {guild.id}. Using default settings for welcome message.")
                settings = {
                    "prefix": "!",
                    "welcome_message": "",
                    "enable_fun_commands": False,
                    "mute_role_id": "",
                    "banned_words": [],
                    "enable_anti_spam": False,
                    "log_channel_id": "",
                    "log_types": []
                }
        
        welcome_message_template = settings.get('welcome_message')
        log_channel_id = settings.get('log_channel_id')

        if welcome_message_template:
            message_to_send = welcome_message_template.replace('{user}', member.mention).replace('{guild}', guild.name)
            
            if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
                try:
                    await guild.system_channel.send(message_to_send)
                    print(f"Sent welcome message to {guild.system_channel.name} in {guild.name}.")
                except discord.Forbidden:
                    print(f"Bot does not have permission to send messages to system channel in {guild.name}.")
                except Exception as e:
                    print(f"Error sending welcome message to system channel in {guild.name}: {e}")
            elif log_channel_id:
                log_channel = guild.get_channel(int(log_channel_id))
                if log_channel and isinstance(log_channel, discord.TextChannel) and log_channel.permissions_for(guild.me).send_messages:
                    try:
                        await log_channel.send(message_to_send)
                        print(f"Sent welcome message to log channel {log_channel.name} in {guild.name}.")
                    except discord.Forbidden:
                        print(f"Bot does not have permission to send messages to log channel in {guild.name}.")
                    except Exception as e:
                        print(f"Error sending welcome message to log channel in {guild.name}: {e}")
                else:
                    print(f"Log channel {log_channel_id} not found or bot lacks permissions in {guild.name}.")
            else:
                print(f"No suitable channel found to send welcome message in {guild.name}.")
        else:
            print(f"No welcome message configured for guild {guild.name}.")


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

# --- Flask APIエンドポイント (ボット内で実行) ---
# 注意: Flaskルートはasyncioのイベントループとは異なるスレッドで実行されるため、
# Discord.pyのasync/await関数を直接呼び出す場合は注意が必要です。
# ここでは、asyncio.to_thread を使用して安全に呼び出します。

@api_app.route('/api/bot/joined_guilds', methods=['GET'])
async def get_bot_joined_guilds_api():
    """ボットが参加しているギルドのIDリストを返すAPI"""
    def _get_joined_guilds_sync():
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT guild_id FROM bot_joined_guilds WHERE joined = 1")
            return [row['guild_id'] for row in cursor.fetchall()]
    
    try:
        guild_ids = await asyncio.to_thread(_get_joined_guilds_sync)
        return jsonify(guild_ids), 200
    except Exception as e:
        print(f"Error fetching joined guilds from SQLite: {e}")
        return jsonify({"message": "Failed to fetch joined guilds"}), 500

@api_app.route('/api/bot/server_settings/<guild_id>', methods=['GET'])
async def get_server_settings_api(guild_id):
    """指定されたギルドのサーバー設定を返すAPI"""
    def _get_server_settings_sync():
        settings = {}
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM server_settings WHERE guild_id = ?", (guild_id,))
            row = cursor.fetchone()
            if row:
                settings = dict(row)
                # JSON文字列として保存されたフィールドをデコード
                if settings.get('banned_words'):
                    settings['banned_words'] = json.loads(settings['banned_words'])
                else:
                    settings['banned_words'] = [] # Noneの場合は空リスト
                if settings.get('log_types'):
                    settings['log_types'] = json.loads(settings['log_types'])
                else:
                    settings['log_types'] = [] # Noneの場合は空リスト
                # INTEGERとして保存されたBOOLEAN値をPythonのboolに変換
                settings['enable_fun_commands'] = bool(settings.get('enable_fun_commands', 0))
                settings['enable_anti_spam'] = bool(settings.get('enable_anti_spam', 0))
            else:
                print(f"No settings found in DB for guild {guild_id}. Returning default.")
                # デフォルト設定
                settings = {
                    "prefix": "!",
                    "welcome_message": "",
                    "enable_fun_commands": False,
                    "mute_role_id": "",
                    "banned_words": [],
                    "enable_anti_spam": False,
                    "log_channel_id": "",
                    "log_types": []
                }
        return settings

    try:
        settings = await asyncio.to_thread(_get_server_settings_sync)
        return jsonify(settings), 200
    except Exception as e:
        print(f"Error fetching server settings from SQLite for {guild_id}: {e}")
        return jsonify({"message": "Failed to fetch server settings"}), 500

@api_app.route('/api/bot/server_settings/<guild_id>', methods=['POST'])
async def update_server_settings_api(guild_id):
    """指定されたギルドのサーバー設定を更新するAPI"""
    def _update_server_settings_sync(data):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 既存の設定を読み込み、新しいデータで更新
            # まず既存のデータを取得し、存在しない場合はデフォルトで初期化
            cursor.execute("SELECT * FROM server_settings WHERE guild_id = ?", (guild_id,))
            existing_row = cursor.fetchone()
            if existing_row:
                existing_settings = dict(existing_row)
                # JSON文字列をデコード
                if existing_settings.get('banned_words'):
                    existing_settings['banned_words'] = json.loads(existing_settings['banned_words'])
                else:
                    existing_settings['banned_words'] = []
                if existing_settings.get('log_types'):
                    existing_settings['log_types'] = json.loads(existing_settings['log_types'])
                else:
                    existing_settings['log_types'] = []
                existing_settings['enable_fun_commands'] = bool(existing_settings.get('enable_fun_commands', 0))
                existing_settings['enable_anti_spam'] = bool(existing_settings.get('enable_anti_spam', 0))
            else:
                existing_settings = {
                    "prefix": "!",
                    "welcome_message": "",
                    "enable_fun_commands": False,
                    "mute_role_id": "",
                    "banned_words": [],
                    "enable_anti_spam": False,
                    "log_channel_id": "",
                    "log_types": []
                }

            # 受け取ったデータで既存の設定を上書き
            for key, value in data.items():
                if key in ['enable_fun_commands', 'enable_anti_spam']:
                    existing_settings[key] = bool(value) # boolで受け取ってboolで保存
                elif key in ['banned_words', 'log_types']:
                    existing_settings[key] = value # リストとして受け取ってそのまま保存（後でdumps）
                else:
                    existing_settings[key] = value

            # 保存前にJSON文字列にエンコード
            banned_words_json = json.dumps(existing_settings.get('banned_words', []))
            log_types_json = json.dumps(existing_settings.get('log_types', []))
            
            # ブール値はINTEGERに変換
            enable_fun_commands_int = int(existing_settings.get('enable_fun_commands', False))
            enable_anti_spam_int = int(existing_settings.get('enable_anti_spam', False))

            # INSERT OR REPLACE を使用して、存在すれば更新、なければ挿入
            cursor.execute('''
                INSERT OR REPLACE INTO server_settings (
                    guild_id, prefix, welcome_message, enable_fun_commands, 
                    mute_role_id, banned_words, enable_anti_spam, 
                    log_channel_id, log_types
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                guild_id,
                existing_settings.get('prefix'),
                existing_settings.get('welcome_message'),
                enable_fun_commands_int,
                existing_settings.get('mute_role_id'),
                banned_words_json,
                enable_anti_spam_int,
                existing_settings.get('log_channel_id'),
                log_types_json
            ))
            conn.commit()
        return {"message": "Settings updated successfully", "status": "success"}

    try:
        data = request.get_json()
        print(f"API: Received update for guild {guild_id}: {data}")
        result = await asyncio.to_thread(_update_server_settings_sync, data)
        return jsonify(result), 200
    except Exception as e:
        print(f"Error updating server settings in SQLite for {guild_id}: {e}")
        return jsonify({"message": "Failed to update settings", "status": "error"}), 500

# Flask APIサーバーを別スレッドで実行する関数
def run_api_server():
    # Flaskのデバッグモードは本番ではFalseに
    api_app.run(host='0.0.0.0', port=API_PORT, debug=False)

# ===== Bot起動 =====
if __name__ == '__main__':
    if not DISCORD_BOT_TOKEN:
        print("Error: DISCORD_BOT_TOKEN environment variable not set.")
        sys.exit(1)

    # Flask APIサーバーを別スレッドで開始
    api_thread = threading.Thread(target=run_api_server)
    api_thread.daemon = True # メインスレッド終了時に一緒に終了
    api_thread.start()
    print(f"Flask API server started on port {API_PORT} in a separate thread.")

    # Discordボットを実行
    try:
        bot.run(DISCORD_BOT_TOKEN)
    except discord.LoginFailure:
        print("Error: Invalid Discord bot token. Please check DISCORD_BOT_TOKEN in your .env file.")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred during bot execution: {e}")
        sys.exit(1)

