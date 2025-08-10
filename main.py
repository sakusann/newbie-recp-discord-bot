import discord
from discord import app_commands
import os
import pymongo
from keep_alive import keep_alive

# ===================================================================
# 環境変数の読み込み
# ===================================================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
# ===================================================================

# MongoDB 接続
mongo_client = None
db = None
if MONGO_URI:
    try:
        mongo_client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        mongo_client.server_info()
        db = mongo_client.get_database("discord_bot_db").get_collection("server_configs")
        print("✅ MongoDBに正常に接続しました。")
    except Exception as e:
        print(f"❌ MongoDB接続エラー: {e}")
else:
    print("❌ MONGO_URIが環境変数に設定されていません。")

# --- DB操作関数（改良版） ---
def get_config(server_id):
    if db is None: return {}
    return db.find_one({"_id": server_id}) or {}

def update_config(server_id, new_values):
    if db is None: return None
    try:
        # 書き込み結果を待つように変更
        result = db.update_one({"_id": server_id}, {"$set": new_values}, upsert=True)
        print(f"🔄 DB更新試行: server_id={server_id}, acknowledged={result.acknowledged}")
        return result
    except Exception as e:
        print(f"❌ update_configエラー: {e}")
        return None

# --- Discord Bot設定 ---
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
intents.members = True

class MyClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ コマンドツリーを同期しました。")

client = MyClient(intents=intents)

# --- コマンド定義（応答部分を強化） ---
@client.tree.command(name="set_channel", description="キーワードに反応するチャンネルを設定します。")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    result = update_config(str(interaction.guild.id), {"channel_id": channel.id})
    if result and result.acknowledged:
        await interaction.followup.send(f"✅ 監視対象を {channel.mention} に設定しました。", ephemeral=True)
    else:
        await interaction.followup.send("❌ データベースの更新に失敗しました。再度お試しください。", ephemeral=True)

@client.tree.command(name="set_config", description="キーワードと付与するロールを設定します。")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_config(interaction: discord.Interaction, keyword: str, role: discord.Role):
    await interaction.response.defer(ephemeral=True)
    if interaction.guild.me.top_role <= role:
        await interaction.followup.send(f"❌ Botのロールを {role.mention} より上位に配置してください。", ephemeral=True)
        return
    result = update_config(str(interaction.guild.id), {"keyword": keyword, "role_id": role.id})
    if result and result.acknowledged:
        await interaction.followup.send(f"✅ キーワードを「**{keyword}**」、ロールを **{role.mention}** に設定しました。", ephemeral=True)
    else:
        await interaction.followup.send("❌ データベースの更新に失敗しました。再度お試しください。", ephemeral=True)

@client.tree.command(name="set_log_channel", description="ログを送信するチャンネルを設定します。")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_log_channel(interaction: discord.Interaction, log_channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    result = update_config(str(interaction.guild.id), {"log_channel_id": log_channel.id})
    if result and result.acknowledged:
        await interaction.followup.send(f"✅ ログを {log_channel.mention} に送信します。", ephemeral=True)
    else:
        await interaction.followup.send("❌ データベースの更新に失敗しました。再度お試しください。", ephemeral=True)
        
@client.tree.command(name="check_roles", description="Botのロール階層と権限を診断します。") # 診断機能も追加
@app_commands.checks.has_permissions(manage_guild=True)
async def check_roles(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    bot_member = interaction.guild.me
    permissions = bot_member.guild_permissions
    embed = discord.Embed(title="🔍 Bot権限・階層診断", color=discord.Color.orange())
    embed.add_field(name="Botの最上位ロール", value=f"{bot_member.top_role.mention} (位置: {bot_member.top_role.position})", inline=False)
    embed.add_field(
        name="必要な権限",
        value=f"ロール管理: {'✅' if permissions.manage_roles else '❌'}\n"
              f"メッセージ管理: {'✅' if permissions.manage_messages else '❌'}\n"
              f"メッセージ送信: {'✅' if permissions.send_messages else '❌'}",
        inline=False
    )
    await interaction.followup.send(embed=embed, ephemeral=True)

@client.tree.command(name="show_config", description="現在の設定を確認します。")
@app_commands.checks.has_permissions(manage_guild=True)
async def show_config(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    config = get_config(str(interaction.guild.id))
    channel = interaction.guild.get_channel(config.get("channel_id"))
    role = interaction.guild.get_role(config.get("role_id"))
    log_channel = interaction.guild.get_channel(config.get("log_channel_id"))
    embed = discord.Embed(title="現在のBot設定", color=discord.Color.blue())
    embed.add_field(name="監視チャンネル", value=channel.mention if channel else "未設定", inline=False)
    embed.add_field(name="キーワード", value=config.get("keyword", "未設定"), inline=False)
    embed.add_field(name="付与するロール", value=role.mention if role else "未設定", inline=False)
    embed.add_field(name="ログチャンネル", value=log_channel.mention if log_channel else "未設定", inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)

@client.tree.command(name="ping", description="Botの動作と応答速度をテストします。")
async def ping(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    latency = client.latency * 1000
    await interaction.followup.send(f"🏓 **Pong!**\n応答速度: `{latency:.2f}ms`", ephemeral=True)
    
# --- イベントハンドラ ---
@client.event
async def on_ready():
    print(f'✅ {client.user} としてログインしました！')

@client.event
async def on_message(message):
    if message.author.bot or not message.guild: return
    config = get_config(str(message.guild.id))
    target_channel_id, keyword, role_id = config.get("channel_id"), config.get("keyword"), config.get("role_id")
    if not all([target_channel_id, keyword, role_id]): return
    if message.channel.id == target_channel_id and keyword in message.content:
        role = message.guild.get_role(role_id)
        if role and role not in message.author.roles:
            try:
                await message.author.add_roles(role)
                await message.channel.send(f"{message.author.mention} に **{role.name}** を付与しました！", delete_after=10)
                # ログ送信はDB書き込みを伴うため、成功を保証しない
                # await send_log(message.guild, "✅ ロール付与成功", f"{message.author.mention} に **{role.name}** を付与", discord.Color.green())
            except Exception as e:
                print(f"ロール付与エラー: {e}")

# --- メイン実行 ---
keep_alive()
if DISCORD_TOKEN:
    print("🚀 Discord Bot を起動中...")
    client.run(DISCORD_TOKEN)
else:
    print("❌ DISCORD_TOKENが環境変数に設定されていません。")
