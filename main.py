import discord
from discord import app_commands
import os
from keep_alive import keep_alive
import pymongo # ★ 追加

# MongoDB 接続
try:
    MONGO_URI = os.getenv("MONGO_URI")
    mongo_client = pymongo.MongoClient(MONGO_URI)
    db = mongo_client.get_database("discord_bot_db").get_collection("server_configs")
    print("✅ MongoDBに正常に接続しました。")
except Exception as e:
    print(f"❌ MongoDB接続エラー: {e}")
    db = None

# Discord TOKEN
TOKEN = os.getenv("DISCORD_TOKEN")

# ★★★★★ DB操作関数をMongoDB用に変更 ★★★★★
def get_config(server_id):
    if db is None: return {}
    config = db.find_one({"_id": server_id})
    return config if config else {}

def update_config(server_id, new_values):
    if db is None: return
    db.update_one({"_id": server_id}, {"$set": new_values}, upsert=True)

# Discord Bot設定 (以下、変更は少ない)
intents = discord.Intents.default()
# (中略... MyClientクラスやエラーハンドリング、ログ送信関数はほぼ同じなので省略)
# (ただし、DB操作部分は新しい関数を使うように変更します)
# (以下、完全なコードです)

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

async def handle_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # (この関数は変更なし)
    message = "❌ 予期せぬエラーが発生しました。"
    if isinstance(error, app_commands.MissingPermissions):
        message = "❌ このコマンドを実行するには「サーバーの管理」権限が必要です。"
    print(f"エラー詳細: {type(error).__name__}: {error}")
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


async def send_log(guild, title, description, color):
    config = get_config(str(guild.id)) # ★ 変更
    log_channel_id = config.get("log_channel_id")
    if log_channel_id:
        log_channel = guild.get_channel(log_channel_id)
        if log_channel:
            embed = discord.Embed(title=title, description=description, color=color)
            await log_channel.send(embed=embed)

# --- コマンド定義 (DB操作部分を修正) ---

@client.tree.command(name="set_channel", description="キーワードに反応するチャンネルを設定します。")
@app_commands.describe(channel="対象にしたいチャンネル")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    server_id = str(interaction.guild.id)
    update_config(server_id, {"channel_id": channel.id}) # ★ 変更
    await interaction.response.send_message(f"✅ 監視対象を {channel.mention} に設定しました。", ephemeral=True)

@client.tree.command(name="set_config", description="キーワードと付与するロールを設定します。")
@app_commands.describe(keyword="反応するキーワード", role="付与するロール")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_config(interaction: discord.Interaction, keyword: str, role: discord.Role):
    if interaction.guild.me.top_role <= role:
        await interaction.response.send_message(f"❌ Botのロールを {role.mention} より上位に配置してください。", ephemeral=True)
        return
    server_id = str(interaction.guild.id)
    update_config(server_id, {"keyword": keyword, "role_id": role.id}) # ★ 変更
    await interaction.response.send_message(f"✅ キーワードを「**{keyword}**」、ロールを **{role.mention}** に設定しました。", ephemeral=True)

@client.tree.command(name="set_log_channel", description="ログを送信するチャンネルを設定します。")
@app_commands.describe(log_channel="ログ用チャンネル")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_log_channel(interaction: discord.Interaction, log_channel: discord.TextChannel):
    server_id = str(interaction.guild.id)
    update_config(server_id, {"log_channel_id": log_channel.id}) # ★ 変更
    await interaction.response.send_message(f"✅ ログを {log_channel.mention} に送信します。", ephemeral=True)

@client.tree.command(name="show_config", description="現在の設定を確認します。")
@app_commands.checks.has_permissions(manage_guild=True)
async def show_config(interaction: discord.Interaction):
    config = get_config(str(interaction.guild.id)) # ★ 変更
    # (以下、表示ロジックはほぼ同じ)
    channel = interaction.guild.get_channel(config.get("channel_id"))
    role = interaction.guild.get_role(config.get("role_id"))
    log_channel = interaction.guild.get_channel(config.get("log_channel_id"))
    embed = discord.Embed(title="現在のBot設定", color=discord.Color.blue())
    embed.add_field(name="監視チャンネル", value=channel.mention if channel else "未設定", inline=False)
    embed.add_field(name="キーワード", value=config.get("keyword", "未設定"), inline=False)
    embed.add_field(name="付与するロール", value=role.mention if role else "未設定", inline=False)
    embed.add_field(name="ログチャンネル", value=log_channel.mention if log_channel else "未設定", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@client.tree.command(name="ping", description="Botの動作をテストします。")
async def ping(interaction: discord.Interaction):
    latency = client.latency * 1000
    db_ping = "N/A"
    if db:
        try:
            start_time = discord.utils.utcnow().timestamp()
            db.command("ping")
            end_time = discord.utils.utcnow().timestamp()
            db_ping = f"{(end_time - start_time) * 1000:.2f}ms"
        except Exception:
            db_ping = "失敗"
            
    await interaction.response.send_message(f"🏓 Pong!\nDiscord API: {latency:.2f}ms\nDatabase: {db_ping}", ephemeral=True)
    
# (エラーハンドラやon_ready, on_messageイベントのロジックも新しいDB関数を使うように修正)
@set_channel.error
@set_config.error
@set_log_channel.error
@show_config.error
@ping.error
async def on_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await handle_error(interaction, error)

@client.event
async def on_ready():
    print(f'✅ {client.user} としてログインしました！')

@client.event
async def on_message(message):
    if message.author.bot or not message.guild: return

    config = get_config(str(message.guild.id)) # ★ 変更
    target_channel_id = config.get("channel_id")
    keyword = config.get("keyword")
    role_id = config.get("role_id")

    if not all([target_channel_id, keyword, role_id]): return

    if message.channel.id == target_channel_id and keyword in message.content:
        role = message.guild.get_role(role_id)
        if role is None or role in message.author.roles: return

        try:
            await message.author.add_roles(role)
            await send_log(message.guild, "✅ ロール付与成功", f"{message.author.mention} に **{role.name}** を付与", discord.Color.green())
            await message.channel.send(f"{message.author.mention} に **{role.name}** ロールを付与しました！", delete_after=10)
        except discord.Forbidden:
            await send_log(message.guild, "❌ ロール付与失敗", f"権限不足", discord.Color.red())
        except Exception as e:
            print(f"ロール付与エラー: {e}")

# --- メイン実行 ---
if __name__ == "__main__":
    keep_alive()
    if not TOKEN:
        print("❌ DISCORD_TOKENが設定されていません！")
    if not MONGO_URI:
        print("❌ MONGO_URIが設定されていません！")
    
    if TOKEN and MONGO_URI:
        try:
            client.run(TOKEN)
        except Exception as e:
            print(f"❌ Bot起動エラー: {e}")
