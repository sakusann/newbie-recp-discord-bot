import discord
from discord import app_commands
import os
from threading import Thread
import json
from flask import Flask

# ---------------------------------
# 設定が必要な項目
# ---------------------------------
TOKEN = os.getenv("DISCORD_TOKEN")

# Render用のデータストレージ（JSONファイル）
def load_db():
    try:
        with open('bot_data.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_db(data):
    with open('bot_data.json', 'w') as f:
        json.dump(data, f, indent=2)

# Flask keep-alive server
app = Flask('')

@app.route('/')
def home():
    return "Discord Bot is running on Render! 🚀"

@app.route('/ping')
def ping():
    return "pong"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# ---------------------------------

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
            for cmd in synced:
                print(f"  - /{cmd.name}: {cmd.description}")
        except Exception as e:
            print(f"❌ コマンド同期エラー: {e}")

client = MyClient(intents=intents)

# --- エラーハンドリング ---
async def handle_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    try:
        if isinstance(error, app_commands.MissingPermissions):
            message = "❌ このコマンドを実行するには「サーバーの管理」権限が必要です。"
        elif isinstance(error, app_commands.CommandOnCooldown):
            message = f"❌ コマンドがクールダウン中です。{error.retry_after:.2f}秒後に再試行してください。"
        else:
            message = "❌ 予期せぬエラーが発生しました。"
            print(f"エラー詳細: {type(error).__name__}: {error}")
        
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except Exception as e:
        print(f"エラーハンドラでエラー: {e}")

# --- ログ送信用の関数 ---
async def send_log(guild, title, description, color):
    try:
        db = load_db()
        config = db.get(str(guild.id), {})
        log_channel_id = config.get("log_channel_id")
        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if log_channel:
                embed = discord.Embed(title=title, description=description, color=color)
                await log_channel.send(embed=embed)
    except Exception as e:
        print(f"ログ送信エラー: {e}")

# コマンド設定（あなたの既存コードをそのまま使用）
@client.tree.command(name="set_channel", description="キーワードに反応するチャンネルを設定します。")
@app_commands.describe(channel="対象にしたいチャンネルを選択してください。")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    try:
        server_id = str(interaction.guild.id)
        db = load_db()
        if server_id not in db:
            db[server_id] = {}
        db[server_id]["channel_id"] = channel.id
        save_db(db)
        await interaction.response.send_message(
            f"✅ **チャンネル設定完了！**\n監視対象を {channel.mention} に設定しました。", 
            ephemeral=True
        )
        print(f"チャンネル設定: {interaction.guild.name} -> {channel.name}")
    except Exception as e:
        print(f"set_channel エラー: {e}")
        await handle_error(interaction, e)

@client.tree.command(name="set_config", description="ロール付与のキーワードと、付与するロールを設定します。")
@app_commands.describe(keyword="反応させたいキーワード（例: 合言葉）", role="付与したいロールを選択")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_config(interaction: discord.Interaction, keyword: str, role: discord.Role):
    try:
        server_id = str(interaction.guild.id)
        if interaction.guild.me.top_role <= role:
            await interaction.response.send_message(
                f"❌ **設定エラー**\nBotのロール({interaction.guild.me.top_role.mention})は、"
                f"付与したいロール({role.mention})よりも上位に配置する必要があります。\n"
                f"サーバー設定 > ロール から順番を変更してください。", 
                ephemeral=True
            )
            return
        
        db = load_db()
        if server_id not in db:
            db[server_id] = {}
        db[server_id]["keyword"] = keyword
        db[server_id]["role_id"] = role.id
        save_db(db)
        await interaction.response.send_message(
            f"✅ **キーワード・ロール設定完了！**\n"
            f"キーワードが「**{keyword}**」、付与するロールが **{role.mention}** に設定されました。", 
            ephemeral=True
        )
        print(f"設定完了: {interaction.guild.name} -> キーワード: {keyword}, ロール: {role.name}")
    except Exception as e:
        print(f"set_config エラー: {e}")
        await handle_error(interaction, e)

@client.tree.command(name="ping", description="Botが正常に動作しているかテストします。")
async def ping(interaction: discord.Interaction):
    try:
        await interaction.response.send_message("🏓 Pong! Renderで稼働中！", ephemeral=True)
        print(f"Pingコマンド実行: {interaction.user.name} in {interaction.guild.name}")
    except Exception as e:
        print(f"ping エラー: {e}")
        await handle_error(interaction, e)

# メッセージ監視
@client.event
async def on_ready():
    print(f'{client.user} としてRenderでログインしました！')
    print(f'Bot ID: {client.user.id}')
    print(f'参加サーバー数: {len(client.guilds)}')

@client.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    try:
        server_id = str(message.guild.id)
        db = load_db()
        config = db.get(server_id)
        if not config: 
            return

        target_channel_id = config.get("channel_id")
        keyword = config.get("keyword")
        role_id = config.get("role_id")

        if not all([target_channel_id, keyword, role_id]): 
            return

        if message.channel.id == target_channel_id:
            if keyword in message.content:
                role = message.guild.get_role(role_id)
                if role is None or role in message.author.roles: 
                    return

                try:
                    await message.author.add_roles(role)
                    await send_log(message.guild, "✅ ロール付与成功", 
                                 f"{message.author.mention} に **{role.name}** を付与しました。", 
                                 discord.Color.green())
                    
                    await message.channel.send(
                        f"{message.author.mention}さんに **{role.name}** ロールを付与しました！", 
                        delete_after=10
                    )
                    print(f"ロール付与成功: {message.author.name} -> {role.name}")
                    
                except discord.Forbidden:
                    await send_log(message.guild, "❌ ロール付与失敗", 
                                 f"権限不足: {message.author.mention} -> {role.mention}", 
                                 discord.Color.red())
                except Exception as e:
                    print(f"ロール付与時のエラー: {e}")
                    
    except Exception as e:
        print(f"メッセージ処理エラー: {e}")

# Keep-alive開始
keep_alive()

if not TOKEN:
    print("❌ DISCORD_TOKENが設定されていません！")
    exit(1)

print("🚀 RenderでDiscord Bot を起動しています...")

try:
    client.run(TOKEN)
except Exception as e:
    print(f"❌ Bot起動エラー: {e}")
    os._exit(1)