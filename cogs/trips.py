import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, time

class TravelPlanner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 結構： [ {"name": str, "start": date, "end": date, "creator": int, "members": [int, ...]} ]
        self.all_trips = [] 
        self.schedules = [] # 具體行程紀錄
        self.check_future_schedules.start()

    def cog_unload(self):
        self.check_future_schedules.cancel()

    # --- 自動完成建議：列出所有可加入的旅程 ---
    async def trip_autocomplete(self, interaction: discord.Interaction, current: str):
        # 獲取所有目前存在的旅程名稱 (不分使用者)
        options = list(set(t["name"] for t in self.all_trips))
        # 加上行程中出現過但未正式建立的名稱
        tag_options = list(set(s["trip_name"] for s in self.schedules if s["trip_name"] != "未分組"))
        
        final_options = list(set(options + tag_options))
        return [app_commands.Choice(name=t, value=t) for t in final_options if current.lower() in t.lower()][:25]

    # --- 1. 建立計畫 ---
    @app_commands.command(name="create_trip", description="建立一個新的大型旅程")
    async def create_trip(self, interaction: discord.Interaction, name: str, start_date: str, end_date: str):
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
            u_id = interaction.user.id
            
            # 建立旅程並預設建立者為成員
            self.all_trips.append({
                "name": name, "start": start, "end": end, 
                "creator": u_id, "members": [u_id]
            })
            await interaction.response.send_message(f"🎒 **大型旅程已建立！**\n名稱：`{name}`\n建立者：{interaction.user.mention}")
        except ValueError:
            await interaction.response.send_message("❌ 格式錯誤！YYYY-MM-DD", ephemeral=True)

    # --- 2. 加入計畫 (核心新功能) ---
    @app_commands.command(name="join_trip", description="加入現有的旅程計畫，共同接收提醒")
    @app_commands.autocomplete(name=trip_autocomplete)
    async def join_trip(self, interaction: discord.Interaction, name: str):
        u_id = interaction.user.id
        
        # 尋找該旅程
        trip = next((t for t in self.all_trips if t["name"] == name), None)
        if not trip:
            # 如果不存在，可能是有人先用了 schedule 標籤，我們幫忙補建一個空旅程
            trip = {"name": name, "start": None, "end": None, "creator": None, "members": []}
            self.all_trips.append(trip)
            
        if u_id in trip["members"]:
            await interaction.response.send_message(f"ℹ️ 您已經在 `{name}` 的成員名單中囉！", ephemeral=True); return
            
        trip["members"].append(u_id)
        await interaction.response.send_message(f"✨ {interaction.user.mention} 成功加入了旅程：**{name}**！\n您將會收到相關項目的倒數與天氣提醒。")

    # --- 3. 設定行程 ---
    @app_commands.command(name="schedule", description="排定行程 (同組行程會標記所有加入者)")
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
                await interaction.followup.send("❌ 過去時間！"); return

            final_t_name = trip_name if trip_name else "未分組"
            self.schedules.append({
                "datetime": dt, "has_time": has_time, "task": task, "trip_name": final_t_name,
                "location": location,
                "user_id": interaction.user.id, "channel_id": interaction.channel_id,
                "notified_3d": False, "notified_1d": False
            })
            
            # 即時天氣回報
            is_today = dt.date() == now.date()
            weather_str = ""
            if is_today and location:
                wc = self.bot.get_cog("Weather")
                if wc:
                    info = await wc.get_weather_info(location)
                    if info: weather_str = f" | 🌡️ **即時天氣：{info['condition']} {info['temp']}°C**"

            await interaction.followup.send(f"📅 已鎖定：`{time_str}` - **{task}** (分組：`{final_t_name}`){weather_str}")
        except ValueError:
            await interaction.followup.send("❌ 格式錯誤！")

    # --- 檢視介面優化 ---
    @app_commands.command(name="view_trip", description="檢視旅程成員與細節")
    @app_commands.autocomplete(name=trip_autocomplete)
    async def view_trip(self, interaction: discord.Interaction, name: str = "未分組"):
        trip = next((t for t in self.all_trips if t["name"] == name), None)
        related = sorted([s for s in self.schedules if s["trip_name"] == name], key=lambda x: x["datetime"])
        if not trip and not related:
            await interaction.response.send_message(f"❌ 查無專案 `{name}`。", ephemeral=True); return
            
        embed = discord.Embed(title=f"🎒 旅程詳情：{name}", color=discord.Color.green())
        if trip and trip["members"]:
            member_mentions = ", ".join([f"<@{uid}>" for uid in trip["members"]])
            embed.add_field(name="👥 此團成員", value=member_mentions, inline=False)
            
        lines = [f"🔹 `{s['datetime'].strftime('%m/%d %H:%M' if s['has_time'] else '%m/%d')}` - {s['task']}{' @ ' + s['location'] if s['location'] else ''}" for s in related]
        embed.add_field(name="內容清單", value="\n".join(lines) if lines else "無內容。", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="list_trips", description="列出所有可追蹤的旅程")
    async def list_trips(self, interaction: discord.Interaction):
        if not self.all_trips and not self.schedules:
            await interaction.response.send_message("無內容。", ephemeral=True); return
        embed = discord.Embed(title="✈️ 全域旅程總覽", color=discord.Color.blue())
        for t in self.all_trips:
            period = f"`{t['start']}` 到 `{t['end']}`" if t["start"] else "日期未定"
            embed.add_field(name=f"📌 {t['name']}", value=f"📅 {period}\n👥 成員：{len(t['members'])} 人", inline=False)
        await interaction.response.send_message(embed=embed)

    # --- 關鍵修正：提醒時自動標記所有人 ---
    @tasks.loop(time=time(hour=0, minute=0))
    async def check_future_schedules(self):
        today = datetime.now().date()
        wc = self.bot.get_cog("Weather")
        
        for s in self.schedules[:]:
            target_date = s["datetime"].date()
            days_left = (target_date - today).days
            chan = self.bot.get_channel(s["channel_id"])
            if not chan: continue

            # 獲取標記名單：行程建立者 + 該旅程的所有成員
            trip = next((t for t in self.all_trips if t["name"] == s["trip_name"]), None)
            mentions = set([s["user_id"]])
            if trip: mentions.update(trip["members"])
            mention_str = " ".join([f"<@{uid}>" for uid in mentions])

            pf = f"【{s['trip_name']}】" if s['trip_name'] else ""

            if days_left == 0:
                weather_str = ""
                if s["location"] and wc:
                    info = await wc.get_weather_info(s["location"])
                    if info: weather_str = f" | 📍 測報：{info['condition']} {info['temp']}°C"
                await chan.send(f"🚩 {mention_str} 今日行程：{pf} **{s['task']}**{weather_str}")
                self.schedules.remove(s); continue
            elif days_left < 0:
                self.schedules.remove(s); continue

            if days_left == 3:
                await chan.send(f"🔔 {mention_str} 預告：{pf} **{s['task']}** 還有 3 天！")
            elif days_left == 1:
                await chan.send(f"⚠️ {mention_str} 強調：{pf} **{s['task']}** 就在明天！")

async def setup(bot):
    await bot.add_cog(TravelPlanner(bot))
