import discord
from discord import app_commands
import os
import pymongo # ★ PostgreSQL(sqlalchemy)から変更
from keep_alive import keep_alive

# ===================================================================
# 環境変数の読み込み
# ===================================================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MONGO_URI = os.getenv("MONGO_URI") # ★ POSTGRES_URIから変更
# ===================================================================

# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
# MongoDB 接続ブロック
# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
mongo_client = None
db = None
if MONGO_URI:
    try:
        mongo_client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        mongo_client.server_info() # 接続をテスト
        db = mongo_client.get_database("discord_bot_db").get_collection("server_configs")
        print("✅ MongoDBに正常に接続しました。")
    except Exception as e:
        print(f"❌ MongoDB接続エラー: {e}")
else:
    print("❌ MONGO_URIが環境変数に設定されていません。")

# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
# DB操作関数 (MongoDB版)
# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
def get_config(server_id):
    if db is None: return {}
    # MongoDBではIDが文字列なので、変換は不要
    return db.find_one({"_id": server_id}) or {}

def update_config(server_id, new_values):
    if db is None: return None
    try:
        # update_oneは結果オブジェクトを返す
        result = db.update_one({"_id": server_id}, {"$set": new_values}, upsert=True)
        print(f"🔄 DB更新試行: server_id={server_id}, acknowledged={result.acknowledged}")
        return result
    except Exception as e:
        print(f"❌ update_configエラー: {e}")
        return None

# --- ログ送信機能 (変更なし) ---
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

# --- Discord Bot設定 (変更なし) ---
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

# --- コマンド定義 (DB操作部分のロジックを微調整) ---
@client.tree.command(name="set_channel", description="キーワードに反応するチャンネルを設定します。")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    # MongoDBではサーバーIDを文字列として扱う
    result = update_config(str(interaction.guild.id), {"channel_id": channel.id})
    if result and result.acknowledged:
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
    result = update_config(str(interaction.guild.id), {"keyword": keyword, "role_id": role.id})
    if result and result.acknowledged:
        await interaction.followup.send(f"✅ キーワードを「**{keyword}**」、ロールを **{role.mention}** に設定しました。", ephemeral=True)
    else:
        await interaction.followup.send("❌ データベースの更新に失敗しました。", ephemeral=True)

@client.tree.command(name="set_log_channel", description="ログを送信するチャンネルを設定します。")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_log_channel(interaction: discord.Interaction, log_channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    result = update_config(str(interaction.guild.id), {"log_channel_id": log_channel.id})
    if result and result.acknowledged:
        await interaction.followup.send(f"✅ ログを {log_channel.mention} に送信します。", ephemeral=True)
    else:
        await interaction.followup.send("❌ データベースの更新に失敗しました。", ephemeral=True)

# (check_roles, show_config, ping はPostgreSQL版とほぼ同じロジックで動作します)
# (以下、コードの完全性のために含めます)

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

# --- イベントハンドラ (変更なし) ---
@client.event
async def on_ready():
    print(f'✅ {client.user} としてログインしました！')

# 機能①：新規参加者へのウェルカムDM
@client.event
async def on_member_join(member):
    if member.bot:
        return
    print(f"🎉 新規参加: {member.name} がサーバー '{member.guild.name}' に参加しました。")
    welcome_message = (
        f"{member.mention}さん「Platoon Server」へようこそ。\n"
        "入隊希望の方は下記のコミュニティ規約を確認して頂き、 『確認しました』と <#1188077063899447333> へ書き込みをお願いします！\n"
        "原則botのみでの対応になります。その為『』の中の文言のみを打込みお願い致します。\n\n"
        "また、規約同意を頂けない場合はキック処理しますのでご了承下さい。\n"
        "https://docs.google.com/document/d/1vuwClxhsNRUrAhR0SoaL5RA73qzTI6kY/edit#heading=h.30j0zll"
    )
    try:
        await member.send(welcome_message)
        print(f"✅ {member.name} にウェルカムDMを送信しました。")
    except Exception as e:
        print(f"❌ ウェルカムDM送信中にエラー: {e}")

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
                    dm_message = (
                        "確認ありがとうございます。\n"
                        "現段階の次回新規入隊案内は ⁠<#1188077063899447334> をご覧下さい。\n"
                        "参加の可否にあっては送信しなくても大丈夫です。\n"
                        "今後の流れや講習内容にあっては ⁠<#1188077063899447334> こちらから閲覧できます。\n"
                        "また不明点・問題点があれば、⁠<#1259234807796207727> に書いてある内容を確認して下さい。"
                        "その他問題・不明部分があれば 「@教官」または「@事務」にメンションして下さい。"
                    )
                    try:
                        await message.author.send(dm_message)
                        print(f"✅ {message.author.name} さんへDMを送信しました。")
                    except discord.errors.Forbidden:
                        print(f"❌ {message.author.name} さんへのDM送信に失敗しました。DMが閉鎖されている可能性があります。")
                    except Exception as e:
                        print(f"❌ DM送信中に予期せぬエラー: {e}")
                
                except discord.errors.Forbidden:
                    print("エラー: ロールの付与権限がありません。")
                    await send_log(
                        guild=message.guild,
                        title="❌ ロール付与失敗",
                        description=f"原因: Botの権限不足です。\n「ロールの管理」権限を確認してください。",
                        color=discord.Color.red()
                    )
                except Exception as e:
                    print(f"ロール付与/通知処理中にエラー: {e}")
    except Exception as e:
        print(f"❌ on_message処理中に予期せぬエラーが発生: {e}")


# --- メイン実行 ---
keep_alive()
# ★ POSTGRES_URIからMONGO_URIに変更
if DISCORD_TOKEN and MONGO_URI:
    print("🚀 Discord Bot を起動中...")
    client.run(DISCORD_TOKEN)
else:
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKENが設定されていません。")
    if not MONGO_URI:
        print("❌ MONGO_URIが設定されていません。")
