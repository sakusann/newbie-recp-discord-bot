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
        mongo_client = pymongo.MongoClient(MONGO_URI)
        db = mongo_client.get_database("discord_bot_db").get_collection("server_configs")
        print("✅ MongoDBに正常に接続しました。")
    except Exception as e:
        print(f"❌ MongoDB接続エラー: {e}")
else:
    print("❌ MONGO_URIが環境変数に設定されていません。")

# --- DB操作関数 ---
def get_config(server_id):
    if db is None: return {}
    return db.find_one({"_id": server_id}) or {}

def update_config(server_id, new_values):
    if db is None: return
    db.update_one({"_id": server_id}, {"$set": new_values}, upsert=True)

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
        try:
            synced = await self.tree.sync()
            print(f"✅ {len(synced)} 個のコマンドを同期しました")
        except Exception as e:
            print(f"❌ コマンド同期エラー: {e}")

client = MyClient(intents=intents)

# ★★★★★★★★★★★★★★★★★★★★★★★
# ここからコマンド定義（すべて defer() を適用）
# ★★★★★★★★★★★★★★★★★★★★★★★

@client.tree.command(name="set_channel", description="キーワードに反応するチャンネルを設定します。")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True) # 先に応答を保留
    update_config(str(interaction.guild.id), {"channel_id": channel.id})
    await interaction.followup.send(f"✅ 監視対象を {channel.mention} に設定しました。", ephemeral=True)

@client.tree.command(name="set_config", description="キーワードと付与するロールを設定します。")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_config(interaction: discord.Interaction, keyword: str, role: discord.Role):
    await interaction.response.defer(ephemeral=True) # 先に応答を保留
    if interaction.guild.me.top_role <= role:
        await interaction.followup.send(f"❌ Botのロールを {role.mention} より上位に配置してください。", ephemeral=True)
        return
    update_config(str(interaction.guild.id), {"keyword": keyword, "role_id": role.id})
    await interaction.followup.send(f"✅ キーワードを「**{keyword}**」、ロールを **{role.mention}** に設定しました。", ephemeral=True)

@client.tree.command(name="set_log_channel", description="ログを送信するチャンネルを設定します。")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_log_channel(interaction: discord.Interaction, log_channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True) # 先に応答を保留
    update_config(str(interaction.guild.id), {"log_channel_id": log_channel.id})
    await interaction.followup.send(f"✅ ログを {log_channel.mention} に送信します。", ephemeral=True)

@client.tree.command(name="show_config", description="現在の設定を確認します。")
@app_commands.checks.has_permissions(manage_guild=True)
async def show_config(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True) # 先に応答を保留
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
    await interaction.response.defer(ephemeral=True) # 先に応答を保留
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
                # この部分はDB通信を伴わないのでdeferは不要
                await message.author.add_roles(role)
                # ログ送信はDB通信を伴うが、バックグラウンド処理なのでエラーになっても影響は少ない
                # ユーザーへの応答を優先する
                await message.channel.send(f"{message.author.mention} に **{role.name}** を付与しました！", delete_after=10)
                await send_log(message.guild, "✅ ロール付与成功", f"{message.author.mention} に **{role.name}** を付与", discord.Color.green())
            except Exception as e:
                print(f"ロール付与エラー: {e}")

# --- メイン実行 ---
# Webサーバーを起動
keep_alive()

# Botを起動
if DISCORD_TOKEN:
    print("🚀 Discord Bot を起動中...")
    try:
        client.run(DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ Bot起動エラー: {e}")
else:
    print("❌ DISCORD_TOKENが環境変数に設定されていません。")
