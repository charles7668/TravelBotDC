import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta

class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reminders = []     # 存放 HH:MM 定時提醒
        self.schedules = []     # 存放日期提醒
        self.check_reminders.start()
        self.check_daily_schedules.start()

    def cog_unload(self):
        self.check_reminders.cancel()
        self.check_daily_schedules.cancel()

    # --- 原有的 HH:MM 定時提醒 ---
    @app_commands.command(name="remind", description="設定今日定時提醒 (HH:MM)")
    @app_commands.describe(reminder_time="格式 HH:MM (例如 14:30)", task="提醒內容")
    async def remind(self, interaction: discord.Interaction, reminder_time: str, task: str):
        try:
            datetime.strptime(reminder_time, "%H:%M")
            self.reminders.append({
                "time": reminder_time,
                "task": task,
                "user_id": interaction.user.id,
                "channel_id": interaction.channel_id
            })
            await interaction.response.send_message(f"✅ 今日定時提醒已設定：`{reminder_time}` - **{task}**")
        except ValueError:
            await interaction.response.send_message("❌ 格式錯誤！請使用 HH:MM (例如 14:30)", ephemeral=True)

    # --- 新增的日期倒數提醒 ---
    @app_commands.command(name="schedule", description="設定行程日期提醒 (提前 3 天與 1 天標註)")
    @app_commands.describe(date="目標日期 YYYY-MM-DD (例如 2024-12-31)", task="行程名稱")
    async def schedule(self, interaction: discord.Interaction, date: str, task: str):
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
            if target_date < datetime.now().date():
                await interaction.response.send_message("❌ 不能設定過去的日期喔！", ephemeral=True)
                return

            self.schedules.append({
                "date": target_date,
                "task": task,
                "user_id": interaction.user.id,
                "channel_id": interaction.channel_id,
                "notified_3d": False,
                "notified_1d": False
            })
            await interaction.response.send_message(f"📅 行程已排定：`{date}` - **{task}**\n(將在 3 天前與 1 天前早晨自動提醒)")
        except ValueError:
            await interaction.response.send_message("❌ 格式錯誤！請使用 YYYY-MM-DD (例如 2024-12-31)", ephemeral=True)

    # 每分鐘檢查一次 HH:MM 提醒
    @tasks.loop(minutes=1)
    async def check_reminders(self):
        if not self.reminders:
            return
        current_time = datetime.now().strftime("%H:%M")
        for r in self.reminders[:]:
            if r["time"] == current_time:
                channel = self.bot.get_channel(r["channel_id"])
                user = self.bot.get_user(r["user_id"])
                if channel:
                    mention = user.mention if user else "@everyone"
                    await channel.send(f"⏰ {mention} 定時提醒時間到：**{r['task']}**")
                self.reminders.remove(r)

    # 每天早上 9:00 檢查一次行程提醒 (暫定每小時檢查一次日期變化)
    @tasks.loop(hours=1)
    async def check_daily_schedules(self):
        today = datetime.now().date()
        for s in self.schedules[:]:
            target_date = s["date"]
            days_left = (target_date - today).days
            
            channel = self.bot.get_channel(s["channel_id"])
            user = self.bot.get_user(s["user_id"])
            if not channel: continue
            
            mention = user.mention if user else "@everyone"
            
            # 提前 3 天提醒
            if days_left == 3 and not s["notified_3d"]:
                await channel.send(f"🔔 {mention} 行程預告：**{s['task']}** 還有 **3 天** 就要到了！({target_date})")
                s["notified_3d"] = True
            
            # 提前 1 天提醒
            elif days_left == 1 and not s["notified_1d"]:
                await channel.send(f"⚠️ {mention} 行程強烈提醒：**{s['task']}** **就在明天**！({target_date})")
                s["notified_1d"] = True
            
            # 到期當天 (可選: 也可以移除此段)
            elif days_left == 0:
                await channel.send(f"🚩 {mention} 行程就是今天：**{s['task']}**！祝旅途愉快！")
                self.schedules.remove(s)
            
            # 移除過期行程
            elif days_left < 0:
                self.schedules.remove(s)

async def setup(bot):
    await bot.add_cog(Reminders(bot))
