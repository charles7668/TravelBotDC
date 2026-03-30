import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

# 加載環境變數
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

class TravelBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
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
