from discord.ext import commands
import discord

class PanelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="rolepanel", description="ロールパネルを作成します。")
    @commands.has_permissions(manage_roles=True)
    async def panel_role_command(self, ctx: commands.Context, タイトル: str, 説明: str, メンションを表示するか: bool, ロール1: discord.Role, ロール2: discord.Role = None, ロール3: discord.Role = None, ロール4: discord.Role = None, ロール5: discord.Role = None, ロール6: discord.Role = None, ロール7: discord.Role = None, ロール8: discord.Role = None, ロール9: discord.Role = None, ロール10: discord.Role = None):
        view = discord.ui.View()
        ls = []
        view.add_item(discord.ui.Button(label=f"{ロール1.name}", custom_id=f"rolepanel_v1+{ロール1.id}"))
        ls.append(f"{ロール1.mention}")
        try:
            view.add_item(discord.ui.Button(label=f"{ロール2.name}", custom_id=f"rolepanel_v1+{ロール2.id}"))
            ls.append(f"{ロール2.mention}")
        except:
            pass
        try:
            view.add_item(discord.ui.Button(label=f"{ロール3.name}", custom_id=f"rolepanel_v1+{ロール3.id}"))
            ls.append(f"{ロール3.mention}")
        except:
            pass
        try:
            view.add_item(discord.ui.Button(label=f"{ロール4.name}", custom_id=f"rolepanel_v1+{ロール4.id}"))
            ls.append(f"{ロール4.mention}")
        except:
            pass
        try:
            view.add_item(discord.ui.Button(label=f"{ロール5.name}", custom_id=f"rolepanel_v1+{ロール5.id}"))
            ls.append(f"{ロール5.mention}")
        except:
            pass
        try:
            view.add_item(discord.ui.Button(label=f"{ロール6.name}", custom_id=f"rolepanel_v1+{ロール6.id}"))
            ls.append(f"{ロール6.mention}")
        except:
            pass
        try:
            view.add_item(discord.ui.Button(label=f"{ロール7.name}", custom_id=f"rolepanel_v1+{ロール7.id}"))
            ls.append(f"{ロール7.mention}")
        except:
            pass
        try:
            view.add_item(discord.ui.Button(label=f"{ロール8.name}", custom_id=f"rolepanel_v1+{ロール8.id}"))
            ls.append(f"{ロール8.mention}")
        except:
            pass
        try:
            view.add_item(discord.ui.Button(label=f"{ロール9.name}", custom_id=f"rolepanel_v1+{ロール9.id}"))
            ls.append(f"{ロール9.mention}")
        except:
            pass
        try:
            view.add_item(discord.ui.Button(label=f"{ロール10.name}", custom_id=f"rolepanel_v1+{ロール10.id}"))
            ls.append(f"{ロール10.mention}")
        except:
            pass
        embed = discord.Embed(title=f"{タイトル}", description=f"{説明}", color=discord.Color.green())
        if メンションを表示するか:
            embed.add_field(name="ロール一覧", value=f"\n".join(ls))
        await ctx.channel.send(embed=embed, view=view)
        await ctx.reply(embed=discord.Embed(title="作成しました。", color=discord.Color.green()), ephemeral=True)

    @commands.Cog.listener(name="on_interaction")
    async def on_interaction_panel(self, interaction: discord.Interaction):
        try:
            if interaction.data['component_type'] == 2:
                try:
                    custom_id = interaction.data["custom_id"]
                except:
                    return
                if "rolepanel_v1+" in custom_id:
                    try:
                        await interaction.response.defer(ephemeral=True)
                        if not interaction.guild.get_role(int(custom_id.split("+")[1])) in interaction.user.roles:
                            await interaction.user.add_roles(interaction.guild.get_role(int(custom_id.split("+")[1])))
                            await interaction.followup.send("ロールを追加しました。", ephemeral=True)
                        else:
                            await interaction.user.remove_roles(interaction.guild.get_role(int(custom_id.split("+")[1])))
                            await interaction.followup.send("ロールを剥奪しました。", ephemeral=True)
                    except discord.Forbidden as f:
                        await interaction.followup.send("付与したいロールの位置がSharkBotのロールよりも\n上にあるため付与できませんでした。\nhttps://i.imgur.com/fGcWslT.gif", ephemeral=True)
                    except:
                        await interaction.followup.send("追加に失敗しました。", ephemeral=True)
        except:
            return

async def setup(bot):
    await bot.add_cog(PanelCog(bot))
