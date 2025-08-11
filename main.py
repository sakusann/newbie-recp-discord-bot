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
    if engine is None: return
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
        connection.execute(stmt, params)
        connection.commit()

# --- ログ送信機能 ---
async def send_log(guild, title, description, color):
    # この関数はDBから設定を読み取るだけなので、deferは不要
    config = get_config(str(guild.id))
    log_channel_id = config.get("log_channel_id")
    if log_channel_id:
        log_channel = guild.get_channel(log_channel_id)
        if log_channel:
            try:
                embed = discord.Embed(title=title, description=description, color=color)
                await log_channel.send(embed=embed)
            except Exception as e:
                print(f"ログチャンネルへの送信に失敗しました: {e}")```

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

client = MyClient(intents=intents)

# --- コマンド定義（最終版） ---
async def handle_command_logic(interaction: discord.Interaction, logic_func, success_message):
    """コマンドの共通処理をまとめるヘルパー関数"""
    try:
        # まず応答を試みる
        await interaction.response.defer(ephemeral=True)
        # DB操作などのロジックを実行
        logic_func()
        # 成功メッセージを送信
        await interaction.followup.send(success_message, ephemeral=True)
    except discord.errors.NotFound as e:
        # Interactionのタイムアウトを検知した場合
        if e.code == 10062:
            print(f"インタラクションのタイムアウトを検知。バックグラウンドで処理を試みます。")
            # 応答はできないが、DB操作は実行する
            try:
                logic_func()
            except Exception as logic_e:
                print(f"バックグラウンド処理中にエラー: {logic_e}")
        else:
            print(f"予期せぬNotFoundエラー: {e}")
    except Exception as e:
        print(f"コマンド処理中に予期せぬエラー: {e}")
        try:
            # 万が一のエラーでもユーザーに通知
            await interaction.followup.send("❌ 不明なエラーが発生しました。", ephemeral=True)
        except Exception:
            pass # 通知すらできない場合は諦める

@client.tree.command(name="set_channel", description="キーワードに反応するチャンネルを設定します。")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    logic = lambda: update_config(interaction.guild.id, {"channel_id": channel.id})
    message = f"✅ 監視対象を {channel.mention} に設定しました。"
    await handle_command_logic(interaction, logic, message)

@client.tree.command(name="set_config", description="キーワードと付与するロールを設定します。")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_config(interaction: discord.Interaction, keyword: str, role: discord.Role):
    # このコマンドはロール階層チェックが先に入るので、ヘルパーは使わない
    try:
        await interaction.response.defer(ephemeral=True)
        if interaction.guild.me.top_role <= role:
            await interaction.followup.send(f"❌ Botのロールを {role.mention} より上位に配置してください。", ephemeral=True)
            return
        update_config(interaction.guild.id, {"keyword": keyword, "role_id": role.id})
        await interaction.followup.send(f"✅ キーワードを「**{keyword}**」、ロールを **{role.mention}** に設定しました。", ephemeral=True)
    except discord.errors.NotFound as e:
        if e.code == 10062:
            print("インタラクションタイムアウトを検知（set_config）。バックグラウンドで処理します。")
            if interaction.guild.me.top_role > role:
                update_config(interaction.guild.id, {"keyword": keyword, "role_id": role.id})
        else:
            print(f"予期せぬNotFoundエラー(set_config): {e}")


@client.tree.command(name="set_log_channel", description="ログを送信するチャンネルを設定します。")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_log_channel(interaction: discord.Interaction, log_channel: discord.TextChannel):
    logic = lambda: update_config(interaction.guild.id, {"log_channel_id": log_channel.id})
    message = f"✅ ログを {log_channel.mention} に送信します。"
    await handle_command_logic(interaction, logic, message)

@client.tree.command(name="check_roles", description="Botのロール階層と権限を診断します。")
@app_commands.checks.has_permissions(manage_guild=True)
async def check_roles(interaction: discord.Interaction):
    try:
        await interaction.response.defer(ephemeral=True)
        bot_member = interaction.guild.me
        permissions = bot_member.guild_permissions
        
        embed = discord.Embed(title="🔍 Bot権限・階層診断", color=discord.Color.orange())
        embed.add_field(
            name="Botの最上位ロール", 
            value=f"{bot_member.top_role.mention} (サーバー内での位置: {bot_member.top_role.position})", 
            inline=False
        )
        embed.add_field(
            name="必要な権限のチェック",
            value=(f"ロールの管理: {'✅' if permissions.manage_roles else '❌'}\n"
                   f"メッセージの管理: {'✅' if permissions.manage_messages else '❌'}\n"
                   f"メッセージの送信: {'✅' if permissions.send_messages else '❌'}"),
            inline=False
        )
        embed.set_footer(text="ロールを付与するには、Botのロールが付与対象ロールより上位にある必要があります。")
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except discord.errors.NotFound:
        print("check_roles タイムアウト") # タイムアウトしても特に何もしない

@client.tree.command(name="ping", description="Botの動作と応答速度をテストします。")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! `{client.latency * 1000:.2f}ms`")

# --- イベントハンドラ ---
@client.event
async def on_ready():
    print(f'✅ {client.user} としてログインしました！')

@client.event
async def on_message(message):
    # Bot自身のメッセージやDMは無視
    if message.author.bot or not message.guild:
        return

    try:
        # DBからこのサーバーの設定を取得
        config = get_config(str(message.guild.id))
        
        # 必要な設定値が揃っているか確認
        target_channel_id = config.get("channel_id")
        keyword = config.get("keyword")
        role_id = config.get("role_id")

        if not all([target_channel_id, keyword, role_id]):
            return

        # 指定されたチャンネルで、キーワードが完全に一致する場合にのみ反応
        if message.channel.id == target_channel_id and message.content == keyword:
            role = message.guild.get_role(role_id)
            
            # ロールが存在し、ユーザーがまだ持っていない場合
            if role and role not in message.author.roles:
                
               
        　　# ロールを付与
            try:
                await message.author.add_roles(role)
                print(f"🎉 成功: {message.author} に '{role.name}' ロールを付与しました！")

                # ★★★ ログ送信機能をここで呼び出す ★★★
                await send_log(
                    guild=message.guild,
                    title="✅ ロール付与成功",
                    description=f"ユーザー: {message.author.mention}\nロール: {role.mention}",
                    color=discord.Color.green()
                )

                # ユーザーへの通知                
                await message.channel.send(f"{message.author.mention} さんに **{role.name}** ロールを付与しました！", delete_after=10)

            except discord.errors.Forbidden:
                # Botに必要な権限が不足している場合
                print("エラー: ロールの付与またはメッセージの削除権限がありません。")
                await send_log(
                    guild=message.guild,
                    title="❌ ロール付与失敗",
                    description=f"原因: Botの権限不足です。\n"
                                f"「ロールの管理」と「メッセージの管理」権限を確認してください。",
                    color=discord.Color.red()
                )
            except Exception as e:
                print(f"ロール付与/通知処理中にエラー: {e}")```

    except Exception as e:
        print(f"❌ on_message処理中に予期せぬエラーが発生: {e}")


# --- メイン実行 ---
keep_alive()
if DISCORD_TOKEN and POSTGRES_URI:
    print("🚀 Discord Bot を起動中...")
    client.run(DISCORD_TOKEN)
