import discord
from discord.ext import commands
import traceback
import random
import string

# ✅ Traceback を送りたいチャンネルの ID（ログ専用チャンネルなど）
ERROR_TRACEBACK_CHANNEL_ID = 1394294521113612318

class ErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def generate_error_code(self, length=6):
        return ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=length))

    async def send_error_traceback(self, error_id, error_text):
        channel = self.bot.get_channel(ERROR_TRACEBACK_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title=f"<:error:1394294289353277582>エラー発生（コード: {error_id}）",
                description=f"```py\n{error_text[:3900]}```",  # Discordの上限考慮
                color=discord.Color.red()
            )
            await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return

        error_id = self.generate_error_code()
        error_text = "".join(traceback.format_exception(type(error), error, error.__traceback__))

        print(f"[ERROR CODE {error_id}]\n{error_text}")
        await self.send_error_traceback(error_id, error_text)

        await ctx.send(
            f"<:error:1394294289353277582>コマンド実行中にエラーが発生しました。\nエラーコード: `{error_id}`",
            ephemeral=True if hasattr(ctx, 'interaction') else False
        )

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error):
        if isinstance(error, discord.app_commands.errors.CommandNotFound):
            return

        error_id = self.generate_error_code()
        error_text = "".join(traceback.format_exception(type(error), error, error.__traceback__))

        print(f"[ERROR CODE {error_id}]\n{error_text}")
        await self.send_error_traceback(error_id, error_text)

        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    f"<:error:1394294289353277582>コマンド実行中にエラーが発生しました。\nエラーコード: `{error_id}`",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"<:error:1394294289353277582>コマンド実行中にエラーが発生しました。\nエラーコード: `{error_id}`",
                    ephemeral=True
                )
        except discord.HTTPException:
            pass  # 失敗しても無視

async def setup(bot):
    await bot.add_cog(ErrorHandler(bot))
