from discord.ext import commands
import discord

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="コマンド一覧を表示します")
    async def help_command(self, ctx):
        embed = discord.Embed(
            title="📖 Help - コマンド一覧",
            description="利用可能なコマンドの一覧です。",
            color=discord.Color.blurple()
        )

        embed.add_field(name="!ping /ping", value="Botの応答速度を表示します", inline=False)
        embed.add_field(name="!help /help", value="このヘルプを表示します", inline=False)
        embed.add_field(name="!load [cog]", value="Cogをロード（限定ユーザー）", inline=False)
        embed.add_field(name="!reload [cog]", value="Cogを再読み込み（限定ユーザー）", inline=False)
        embed.add_field(name="!unload [cog]", value="Cogをアンロード（限定ユーザー）", inline=False)
        embed.add_field(name="!listcogs", value="読み込み済みのCogを表示（限定ユーザー）", inline=False)
        embed.add_field(name="!shutdown", value="Botを停止（限定ユーザー）", inline=False)
        embed.add_field(name="!restart", value="Botを再起動（限定ユーザー）", inline=False)

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
