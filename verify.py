import discord
from discord.ext import commands
import random
import string
import io
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import json
import os
from datetime import timedelta

ROLE_FILE = "roles.json"

def load_roles():
    if os.path.exists(ROLE_FILE):
        with open(ROLE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_roles(data):
    with open(ROLE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

class CodeModal(discord.ui.Modal, title="認証コードの入力"):
    def __init__(self, cog, user):
        super().__init__()
        self.cog = cog
        self.user = user
        self.add_item(discord.ui.TextInput(
            label="認証コードを入力",
            placeholder="例: ABCD1",
            max_length=10
        ))

    async def on_submit(self, interaction: discord.Interaction):
        input_code = self.children[0].value.strip().upper()
        verify_info = self.cog.verify_codes.get(self.user.id)

        if verify_info is None:
            await interaction.response.send_message(
                "<:warn:1394241229176311888> 認証データが見つかりません。もう一度 `/verify` から始めてください。",
                ephemeral=True
            )
            return

        code, guild_id, role_id = verify_info
        guild = self.cog.bot.get_guild(int(guild_id))
        member = guild.get_member(self.user.id)

        if input_code == code:
            if guild and member:
                role = guild.get_role(role_id)
                if role:
                    await member.add_roles(role)
                    self.cog.verify_codes.pop(self.user.id, None)
                    await interaction.response.send_message(f"<:check:1394240622310850580>認証しました。", ephemeral=True)
                    return

            await interaction.response.send_message("<:warn:1394241229176311888> サーバーまたはロール情報に問題があります。", ephemeral=True)
        else:
            # 認証失敗 → タイムアウト処理（1分）
            if member:
                try:
                    await member.timeout(discord.utils.utcnow() + timedelta(minutes=10), reason="認証失敗")
                    await interaction.response.send_message(
                        f"<:cross:1394240624202481705>認証に失敗しました。\n1分後にやり直してください。",
                        ephemeral=True
                    )
                except discord.Forbidden:
                    await interaction.response.send_message(
                        f"<:cross:1394240624202481705>認証に失敗しました。",
                        ephemeral=True
                    )
            else:
                await interaction.response.send_message(
                    f"<:cross:1394240624202481705>メンバー情報が取得できませんでした。",
                    ephemeral=True
                )

class CodeInputButton(discord.ui.Button):
    def __init__(self, cog, user):
        super().__init__(label="コードを入力", style=discord.ButtonStyle.success)
        self.cog = cog
        self.user = user

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(f"<:cross:1394240624202481705>このボタンはあなた専用です。", ephemeral=True)
            return
        await interaction.response.send_modal(CodeModal(self.cog, self.user))

class VerifyStartButton(discord.ui.Button):
    def __init__(self, cog):
        super().__init__(label="認証", style=discord.ButtonStyle.primary)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user
        guild = interaction.guild
        guild_id = str(guild.id)
        roles = load_roles()
        role_id = roles.get(guild_id)

        if role_id is None:
            await interaction.response.send_message(
                f"<:warn:1394241229176311888>認証ロールが設定されていません。管理者に設定してください。",
                ephemeral=True
            )
            return

        role = guild.get_role(role_id)
        if role is None:
            await interaction.response.send_message(
                f"<:warn:1394241229176311888>設定された認証ロールが見つかりません。",
                ephemeral=True
            )
            return

        # 認証コード生成
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))

        # 画像作成
        image = Image.new("RGB", (220, 100), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("arial.ttf", 40)
        except:
            font = ImageFont.load_default()
        draw.text((50, 30), code, font=font, fill=(0, 0, 0))
        for _ in range(5):
            draw.line(
                [(random.randint(0, 220), random.randint(0, 100)),
                 (random.randint(0, 220), random.randint(0, 100))],
                fill=(150, 150, 150), width=2
            )
        for _ in range(200):
            x, y = random.randint(0, 219), random.randint(0, 99)
            draw.point((x, y), fill=(random.randint(0, 255), 0, 0))
        image = image.filter(ImageFilter.GaussianBlur(0.7))

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)

        self.cog.verify_codes[user.id] = (code, guild.id, role_id)

        # コード入力ボタン
        view = discord.ui.View()
        view.add_item(CodeInputButton(self.cog, user))

        file = discord.File(buffer, filename="captcha.png")
        await interaction.response.send_message(
            content=f"以下の画像を見て、`コードを入力` ボタンから認証してください。",
            file=file,
            view=view,
            ephemeral=True
        )

class VerifyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.verify_codes = {}  # user_id: (code, guild_id, role_id)

    @commands.hybrid_command(name="verify", with_app_command=True, description="認証ロール設定または認証パネル送信")
    @commands.has_permissions(administrator=True)
    async def verify(self, ctx: commands.Context, role: discord.Role = None):
        roles = load_roles()
        guild_id = str(ctx.guild.id)
        if role is not None:
            roles[guild_id] = role.id
            save_roles(roles)
            await ctx.send(f"<:check:1394240622310850580>認証ロールを `{role.name}` に設定しました。", ephemeral=True)
        else:
            role_id = roles.get(guild_id)
            if role_id is None:
                await ctx.send(f"<:warn:1394241229176311888> 認証ロールが設定されていません。`/verify @ロール名` で設定してください。", ephemeral=True)
                return
            embed = discord.Embed(
                description=f"<@&{role_id}>をもらうには認証してください。",
                color=discord.Color.green()
            )
            view = discord.ui.View()
            view.add_item(VerifyStartButton(self))  # Cogを渡す
            await ctx.send(embed=embed, view=view)
    @verify.error
    async def verify_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(f"<:cross:1394240624202481705>このコマンドを実行するには管理者権限が必要です。", ephemeral=True)
async def setup(bot):
    await bot.add_cog(VerifyCog(bot))
