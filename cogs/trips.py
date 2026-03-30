import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, time

class TravelPlanner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.trips = {}
        self.schedules = []
        self.check_future_schedules.start()

    def cog_unload(self):
        self.check_future_schedules.cancel()

    # --- 自動完成建議邏輯 ---
    async def trip_autocomplete(self, interaction: discord.Interaction, current: str):
        u_id = interaction.user.id
        formal_trips = [t["name"] for t in self.trips.get(u_id, [])]
        active_tags = list(set(s["trip_name"] for s in self.schedules if s["user_id"] == u_id))
        all_options = list(set(formal_trips + active_tags))
        return [
            app_commands.Choice(name=t, value=t)
            for t in all_options if current.lower() in t.lower()
        ][:25]

    # --- 1. 建立計畫 ---
    @app_commands.command(name="create_trip", description="建立一個大型旅程 (例如: 日本行)")
    @app_commands.describe(name="旅程名稱", start_date="開始日期 YYYY-MM-DD", end_date="結束日期 YYYY-MM-DD")
    async def create_trip(self, interaction: discord.Interaction, name: str, start_date: str, end_date: str):
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
            if start > end:
                await interaction.response.send_message("❌ 開始日期不能晚於結束日期喔！", ephemeral=True); return
            
            u_id = interaction.user.id
            if u_id not in self.trips: self.trips[u_id] = []
            self.trips[u_id].append({"name": name, "start": start, "end": end})
            await interaction.response.send_message(f"🎒 **大型旅程已建立！**\n名稱：`{name}`\n日期：`{start_date}` 至 `{end_date}`")
        except ValueError:
            await interaction.response.send_message("❌ 格式錯誤！請使用 YYYY-MM-DD", ephemeral=True)

    # --- 2. 靈活行程 ---
    @app_commands.command(name="schedule", description="設定行程 (不填群組則自動歸到「未分組」)")
    @app_commands.describe(time_str="格式 YYYY-MM-DD [HH:MM]", task="項目名稱", trip_name="所屬大型旅程 (選填)")
    @app_commands.autocomplete(trip_name=trip_autocomplete)
    async def schedule(self, interaction: discord.Interaction, time_str: str, task: str, trip_name: str = None):
        try:
            try:
                target_dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M"); has_time = True
            except ValueError:
                target_dt = datetime.strptime(time_str, "%Y-%m-%d"); has_time = False

            if target_dt < datetime.now() and (has_time or target_dt.date() < datetime.now().date()):
                await interaction.response.send_message("❌ 不能設定過去的時間！", ephemeral=True); return

            final_trip_name = trip_name if trip_name else "未分組"
            self.schedules.append({
                "datetime": target_dt, "has_time": has_time, "task": task, "trip_name": final_trip_name,
                "user_id": interaction.user.id, "channel_id": interaction.channel_id,
                "notified_3d": False, "notified_1d": False
            })
            
            display_time = time_str if has_time else target_dt.date()
            await interaction.response.send_message(f"📅 行程已鎖定：`{display_time}` - **{task}** (歸編：`{final_trip_name}`)")
        except ValueError:
            await interaction.response.send_message("❌ 格式錯誤！請輸入 YYYY-MM-DD [HH:MM]。", ephemeral=True)

    # --- 3. 查詢列表 ---
    @app_commands.command(name="view_trip", description="檢視旅程或分組內容")
    @app_commands.describe(name="欲檢視內容的旅程名稱")
    @app_commands.autocomplete(name=trip_autocomplete)
    async def view_trip(self, interaction: discord.Interaction, name: str = "未分組"):
        u_id = interaction.user.id
        trip_info = next((t for t in self.trips.get(u_id, []) if t["name"] == name), None)
        related = sorted([s for s in self.schedules if s["user_id"] == u_id and s["trip_name"] == name], key=lambda x: x["datetime"])
        if not trip_info and not related:
            await interaction.response.send_message(f"❌ 找不到名為 `{name}` 的內容。", ephemeral=True); return
        
        embed = discord.Embed(title=f"🎒 旅程詳情：{name}", color=discord.Color.green())
        if trip_info: embed.description = f"📅 全程：{trip_info['start']} ~ {trip_info['end']}"
        lines = [f"🔹 `{s['datetime'].strftime('%m/%d %H:%M' if s['has_time'] else '%m/%d')}` - {s['task']}" for s in related]
        embed.add_field(name="子行程列表", value="\n".join(lines) if lines else "目前尚無詳細紀錄。", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="list_trips", description="列出目前所有的旅程計畫")
    async def list_trips(self, interaction: discord.Interaction):
        u_id = interaction.user.id
        ts = self.trips.get(u_id, [])
        active_tags = set(s["trip_name"] for s in self.schedules if s["user_id"] == u_id)
        if not ts and not active_tags:
            await interaction.response.send_message("無內容。", ephemeral=True); return

        embed = discord.Embed(title="✈️ 您的旅程總覽", color=discord.Color.blue())
        already_listed = set()
        for t in ts:
            embed.add_field(name=f"📌 {t['name']}", value=f"日期：`{t['start']}` 到 `{t['end']}`", inline=False)
            already_listed.add(t["name"])
        others = [f"`{o}`" for o in active_tags if o not in already_listed]
        if others: embed.add_field(name="📂 其他分組", value=", ".join(others), inline=False)
        await interaction.response.send_message(embed=embed)

    # --- 4. 每日倒數任務 (改為每日 00:00 執行一次) ---
    @tasks.loop(time=time(hour=0, minute=0))
    async def check_future_schedules(self):
        today = datetime.now().date()
        for s in self.schedules[:]:
            target_date = s["datetime"].date()
            days_left = (target_date - today).days
            
            # 自動清理昨日行程
            if days_left < 0:
                self.schedules.remove(s)
                continue

            chan = self.bot.get_channel(s["channel_id"])
            if not chan: continue
            usr = self.bot.get_user(s["user_id"])
            pf = f"【{s['trip_name']}】" if s['trip_name'] else ""
            mention = usr.mention if usr else ""

            # 每日 0 點後的倒數預報
            if days_left == 3:
                await chan.send(f"🔔 {mention} 預告：{pf} **{s['task']}** 還有 3 天就要到了！")
            elif days_left == 1:
                await chan.send(f"⚠️ {mention} 強調：{pf} **{s['task']}** 就在明天！")

async def setup(bot):
    await bot.add_cog(TravelPlanner(bot))
