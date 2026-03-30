import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, time

class TravelPlanner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.all_trips = [] 
        self.schedules = [] 
        self.check_future_schedules.start()

    def cog_unload(self):
        self.check_future_schedules.cancel()

    # --- 智慧建議邏輯 ---
    async def trip_autocomplete(self, interaction: discord.Interaction, current: str):
        u_id = interaction.user.id
        # 正式建立的旅程名稱
        formal = [t["name"] for t in self.all_trips]
        # 常規選項強制加入「未分組」
        all_options = list(set(formal) | {"未分組"})
        return [
            app_commands.Choice(name=t, value=t)
            for t in all_options if current.lower() in t.lower()
        ][:25]

    async def schedule_autocomplete(self, interaction: discord.Interaction, current: str):
        u_id = interaction.user.id
        options = [
            f"{s['trip_name']} | {s['task']}" 
            for s in self.schedules if s["user_id"] == u_id
        ]
        return [
            app_commands.Choice(name=s, value=s)
            for s in options if current.lower() in s.lower()
        ][:25]

    # --- 1. 旅程管理指令 ---
    @app_commands.command(name="create_trip", description="建立大型旅程項目")
    async def create_trip(self, interaction: discord.Interaction, name: str, start_date: str, end_date: str):
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
            u_id = interaction.user.id
            self.all_trips.append({"name": name, "start": start, "end": end, "creator": u_id, "members": [u_id]})
            await interaction.response.send_message(f"🎒 **大型旅程已建立！**\n名稱：`{name}`")
        except ValueError:
            await interaction.response.send_message("❌ 格式錯誤！請使用 YYYY-MM-DD", ephemeral=True)

    @app_commands.command(name="join_trip", description="加入現有的旅程計畫")
    @app_commands.autocomplete(name=trip_autocomplete)
    async def join_trip(self, interaction: discord.Interaction, name: str):
        u_id = interaction.user.id
        trip = next((t for t in self.all_trips if t["name"] == name), None)
        if not trip:
            trip = {"name": name, "start": None, "end": None, "creator": None, "members": []}
            self.all_trips.append(trip)
        
        if u_id not in trip["members"]:
            trip["members"].append(u_id)
            await interaction.response.send_message(f"✨ 成功加入了旅程：**{name}**！")
        else:
            await interaction.response.send_message("ℹ️ 您已經在成員名單中囉。", ephemeral=True)

    # --- 2. 行程設定指令 ---
    @app_commands.command(name="schedule", description="排定行程並加入詳細描述")
    @app_commands.describe(time_str="YYYY-MM-DD [HH:MM]", task="任務名稱", trip_name="群組", location="地點", description="詳細描述")
    @app_commands.autocomplete(trip_name=trip_autocomplete)
    async def schedule(self, interaction: discord.Interaction, time_str: str, task: str, trip_name: str = None, location: str = None, description: str = None):
        await interaction.response.defer()
        try:
            target_dt, has_time = self._parse_datetime(time_str)
            if not target_dt:
                await interaction.followup.send("❌ 格式錯誤！請使用 YYYY-MM-DD [HH:MM]。")
                return

            if target_dt < datetime.now() and (has_time or target_dt.date() < datetime.now().date()):
                await interaction.followup.send("❌ 不能設定過去的時間！")
                return

            final_t_name = trip_name if trip_name else "未分組"
            self.schedules.append({
                "datetime": target_dt, "has_time": has_time, "task": task, "trip_name": final_t_name,
                "location": location, "description": description,
                "user_id": interaction.user.id, "channel_id": interaction.channel_id,
                "notified_3d": False, "notified_1d": False
            })
            
            w_str = await self._get_instant_weather(target_dt, location)
            await interaction.followup.send(f"📅 已鎖定：`{time_str}` - **{task}** (分組：`{final_t_name}`){w_str}")
        except Exception as e:
            print(f"Schedule Error: {e}")
            await interaction.followup.send("❌ 發生錯誤，請聯絡管理員。")

    def _parse_datetime(self, time_str):
        try:
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M"), True
        except ValueError:
            try:
                return datetime.strptime(time_str, "%Y-%m-%d"), False
            except ValueError:
                return None, False

    async def _get_instant_weather(self, target_dt, location):
        if target_dt.date() == datetime.now().date() and location:
            wc = self.bot.get_cog("Weather")
            if wc:
                info = await wc.get_weather_info(location)
                if info:
                    return f" | 🌡️ **即時天氣：{info['condition']} {info['temp']}°C**"
        return ""

    # --- 3. 檢視與編輯指令 ---
    @app_commands.command(name="edit_schedule", description="編輯行程詳細資料")
    @app_commands.autocomplete(full_task_name=schedule_autocomplete)
    async def edit_schedule(self, interaction: discord.Interaction, full_task_name: str, new_task: str = None, new_description: str = None, new_location: str = None):
        try:
            t_name, task_name = [x.strip() for x in full_task_name.split("|")]
            u_id = interaction.user.id
            target = next((s for s in self.schedules if s["user_id"] == u_id and s["trip_name"] == t_name and s["task"] == task_name), None)
            
            if not target:
                await interaction.response.send_message("❌ 找不到該筆行程。", ephemeral=True)
                return

            if new_task: target["task"] = new_task
            if new_description: target["description"] = new_description
            if new_location: target["location"] = new_location
            await interaction.response.send_message(f"✅ 行程 `{task_name}` 已更新！")
        except Exception:
            await interaction.response.send_message("❌ 編輯失敗。", ephemeral=True)

    @app_commands.command(name="view_details", description="查詢行程筆記")
    @app_commands.autocomplete(full_task_name=schedule_autocomplete)
    async def view_details(self, interaction: discord.Interaction, full_task_name: str):
        try:
            t_name, task_name = [x.strip() for x in full_task_name.split("|")]
            s = next((s for s in self.schedules if s["trip_name"] == t_name and s["task"] == task_name), None)
            
            if not s:
                await interaction.response.send_message("❌ 找不到細節內容。", ephemeral=True)
                return

            embed = discord.Embed(title=f"📝 行程筆記：{s['task']}", color=discord.Color.orange())
            embed.add_field(name="所屬旅程", value=s["trip_name"], inline=True)
            t_fmt = '%Y-%m-%d %H:%M' if s['has_time'] else '%Y-%m-%d'
            embed.add_field(name="時間點", value=s["datetime"].strftime(t_fmt), inline=True)
            if s["location"]:
                embed.add_field(name="地點", value=s["location"], inline=True)
            
            desc = s["description"] if s["description"] else "目前無備註。"
            embed.add_field(name="📜 詳細描述", value=f"```\n{desc}\n```", inline=False)
            await interaction.response.send_message(embed=embed)
        except Exception:
            await interaction.response.send_message("❌ 查詢錯誤。", ephemeral=True)

    @app_commands.command(name="view_trip", description="一覽旅程內容")
    @app_commands.autocomplete(name=trip_autocomplete)
    async def view_trip(self, interaction: discord.Interaction, name: str = "未分組"):
        trip = next((t for t in self.all_trips if t["name"] == name), None)
        related = sorted([s for s in self.schedules if s["trip_name"] == name], key=lambda x: x["datetime"])
        
        if not trip and not related:
            await interaction.response.send_message(f"❌ 查無 `{name}`。", ephemeral=True)
            return

        embed = discord.Embed(title=f"🎒 詳情：{name}", color=discord.Color.green())
        if trip and trip["members"]:
            m_list = ", ".join([f"<@{uid}>" for uid in trip["members"]])
            embed.add_field(name="👥 成員", value=m_list, inline=False)
            
        lines = [f"🔹 `{s['datetime'].strftime('%m/%d %H:%M' if s['has_time'] else '%m/%d')}` - {s['task']}{' @ ' + s['location'] if s['location'] else ''}" for s in related]
        embed.add_field(name="計畫表", value="\n".join(lines) if lines else "無內容。", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="list_trips", description="列出計畫總覽 (正式計畫與未分組)")
    async def list_trips(self, interaction: discord.Interaction):
        u_id = interaction.user.id
        if not self.all_trips and not self.schedules:
            await interaction.response.send_message("目前無任何資料。", ephemeral=True)
            return

        embed = discord.Embed(title="✈️ 您的旅程報表", color=discord.Color.blue())
        
        # 1. 列出正式建立的旅程
        formal_count = 0
        for t in self.all_trips:
            period = f"`{t['start']}` 到 `{t['end']}`" if t["start"] else "日期未定"
            embed.add_field(name=f"📌 {t['name']}", value=f"📅 {period}\n👥 {len(t['members'])} 人", inline=False)
            formal_count += 1
        
        # 2. 檢測是否有未歸類的行程
        has_uncat = any(s["trip_name"] == "未分組" and s["user_id"] == u_id for s in self.schedules)
        if has_uncat:
            embed.add_field(name="📂 基礎行程", value="`未分組`", inline=False)
        elif formal_count == 0:
            await interaction.response.send_message("目前無有效的旅程項目可列出。", ephemeral=True)
            return

        await interaction.response.send_message(embed=embed)

    # --- 4. 背景服務 ---
    @tasks.loop(time=time(hour=0, minute=0))
    async def check_future_schedules(self):
        today = datetime.now().date()
        for s in self.schedules[:]:
            await self._process_daily_notification(s, today)

    async def _process_daily_notification(self, s, today):
        target_date = s["datetime"].date()
        days_left = (target_date - today).days
        
        if days_left < 0:
            self.schedules.remove(s)
            return

        chan = self.bot.get_channel(s["channel_id"])
        if not chan:
            return

        m_str = self._get_mention_string(s)
        pf = f"【{s['trip_name']}】" if s['trip_name'] else ""

        if days_left == 0:
            w_info = await self._get_forecast_weather(s)
            await chan.send(f"🚩 {m_str} 今日行程：{pf} **{s['task']}**{w_info}")
            self.schedules.remove(s)
        elif days_left == 3:
            await chan.send(f"🔔 {m_str} 預告：{pf} **{s['task']}** 還有 3 天！")
        elif days_left == 1:
            await chan.send(f"⚠️ {m_str} 強調：{pf} **{s['task']}** 就在明天！")

    def _get_mention_string(self, s):
        trip = next((t for t in self.all_trips if t["name"] == s["trip_name"]), None)
        m_set = {s["user_id"]}
        if trip:
            m_set.update(trip["members"])
        return " ".join([f"<@{u}>" for u in m_set])

    async def _get_forecast_weather(self, s):
        if s["location"]:
            wc = self.bot.get_cog("Weather")
            if wc:
                info = await wc.get_weather_info(s["location"])
                if info:
                    return f" | 📍 測報：{info['condition']} {info['temp']}°C"
        return ""

async def setup(bot):
    await bot.add_cog(TravelPlanner(bot))
