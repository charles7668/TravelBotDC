import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime

class Timers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reminders = []  # 存放當日速記提醒
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

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
            await interaction.response.send_message(f"✅ 今日定時提醒已設定： `{reminder_time}` - **{task}**")
        except ValueError:
            await interaction.response.send_message("❌ 格式錯誤！請使用 HH:MM (例如 14:30)", ephemeral=True)

    @tasks.loop(minutes=1)
    async def check_reminders(self):
        if not self.reminders: return
        now = datetime.now().strftime("%H:%M")
        for r in self.reminders[:]:
            if r["time"] == now:
                await self._send_simple(r)
                self.reminders.remove(r)

    async def _send_simple(self, r):
        chan = self.bot.get_channel(r["channel_id"])
        if chan:
            usr = self.bot.get_user(r["user_id"])
            mention = usr.mention if usr else ""
            await chan.send(f"⏰ {mention} 提醒：**{r['task']}**")

async def setup(bot):
    await bot.add_cog(Timers(bot))
