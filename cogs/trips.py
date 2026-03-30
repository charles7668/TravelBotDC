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

    async def trip_autocomplete(self, interaction: discord.Interaction, current: str):
        u_id = interaction.user.id
        formal = [t["name"] for t in self.trips.get(u_id, [])]
        tags = list(set(s["trip_name"] for s in self.schedules if s["user_id"] == u_id))
        all_options = list(set(formal + tags))
        return [app_commands.Choice(name=t, value=t) for t in all_options if current.lower() in t.lower()][:25]

    # --- 1. 建立計畫 ---
    @app_commands.command(name="create_trip", description="建立大型旅程")
    @app_commands.describe(name="旅程名稱", start_date="開始日期 YYYY-MM-DD", end_date="結束日期 YYYY-MM-DD")
    async def create_trip(self, interaction: discord.Interaction, name: str, start_date: str, end_date: str):
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
            u_id = interaction.user.id
            if u_id not in self.trips: self.trips[u_id] = []
            self.trips[u_id].append({"name": name, "start": start, "end": end})
            await interaction.response.send_message(f"🎒 **大型旅程已建立！**\n名稱：`{name}`\n日期：`{start_date}` 至 `{end_date}`")
        except ValueError:
            await interaction.response.send_message("❌ 格式錯誤！請使用 YYYY-MM-DD", ephemeral=True)

    # --- 2. 行程設定 (顯示加載狀態) ---
    @app_commands.command(name="schedule", description="排定行程 (自動測候狀況)")
    @app_commands.describe(time_str="格式 YYYY-MM-DD [HH:MM]", task="項目名稱", trip_name="所屬群組或名稱", location="目標城市/地點 (選填)")
    @app_commands.autocomplete(trip_name=trip_autocomplete)
    async def schedule(self, interaction: discord.Interaction, time_str: str, task: str, trip_name: str = None, location: str = None):
        await interaction.response.defer()
        try:
            try:
                dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M"); has_time = True
            except ValueError:
                dt = datetime.strptime(time_str, "%Y-%m-%d"); has_time = False

            now = datetime.now()
            if dt < now and (has_time or dt.date() < now.date()):
                await interaction.followup.send("❌ 不能設定過去的時間！"); return

            final_t_name = trip_name if trip_name else "未分組"
            self.schedules.append({
                "datetime": dt, "has_time": has_time, "task": task, "trip_name": final_t_name,
                "location": location,
                "user_id": interaction.user.id, "channel_id": interaction.channel_id,
                "notified_3d": False, "notified_1d": False
            })
            
            # --- 即時天氣與狀況顯示 ---
            is_today = dt.date() == now.date()
            weather_str = ""
            if is_today and location:
                weather_cog = self.bot.get_cog("Weather")
                if weather_cog:
                    info = await weather_cog.get_weather_info(location)
                    if info:
                        weather_str = f" | 🌡️ **即時天氣：{info['condition']} {info['temp']}°C**"

            msg = f"📅 已鎖定：`{time_str}` - **{task}** (群組：`{final_t_name}`)"
            if location: msg += f" | 📍 地點：`{location}`"
            await interaction.followup.send(msg + weather_str)
        except ValueError:
            await interaction.followup.send("❌ 格式錯誤！請錄入 YYYY-MM-DD [HH:MM] 格式。")

    # --- 3. 檢視列表 ---
    @app_commands.command(name="view_trip", description="檢視旅程細節")
    @app_commands.autocomplete(name=trip_autocomplete)
    async def view_trip(self, interaction: discord.Interaction, name: str = "未分組"):
        u_id = interaction.user.id
        trip_info = next((t for t in self.trips.get(u_id, []) if t["name"] == name), None)
        related = sorted([s for s in self.schedules if s["user_id"] == u_id and s["trip_name"] == name], key=lambda x: x["datetime"])
        if not trip_info and not related:
            await interaction.response.send_message(f"❌ 查無專案 `{name}`。", ephemeral=True); return
        embed = discord.Embed(title=f"🎒 旅程詳情：{name}", color=discord.Color.green())
        lines = [f"🔹 `{s['datetime'].strftime('%m/%d %H:%M' if s['has_time'] else '%m/%d')}` - {s['task']}{' @ ' + s['location'] if s['location'] else ''}" for s in related]
        embed.add_field(name="內容清單", value="\n".join(lines) if lines else "目前尚無詳細紀錄。", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="list_trips", description="列出計畫總覽")
    async def list_trips(self, interaction: discord.Interaction):
        u_id = interaction.user.id
        ts = self.trips.get(u_id, [])
        tags = set(s["trip_name"] for s in self.schedules if s["user_id"] == u_id)
        if not ts and not tags: await interaction.response.send_message("目前無內容。", ephemeral=True); return
        embed = discord.Embed(title="✈️ 您的旅程總覽", color=discord.Color.blue())
        listed = {t["name"] for t in ts}
        for t in ts: embed.add_field(name=f"📌 {t['name']}", value=f"日期：`{t['start']}` 到 `{t['end']}`", inline=False)
        others = [f"`{o}`" for o in tags if o not in listed]
        if others: embed.add_field(name="📂 其他分組", value=", ".join(others), inline=False)
        await interaction.response.send_message(embed=embed)

    # --- 4. 每日倒數與氣象預報 ---
    @tasks.loop(time=time(hour=0, minute=0))
    async def check_future_schedules(self):
        today = datetime.now().date()
        weather_cog = self.bot.get_cog("Weather")
        
        for s in self.schedules[:]:
            target_date = s["datetime"].date()
            days_left = (target_date - today).days
            chan = self.bot.get_channel(s["channel_id"])
            if not chan: continue
            usr = self.bot.get_user(s["user_id"])
            pf = f"【{s['trip_name']}】" if s['trip_name'] else ""
            mention = usr.mention if usr else ""

            if days_left == 0:
                # 當日行程發布 (結合完整氣象)
                weather_str = ""
                if s["location"] and weather_cog:
                    info = await weather_cog.get_weather_info(s["location"])
                    if info: weather_str = f" | 📍 測報：{info['condition']} {info['temp']}°C"
                await chan.send(f"🚩 {mention} 今日行程：{pf} **{s['task']}**{weather_str}")
                self.schedules.remove(s)
                continue
            elif days_left < 0:
                self.schedules.remove(s); continue

            if days_left == 3:
                await chan.send(f"🔔 {mention} 預告：{pf} **{s['task']}** 還有 3 天！")
            elif days_left == 1:
                await chan.send(f"⚠️ {mention} 強調：{pf} **{s['task']}** 就在明天！")

async def setup(bot):
    await bot.add_cog(TravelPlanner(bot))
