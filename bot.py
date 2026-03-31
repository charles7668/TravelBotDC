import discord
from discord.ext import commands
import os
import asyncpg
from dotenv import load_dotenv

# 加載環境變數
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

class TravelBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.db_pool = None

    async def init_db(self):
        async with self.db_pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS trips (
                    name VARCHAR PRIMARY KEY,
                    start_date DATE,
                    end_date DATE,
                    creator BIGINT,
                    note TEXT
                );
                
                CREATE TABLE IF NOT EXISTS trip_members (
                    trip_name VARCHAR REFERENCES trips(name) ON DELETE CASCADE,
                    user_id BIGINT,
                    PRIMARY KEY (trip_name, user_id)
                );
                
                CREATE TABLE IF NOT EXISTS schedules (
                    id VARCHAR PRIMARY KEY,
                    datetime TIMESTAMP,
                    has_time BOOLEAN,
                    task VARCHAR,
                    trip_name VARCHAR,
                    location VARCHAR,
                    description TEXT,
                    user_id BIGINT,
                    channel_id BIGINT,
                    notified_3d BOOLEAN DEFAULT FALSE,
                    notified_1d BOOLEAN DEFAULT FALSE
                );
            ''')

    async def setup_hook(self):
        # 建立資料庫連線池
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            try:
                print("正在連接 PostgreSQL 資料庫...")
                self.db_pool = await asyncpg.create_pool(database_url)
                await self.init_db()
                print("✅ 資料庫連線與初始化成功！")
            except Exception as e:
                print(f"❌ 資料庫連線失敗: {e}")
        else:
            print("⚠️ 警告：找不到 DATABASE_URL，部分需要資料庫的功能將無法運作。")
            
        # 自動載入 cogs 資料夾內的所有 .py 檔案
        print("正在載入 Cogs...")
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                await self.load_extension(f'cogs.{filename[:-3]}')
                print(f'  - 已載入 {filename}')
        
        # 同步 Slash 指令
        print("正在同步 Slash 指令...")
        await self.tree.sync()
        print("所有指令同步完成！")

bot = TravelBot()

@bot.command()
@commands.is_owner()
async def sync(ctx):
    print("正在將指令強制同步到此伺服器...")
    # 將全域指令樹複製到當前伺服器中
    bot.tree.copy_global_to(guild=ctx.guild)
    # 同步該伺服器的指令樹
    synced = await bot.tree.sync(guild=ctx.guild)
    
    print(f"成功同步了 {len(synced)} 個指令至伺服器：{ctx.guild.name}")
    await ctx.send(f"✅ 指令已成功強制同步到此伺服器！(共 {len(synced)} 個)\n請按 `Ctrl + R` 或稍候片刻即可看到新指令。")

@bot.event
async def on_ready():
    print('---')
    print(f'目前登入身份：{bot.user}')
    print(f'Bot ID: {bot.user.id}')
    print('旅行機器人已準備就緒！')
    print('---')

if __name__ == '__main__':
    if TOKEN:
        bot.run(TOKEN)
    else:
        print('錯誤：找不到 DISCORD_TOKEN，請檢查 .env 檔案。')
