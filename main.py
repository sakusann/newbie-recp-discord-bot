import discord
from discord import app_commands
import os
import json
from keep_alive import keep_alive

# Discord TOKEN
TOKEN = os.getenv("DISCORD_TOKEN")

# データストレージ（JSONファイル）
def load_db():
    try:
        with open('bot_data.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        print("⚠️ bot_data.jsonが破損しています。初期化します。")
        return {}

def save_db(data):
    with open('bot_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# Discord Bot設定
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

# エラーハンドリング
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

# ログ送信機能
async def send_log(guild, title, description, color):
    try:
        db = load_db()
        config = db.get(str(guild.id), {})
        log_channel_id = config.get("log_channel_id")
        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if log_channel:
                embed = discord.Embed(title=title, description=description, color=color)
                embed.set_footer(text="Powered by Render")
                await log_channel.send(embed=embed)
    except Exception as e:
        print(f"ログ送信エラー: {e}")

# コマンド定義
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
                f"付与したいロール({role.mention})よりも上位に配置する必要があります。", 
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
            f"キーワード: **{keyword}**\n付与ロール: **{role.mention}**", 
            ephemeral=True
        )
        print(f"設定完了: {interaction.guild.name} -> キーワード: {keyword}, ロール: {role.name}")
    except Exception as e:
        print(f"set_config エラー: {e}")
        await handle_error(interaction, e)

@client.tree.command(name="set_log_channel", description="Botのログを送信するチャンネルを設定します。")
@app_commands.describe(log_channel="ログチャンネルを選択")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_log_channel(interaction: discord.Interaction, log_channel: discord.TextChannel):
    try:
        server_id = str(interaction.guild.id)
        db = load_db()
        if server_id not in db:
            db[server_id] = {}
        db[server_id]["log_channel_id"] = log_channel.id
        save_db(db)
        await interaction.response.send_message(
            f"✅ **ログチャンネル設定完了！**\n今後、ログを {log_channel.mention} に送信します。", 
            ephemeral=True
        )
    except Exception as e:
        print(f"set_log_channel エラー: {e}")
        await handle_error(interaction, e)

@client.tree.command(name="show_config", description="現在のBotの設定を確認します。")
@app_commands.checks.has_permissions(manage_guild=True)
async def show_config(interaction: discord.Interaction):
    try:
        db = load_db()
        config = db.get(str(interaction.guild.id))
        if not config:
            await interaction.response.send_message("⚙️ まだ設定されていません。", ephemeral=True)
            return
        
        channel_id = config.get("channel_id")
        keyword = config.get("keyword")
        role_id = config.get("role_id")
        log_channel_id = config.get("log_channel_id")
        
        channel = interaction.guild.get_channel(channel_id) if channel_id else None
        role = interaction.guild.get_role(role_id) if role_id else None
        log_channel = interaction.guild.get_channel(log_channel_id) if log_channel_id else None
        
        embed = discord.Embed(title="現在のBot設定", color=discord.Color.blue())
        embed.add_field(
            name="監視チャンネル", 
            value=channel.mention if channel else "未設定", 
            inline=False
        )
        embed.add_field(name="キーワード", value=keyword or "未設定", inline=False)
        embed.add_field(
            name="付与するロール", 
            value=role.mention if role else "未設定", 
            inline=False
        )
        embed.add_field(
            name="ログチャンネル", 
            value=log_channel.mention if log_channel else "未設定", 
            inline=False
        )
        embed.set_footer(text="Hosted on Render")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        print(f"show_config エラー: {e}")
        await handle_error(interaction, e)

@client.tree.command(name="ping", description="Botが正常に動作しているかテストします。")
async def ping(interaction: discord.Interaction):
    try:
        await interaction.response.send_message("🏓 Pong! Renderで稼働中！", ephemeral=True)
        print(f"Pingコマンド実行: {interaction.user.name}")
    except Exception as e:
        print(f"ping エラー: {e}")
        await handle_error(interaction, e)

# イベントハンドラ
@client.event
async def on_ready():
    print(f'✅ {client.user} としてRenderでログインしました！')
    print(f'📊 参加サーバー数: {len(client.guilds)}')
    print('-' * 40)

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

        if message.channel.id == target_channel_id and keyword in message.content:
            role = message.guild.get_role(role_id)
            if role is None or role in message.author.roles: 
                return

            try:
                await message.author.add_roles(role)
                await send_log(message.guild, "✅ ロール付与成功", 
                             f"{message.author.mention} に **{role.name}** を付与しました。", 
                             discord.Color.green())
                
                await message.channel.send(
                    f"{message.author.mention} に **{role.name}** ロールを付与しました！", 
                    delete_after=10
                )
                print(f"✅ ロール付与: {message.author.name} -> {role.name}")
                
            except discord.Forbidden:
                await send_log(message.guild, "❌ ロール付与失敗", 
                             f"権限不足: {message.author.mention} -> {role.mention}", 
                             discord.Color.red())
                print(f"❌ ロール付与失敗: 権限不足")
            except Exception as e:
                print(f"❌ ロール付与エラー: {e}")
                
    except Exception as e:
        print(f"❌ メッセージ処理エラー: {e}")

# エラーハンドラ設定
@set_channel.error
@set_config.error
@set_log_channel.error
@show_config.error
@ping.error
async def on_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await handle_error(interaction, error)

# メイン実行
if __name__ == "__main__":
    # Keep-alive開始（重要！）
    keep_alive()
    
    # TOKEN確認
    if not TOKEN:
        print("❌ DISCORD_TOKENが設定されていません！")
        print("Render Dashboard > Environment Variables で設定してください")
        exit(1)
    
    print("🚀 Discord Bot を起動中...")
    print("🌐 Keep-alive server started")
    
    try:
        client.run(TOKEN)
    except Exception as e:
        print(f"❌ Bot起動エラー: {e}")
        import traceback
        traceback.print_exc()