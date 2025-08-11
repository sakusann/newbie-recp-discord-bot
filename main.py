import discord
from discord import app_commands
import os
from sqlalchemy import create_engine, text, inspect, Table, Column, BigInteger, String, MetaData
from keep_alive import keep_alive

# ===================================================================
# 環境変数の読み込み
# ===================================================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
POSTGRES_URI = os.getenv("POSTGRES_URI")
# ===================================================================

# PostgreSQL 接続
engine = None
if POSTGRES_URI:
    try:
        engine = create_engine(POSTGRES_URI)
        with engine.connect() as connection:
            inspector = inspect(engine)
            if not inspector.has_table("server_configs"):
                meta = MetaData()
                Table(
                    "server_configs", meta,
                    Column('server_id', BigInteger, primary_key=True),
                    Column('channel_id', BigInteger),
                    Column('role_id', BigInteger),
                    Column('log_channel_id', BigInteger),
                    Column('keyword', String),
                )
                meta.create_all(engine)
                print("✅ テーブル 'server_configs' を新規作成しました。")
        print("✅ PostgreSQLに正常に接続しました。")
    except Exception as e:
        print(f"❌ PostgreSQL接続エラー: {e}")
else:
    print("❌ POSTGRES_URIが環境変数に設定されていません。")

# --- DB操作関数 ---
def get_config(server_id):
    if engine is None: return {}
    with engine.connect() as connection:
        result = connection.execute(text("SELECT * FROM server_configs WHERE server_id = :id"), {"id": int(server_id)})
        row = result.fetchone()
        return row._asdict() if row else {}

def update_config(server_id, new_values):
    if engine is None: return None
    try:
        with engine.connect() as connection:
            stmt = text("""
                INSERT INTO server_configs (server_id, {keys}) VALUES (:server_id, :{values})
                ON CONFLICT (server_id) DO UPDATE SET {update_stmt}
            """.format(
                keys=", ".join(new_values.keys()),
                values=", :".join(new_values.keys()),
                update_stmt=", ".join([f"{key} = EXCLUDED.{key}" for key in new_values.keys()])
            ))
            params = {"server_id": int(server_id), **new_values}
            result = connection.execute(stmt, params)
            connection.commit()
            print(f"🔄 DB更新試行: server_id={server_id}")
            return result
    except Exception as e:
        print(f"❌ update_configエラー: {e}")
        return None

# --- ログ送信機能 ---
async def send_log(guild, title, description, color):
    config = get_config(str(guild.id))
    log_channel_id = config.get("log_channel_id")
    if log_channel_id:
        log_channel = guild.get_channel(log_channel_id)
        if log_channel:
            try:
                embed = discord.Embed(title=title, description=description, color=color)
                await log_channel.send(embed=embed)
            except Exception as e:
                print(f"ログチャンネルへの送信に失敗しました: {e}")

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

# --- コマンド定義 ---
@client.tree.command(name="set_channel", description="キーワードに反応するチャンネルを設定します。")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    result = update_config(interaction.guild.id, {"channel_id": channel.id})
    if result:
        await interaction.followup.send(f"✅ 監視対象を {channel.mention} に設定しました。", ephemeral=True)
    else:
        await interaction.followup.send("❌ データベースの更新に失敗しました。", ephemeral=True)

@client.tree.command(name="set_config", description="キーワードと付与するロールを設定します。")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_config(interaction: discord.Interaction, keyword: str, role: discord.Role):
    await interaction.response.defer(ephemeral=True)
    if interaction.guild.me.top_role <= role:
        await interaction.followup.send(f"❌ Botのロールを {role.mention} より上位に配置してください。", ephemeral=True)
        return
    result = update_config(interaction.guild.id, {"keyword": keyword, "role_id": role.id})
    if result:
        await interaction.followup.send(f"✅ キーワードを「**{keyword}**」、ロールを **{role.mention}** に設定しました。", ephemeral=True)
    else:
        await interaction.followup.send("❌ データベースの更新に失敗しました。", ephemeral=True)

@client.tree.command(name="set_log_channel", description="ログを送信するチャンネルを設定します。")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_log_channel(interaction: discord.Interaction, log_channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    result = update_config(interaction.guild.id, {"log_channel_id": log_channel.id})
    if result:
        await interaction.followup.send(f"✅ ログを {log_channel.mention} に送信します。", ephemeral=True)
    else:
        await interaction.followup.send("❌ データベースの更新に失敗しました。", ephemeral=True)

@client.tree.command(name="check_roles", description="Botのロール階層と権限を診断します。")
@app_commands.checks.has_permissions(manage_guild=True)
async def check_roles(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    bot_member = interaction.guild.me
    permissions = bot_member.guild_permissions
    embed = discord.Embed(title="🔍 Bot権限・階層診断", color=discord.Color.orange())
    embed.add_field(name="Botの最上位ロール", value=f"{bot_member.top_role.mention} (位置: {bot_member.top_role.position})", inline=False)
    embed.add_field(name="必要な権限", value=(f"ロールの管理: {'✅' if permissions.manage_roles else '❌'}\n" f"メッセージの管理: {'✅' if permissions.manage_messages else '❌'}\n" f"メッセージの送信: {'✅' if permissions.send_messages else '❌'}"), inline=False)
    embed.set_footer(text="ロールを付与するには、Botのロールが付与対象ロールより上位にある必要があります。")
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
    await interaction.response.send_message(f"🏓 Pong! `{client.latency * 1000:.2f}ms`")

# --- イベントハンドラ ---
@client.event
async def on_ready():
    print(f'✅ {client.user} としてログインしました！')

@client.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return
    try:
        config = get_config(str(message.guild.id))
        target_channel_id = config.get("channel_id")
        keyword = config.get("keyword")
        role_id = config.get("role_id")
        if not all([target_channel_id, keyword, role_id]):
            return
        if message.channel.id == target_channel_id and message.content == keyword:
            role = message.guild.get_role(role_id)
            if role and role not in message.author.roles:
                try:
                    await message.author.add_roles(role)
                    print(f"🎉 成功: {message.author} に '{role.name}' ロールを付与しました。")
                    await send_log(
                        guild=message.guild,
                        title="✅ ロール付与成功",
                        description=f"ユーザー: {message.author.mention}\nロール: {role.mention}",
                        color=discord.Color.green()
                    )
                    
                    await message.channel.send(f"{message.author.mention} さんに **{role.name}** ロールを付与しました！", delete_after=10)
                except discord.errors.Forbidden:
                    print("エラー: ロールの付与またはメッセージの削除権限がありません。")
                    await send_log(
                        guild=message.guild,
                        title="❌ ロール付与失敗",
                        description=f"原因: Botの権限不足です。\n「ロールの管理」と「メッセージの管理」権限を確認してください。",
                        color=discord.Color.red()
                    )
                except Exception as e:
                    print(f"ロール付与/通知処理中にエラー: {e}")
    except Exception as e:
        print(f"❌ on_message処理中に予期せぬエラーが発生: {e}")

# --- メイン実行 ---
keep_alive()
if DISCORD_TOKEN and POSTGRES_URI:
    print("🚀 Discord Bot を起動中...")
    client.run(DISCORD_TOKEN)
else:
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKENが設定されていません。")
    if not POSTGRES_URI:
        print("❌ POSTGRES_URIが設定されていません。")
