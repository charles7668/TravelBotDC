import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, time
import uuid

# --- 新增：多行描述編輯彈窗 ---
class DescriptionEditModal(discord.ui.Modal):
    def __init__(self, schedule_item):
        super().__init__(title=f"編輯行程筆記：{schedule_item['task'][:20]}")
        self.schedule_item = schedule_item
        
        # 建立大文本輸入框
        self.desc_input = discord.ui.TextInput(
            label="行程詳細描述 (支援 Markdown)",
            style=discord.TextStyle.long, # 設定為長文本 (支援換行)
            placeholder="在此輸入行程細節、筆記或是連結...",
            default=schedule_item["description"] if schedule_item["description"] else "",
            required=True,
            max_length=1000
        )
        self.add_item(self.desc_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.schedule_item["description"] = self.desc_input.value
        await interaction.response.send_message(
            f"📝 {interaction.user.mention} 更新了旅程 **【{self.schedule_item['trip_name']}】** 的詳細筆記：\n> 行程：**{self.schedule_item['task']}**"
        )

# --- UI 組件：詳細資料按鈕 ---
class ScheduleDetailButton(discord.ui.Button):
    def __init__(self, schedule_id, task_label, parent_cog):
        super().__init__(label=task_label[:80], style=discord.ButtonStyle.secondary)
        self.schedule_id = schedule_id
        self.cog = parent_cog

    async def callback(self, interaction: discord.Interaction):
        s = next((s for s in self.cog.schedules if s["id"] == self.schedule_id), None)
        if not s:
            await interaction.response.send_message("❌ 行程資料不存在。", ephemeral=True); return

        embed = discord.Embed(title=f"📝 行程筆記：{s['task']}", color=discord.Color.orange())
        embed.add_field(name="所屬旅程", value=s["trip_name"], inline=True)
        t_fmt = '%Y-%m-%d %H:%M' if s['has_time'] else '%Y-%m-%d'
        embed.add_field(name="日期時間", value=s["datetime"].strftime(t_fmt), inline=True)
        if s["location"]: embed.add_field(name="地點", value=s["location"], inline=True)
        
        desc = s["description"] if s["description"] else "目前尚無詳細描述或備註。"
        embed.add_field(name="📜 詳細描述 / 備註", value=desc, inline=False)
        
        # 提供另一個按鈕讓使用者可以點擊並開啟「多行編輯」
        edit_view = discord.ui.View()
        edit_btn = discord.ui.Button(label="✍️ 編輯詳細筆記", style=discord.ButtonStyle.primary)
        
        async def edit_callback(btn_inter: discord.Interaction):
            await btn_inter.response.send_modal(DescriptionEditModal(s))
            
        edit_btn.callback = edit_callback
        edit_view.add_item(edit_btn)
        
        await interaction.response.send_message(embed=embed, view=edit_view, ephemeral=True)

# --- 行程列表視圖 ---
class ScheduleListView(discord.ui.View):
    def __init__(self, related_schedules, parent_cog):
        super().__init__(timeout=180)
        for s in related_schedules[:25]:
            self.add_item(ScheduleDetailButton(s["id"], s["task"], parent_cog))

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
        formal = [t["name"] for t in self.all_trips]
        all_options = list(set(formal) | {"未分組"})
        return [app_commands.Choice(name=t, value=t) for t in all_options if current.lower() in t.lower()][:25]

    async def schedule_autocomplete(self, interaction: discord.Interaction, current: str):
        u_id = interaction.user.id
        choices = []
        for s in self.schedules:
            if s["user_id"] == u_id:
                t_fmt = "%m/%d" if not s["has_time"] else "%m/%d %H:%M"
                label = f"{s['trip_name']} | {s['task']} ({s['datetime'].strftime(t_fmt)})"
                if current.lower() in label.lower():
                    choices.append(app_commands.Choice(name=label[:100], value=s["id"]))
        return choices[:25]

    # --- 1. 基本指令 ---
    @app_commands.command(name="create_trip", description="建立大型旅程項目")
    async def create_trip(self, interaction: discord.Interaction, name: str, start_date: str, end_date: str):
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
            self.all_trips.append({"name": name, "start": start, "end": end, "creator": interaction.user.id, "members": [interaction.user.id]})
            await interaction.response.send_message(f"🎒 **旅程核心已建立！**\n名稱：`{name}`")
        except ValueError:
            await interaction.response.send_message("❌ 格式錯誤。", ephemeral=True)

    @app_commands.command(name="join_trip", description="加入旅程計畫")
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
            await interaction.response.send_message("ℹ️ 您已在成員名單中。", ephemeral=True)

    # --- 2. 行程設定 (注入 UUID) ---
    @app_commands.command(name="schedule", description="排定行程 (單行描述)")
    @app_commands.autocomplete(trip_name=trip_autocomplete)
    async def schedule(self, interaction: discord.Interaction, time_str: str, task: str, trip_name: str = None, location: str = None, description: str = None):
        await interaction.response.defer()
        try:
            try:
                dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M"); has_time = True
            except ValueError:
                dt = datetime.strptime(time_str, "%Y-%m-%d"); has_time = False

            if dt < datetime.now() and (has_time or dt.date() < datetime.now().date()):
                await interaction.followup.send("❌ 過去時間！"); return

            s_id = uuid.uuid4().hex[:8] 
            final_t_name = trip_name if trip_name else "未分組"
            self.schedules.append({
                "id": s_id, "datetime": dt, "has_time": has_time, "task": task, "trip_name": final_t_name,
                "location": location, "description": description,
                "user_id": interaction.user.id, "channel_id": interaction.channel_id,
                "notified_3d": False, "notified_1d": False
            })
            
            w_str = ""
            if dt.date() == datetime.now().date() and location:
                wc = self.bot.get_cog("Weather")
                if wc:
                    info = await wc.get_weather_info(location)
                    if info: w_str = f" | 🌡️ **即時天氣：{info['condition']} {info['temp']}°C**"

            await interaction.followup.send(f"📅 已鎖定：`{time_str}` - **{task}** (分組：`{final_t_name}`){w_str}")
        except Exception:
            await interaction.followup.send("❌ 處理錯誤，請聯絡管理員。")

    # --- 3. 識別 ID 查詢與編輯 (加入彈窗支援) ---
    @app_commands.command(name="edit_schedule", description="編輯具體行程內容")
    @app_commands.autocomplete(full_task_id=schedule_autocomplete)
    async def edit_schedule(self, interaction: discord.Interaction, full_task_id: str, new_task: str = None, new_location: str = None):
        u_id = interaction.user.id
        target = next((s for s in self.schedules if s["id"] == full_task_id and s["user_id"] == u_id), None)
        if not target:
            await interaction.response.send_message("❌ 找不到該筆紀錄。", ephemeral=True); return

        if new_task: target["task"] = new_task
        if new_location: target["location"] = new_location
        
        # 由於 Slash Command 無法多行輸入，這裡主動詢問使用者是否要編輯描述 (透過彈窗)
        if not new_task and not new_location:
            # 如果單純下指令沒填東西，直接彈窗編輯描述
            await interaction.response.send_modal(DescriptionEditModal(target))
        else:
            await interaction.response.send_message(f"✅ 行程基本資料已更新！\n(若需編輯多行描述，請點擊行程按鈕使用彈窗編輯)", ephemeral=True)

    @app_commands.command(name="view_details", description="查詢特定行程詳細筆記")
    @app_commands.autocomplete(full_task_id=schedule_autocomplete)
    async def view_details(self, interaction: discord.Interaction, full_task_id: str):
        # 詳細資料指令沿用按鈕逻辑，這樣查詢完可以順便點「編輯描述」
        btn = ScheduleDetailButton(full_task_id, "查詢中", self)
        await btn.callback(interaction)

    @app_commands.command(name="view_trip", description="檢視旅程清單與精選按鈕")
    @app_commands.autocomplete(name=trip_autocomplete)
    async def view_trip(self, interaction: discord.Interaction, name: str = "未分組"):
        trip = next((t for t in self.all_trips if t["name"] == name), None)
        related = sorted([s for s in self.schedules if s["trip_name"] == name], key=lambda x: x["datetime"])
        if not trip and not related:
            await interaction.response.send_message(f"❌ 查無此分組。", ephemeral=True); return

        embed = discord.Embed(title=f"🎒 旅行計畫表：{name}", color=discord.Color.dark_green())
        if trip and trip["members"]:
            m_list = ", ".join([f"<@{uid}>" for uid in trip["members"]])
            embed.add_field(name="👥 行程夥伴", value=m_list, inline=False)
            
        t_fmt = lambda s: s['datetime'].strftime('%m/%d %H:%M' if s['has_time'] else '%m/%d')
        lines = [f"🔹 `{t_fmt(s)}` - **{s['task']}**" for s in related]
        embed.description = "\n".join(lines) if lines else "目前尚未規劃任何行程。"
        
        view = ScheduleListView(related, self) if related else None
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="list_trips", description="列出計畫清單")
    async def list_trips(self, interaction: discord.Interaction):
        u_id = interaction.user.id
        if not self.all_trips and not self.schedules:
            await interaction.response.send_message("目前無資料。", ephemeral=True); return
        embed = discord.Embed(title="✈️ 旅程預覽", color=discord.Color.blue())
        for t in self.all_trips:
            period = f"`{t['start']}` 到 `{t['end']}`" if t["start"] else "日期未定"
            embed.add_field(name=f"📌 {t['name']}", value=f"📅 {period}\n👥 {len(t['members'])} 人", inline=False)
        has_uncat = any(s["trip_name"] == "未分組" and s["user_id"] == u_id for s in self.schedules)
        if has_uncat: embed.add_field(name="📂 其他分組", value="`未分組`", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- 背景服務維持不變 ---
    @tasks.loop(time=time(hour=0, minute=0))
    async def check_future_schedules(self):
        today = datetime.now().date()
        for s in self.schedules[:]:
            await self._process_daily_notification(s, today)

    async def _process_daily_notification(self, s, today):
        target_date = s["datetime"].date()
        days_left = (target_date - today).days
        if days_left < 0:
            self.schedules.remove(s); return
        chan = self.bot.get_channel(s["channel_id"])
        if not chan: return
        pf = f"【{s['trip_name']}】" if s['trip_name'] else ""
        m_str = self._get_mention_string(s)
        if days_left == 0:
            w_info = await self._get_forecast_weather(s)
            await chan.send(f"🚩 {m_str} 今日：{pf} **{s['task']}**{w_info}")
            self.schedules.remove(s)
        elif days_left == 3: await chan.send(f"🔔 {m_str} 預告：{pf} **{s['task']}** 還有 3 天！")
        elif days_left == 1: await chan.send(f"⚠️ {m_str} 強烈提醒：{pf} **{s['task']}** 就在明天！")

    def _get_mention_string(self, s):
        trip = next((t for t in self.all_trips if t["name"] == s["trip_name"]), None)
        m_set = {s["user_id"]}
        if trip: m_set.update(trip["members"])
        return " ".join([f"<@{u}>" for u in m_set])

    async def _get_forecast_weather(self, s):
        if s["location"]:
            wc = self.bot.get_cog("Weather")
            if wc:
                info = await wc.get_weather_info(s["location"])
                if info: return f" | 📍 測報：{info['condition']} {info['temp']}°C"
        return ""

async def setup(bot):
    await bot.add_cog(TravelPlanner(bot))
