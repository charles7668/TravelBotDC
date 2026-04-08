import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, time
import uuid
import os

# --- 新增：刪除確認 View ---
class DeleteConfirmView(discord.ui.View):
    def __init__(self, schedule_item, parent_cog):
        super().__init__(timeout=60)
        self.item = schedule_item
        self.cog = parent_cog

    @discord.ui.button(label="🔥 確認刪除", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self.cog.bot.db_pool.acquire() as conn:
            await conn.execute("DELETE FROM schedules WHERE id = $1", self.item['id'])
        await interaction.response.send_message(
            f"🗑️ {interaction.user.mention} 已將行程 **{self.item['task']}** 從旅程 **【{self.item['trip_name']}】** 中移除！"
        )
        self.stop()

    @discord.ui.button(label="取消", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("👌 已取消刪除操作。", ephemeral=True)
        self.stop()

# --- 新增：多行描述編輯彈窗 ---
class DescriptionEditModal(discord.ui.Modal):
    def __init__(self, schedule_item, cog):
        super().__init__(title=f"編輯行程：{schedule_item['task'][:20]}")
        self.schedule_item = schedule_item
        self.cog = cog
        
        self.task_input = discord.ui.TextInput(
            label="行程名稱",
            style=discord.TextStyle.short,
            default=schedule_item["task"],
            required=True, max_length=100
        )
        self.location_input = discord.ui.TextInput(
            label="地點",
            style=discord.TextStyle.short,
            default=schedule_item["location"] if schedule_item["location"] else "",
            required=False, max_length=100
        )
        self.desc_input = discord.ui.TextInput(
            label="行程詳細描述 (支援 Markdown)",
            style=discord.TextStyle.long,
            placeholder="在此輸入行程細節、筆記或是連結...",
            default=schedule_item["description"] if schedule_item["description"] else "",
            required=False, max_length=1000
        )
        self.remind_input = discord.ui.TextInput(
            label="提醒訊息內容 (支援 Markdown)",
            style=discord.TextStyle.long,
            placeholder="例如：\n- 記得帶護照\n- 穿厚外套\n- [參考連結](https://...)",
            default=schedule_item["reminder_message"] if schedule_item["reminder_message"] else "",
            required=False, max_length=500
        )
        
        self.add_item(self.task_input)
        self.add_item(self.location_input)
        self.add_item(self.desc_input)
        self.add_item(self.remind_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_task = self.task_input.value
        new_loc = self.location_input.value
        new_desc = self.desc_input.value
        new_remind = self.remind_input.value
        
        async with self.cog.bot.db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE schedules SET task = $1, location = $2, description = $3, reminder_message = $4 WHERE id = $5", 
                new_task, new_loc, new_desc, new_remind, self.schedule_item["id"]
            )
            
        await interaction.response.send_message(
            f"📝 {interaction.user.mention} 已全面更新旅程 **【{self.schedule_item['trip_name']}】** 的行程資料：\n> **{new_task}** @ {new_loc if new_loc else '未定'}"
        )

# --- UI 組件：詳細資料按鈕 ---
class ScheduleDetailButton(discord.ui.Button):
    def __init__(self, schedule_id, task_label, parent_cog):
        super().__init__(label=task_label[:80], style=discord.ButtonStyle.secondary)
        self.schedule_id = schedule_id
        self.cog = parent_cog

    async def callback(self, interaction: discord.Interaction):
        async with self.cog.bot.db_pool.acquire() as conn:
            s = await conn.fetchrow("SELECT * FROM schedules WHERE id = $1", self.schedule_id)
        if not s:
            await interaction.response.send_message("❌ 行程資料不存在。", ephemeral=True); return

        t_fmt = '%Y-%m-%d %H:%M' if s['has_time'] else '%Y-%m-%d'
        is_url = s["location"] and (s["location"].startswith("http://") or s["location"].startswith("https://"))
        
        # 組裝純文字訊息內容
        msg = f"📝 **行程詳情：{s['task']}**\n"
        msg += f"━━━━━━━━━━━━━━━━━━\n"
        msg += f"📁 **所屬旅程**：{s['trip_name']}\n"
        msg += f"📅 **日期時間**：{s['datetime'].strftime(t_fmt)}\n"
        
        if s["location"]:
            loc_val = f"<{s['location']}>" if is_url else s["location"]
            msg += f"📍 **地點**：{loc_val}\n"
            
        if s["reminder_message"]:
            msg += f"\n🔔 **提醒訊息**：\n> {s['reminder_message'].replace('\n', '\n> ')}\n"
            
        msg += f"\n📜 **詳細描述 / 備註**：\n{s['description'] if s['description'] else '無筆記'}\n"
        
        # 如果是網址，在最後一行單獨貼出網址以確保預覽
        if is_url:
            msg += f"\n📍 **地圖預覽**：\n{s['location']}"

        edit_view = discord.ui.View()
        edit_btn = discord.ui.Button(label="✍️ 編輯行程", style=discord.ButtonStyle.primary)
        async def edit_callback(btn_inter: discord.Interaction): await btn_inter.response.send_modal(DescriptionEditModal(dict(s), self.cog))
        edit_btn.callback = edit_callback
        edit_view.add_item(edit_btn)

        if is_url:
            map_btn = discord.ui.Button(label="🗺️ 在 Google Maps 中開啟", url=s["location"])
            edit_view.add_item(map_btn)
        
        await interaction.response.send_message(content=msg, view=edit_view, ephemeral=False)

class TripNoteEditModal(discord.ui.Modal):
    def __init__(self, trip_item, cog):
        super().__init__(title=f"編輯旅程備註：{trip_item['name'][:20]}")
        self.trip_item = trip_item
        self.cog = cog
        self.note_input = discord.ui.TextInput(
            label="旅程整體備註 (支援 Markdown)",
            style=discord.TextStyle.long,
            placeholder="在此輸入這趟旅行的整體備註...",
            default=trip_item.get("note") if trip_item.get("note") else "",
            required=False, max_length=1000
        )
        self.add_item(self.note_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_note = self.note_input.value
        async with self.cog.bot.db_pool.acquire() as conn:
            await conn.execute("UPDATE trips SET note = $1 WHERE name = $2", new_note, self.trip_item['name'])
            
        await interaction.response.send_message(
            f"✅ {interaction.user.mention} 更新了旅程 **【{self.trip_item['name']}】** 的備註！"
        )

class TripNoteEditButton(discord.ui.Button):
    def __init__(self, trip_item, parent_cog):
        super().__init__(label="✍️ 編輯旅程備註", style=discord.ButtonStyle.primary, row=4)
        self.trip_item = trip_item
        self.cog = parent_cog

    async def callback(self, interaction: discord.Interaction):
        if self.trip_item.get("creator") and self.trip_item["creator"] != interaction.user.id:
            await interaction.response.send_message("❌ 您非旅程建立者，無法編輯備註。", ephemeral=True); return
        await interaction.response.send_modal(TripNoteEditModal(self.trip_item, self.cog))

class ScheduleListView(discord.ui.View):
    def __init__(self, related_schedules, trip_item, parent_cog):
        super().__init__(timeout=180)
        if trip_item:
            self.add_item(TripNoteEditButton(dict(trip_item), parent_cog))
        max_schedules = 24 if trip_item else 25
        for s in related_schedules[:max_schedules]:
            self.add_item(ScheduleDetailButton(s["id"], s["task"], parent_cog))


class TravelPlanner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_future_schedules.start()

    def cog_unload(self):
        self.check_future_schedules.cancel()

    # --- 智慧建議邏輯 ---
    async def trip_autocomplete(self, interaction: discord.Interaction, current: str):
        if not self.bot.db_pool: return []
        async with self.bot.db_pool.acquire() as conn:
            records = await conn.fetch("SELECT name FROM trips")
        formal = [r['name'] for r in records]
        all_options = list(set(formal) | {"未分組"})
        return [app_commands.Choice(name=t, value=t) for t in all_options if current.lower() in t.lower()][:25]

    async def schedule_autocomplete(self, interaction: discord.Interaction, current: str):
        if not self.bot.db_pool: return []
        u_id = interaction.user.id
        async with self.bot.db_pool.acquire() as conn:
            schedules = await conn.fetch("SELECT id, trip_name, task, datetime, has_time FROM schedules WHERE user_id = $1", u_id)
        choices = []
        for s in schedules:
            t_fmt = "%m/%d" if not s["has_time"] else "%m/%d %H:%M"
            label = f"{s['trip_name']} | {s['task']} ({s['datetime'].strftime(t_fmt)})"
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label[:100], value=s["id"]))
        return choices[:25]

    # --- 1. 基本指令 ---
    @app_commands.command(name="create_trip", description="建立大型旅程項目")
    async def create_trip(self, interaction: discord.Interaction, name: str, start_date: str, end_date: str, note: str = None):
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
            async with self.bot.db_pool.acquire() as conn:
                try:
                    await conn.execute("INSERT INTO trips (name, start_date, end_date, creator, note) VALUES ($1, $2, $3, $4, $5)", name, start, end, interaction.user.id, note)
                    await conn.execute("INSERT INTO trip_members (trip_name, user_id) VALUES ($1, $2)", name, interaction.user.id)
                    await interaction.response.send_message(f"🎒 **旅程核心已建立！**\n名稱：`{name}`")
                except Exception as e:
                    await interaction.response.send_message(f"❌ 建立失敗，名稱可能已存在。({e})", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ 日期格式錯誤。請使用 YYYY-MM-DD", ephemeral=True)

    @app_commands.command(name="edit_trip", description="編輯旅程的備註")
    @app_commands.autocomplete(name=trip_autocomplete)
    async def edit_trip(self, interaction: discord.Interaction, name: str, new_note: str):
        async with self.bot.db_pool.acquire() as conn:
            trip = await conn.fetchrow("SELECT creator FROM trips WHERE name = $1", name)
            if not trip:
                await interaction.response.send_message("❌ 找不到該旅程。", ephemeral=True); return
            if trip["creator"] and trip["creator"] != interaction.user.id:
                await interaction.response.send_message("❌ 您非旅程建立者，無法編輯備註。", ephemeral=True); return
            
            await conn.execute("UPDATE trips SET note = $1 WHERE name = $2", new_note, name)
        await interaction.response.send_message(f"✅ {interaction.user.mention} 已成功更新旅程 **{name}** 的備註！")

    @app_commands.command(name="join_trip", description="加入旅程計畫")
    @app_commands.autocomplete(name=trip_autocomplete)
    async def join_trip(self, interaction: discord.Interaction, name: str):
        u_id = interaction.user.id
        async with self.bot.db_pool.acquire() as conn:
            trip = await conn.fetchrow("SELECT * FROM trips WHERE name = $1", name)
            if not trip:
                await conn.execute("INSERT INTO trips (name) VALUES ($1)", name)
            
            member = await conn.fetchrow("SELECT * FROM trip_members WHERE trip_name = $1 AND user_id = $2", name, u_id)
            if not member:
                await conn.execute("INSERT INTO trip_members (trip_name, user_id) VALUES ($1, $2)", name, u_id)
                await interaction.response.send_message(f"✨ 成功加入了旅程：**{name}**！")
            else:
                await interaction.response.send_message("ℹ️ 您已在成員名單中。", ephemeral=True)

    # --- 2. 行程設定 ---
    @app_commands.command(name="schedule", description="排定行程")
    @app_commands.describe(
        time_str="輸入日期時間。格式：YYYY-MM-DD 或 YYYY-MM-DD HH:MM (例如：2024-05-20 14:30)",
        task="行程名稱 (例如：搭乘飛機、前往飯店)",
        trip_name="所屬旅程名稱 (選填，可留空或選「未分組」)",
        location="地點名稱或 Google Map 連結 (選填，若輸入名稱且為當日行程會顯示天氣)",
        description="詳細描述或筆記 (選填)",
        reminder_message="出發前要提醒的訊息，支援 Markdown (選填)"
    )
    @app_commands.autocomplete(trip_name=trip_autocomplete)
    async def schedule(self, interaction: discord.Interaction, time_str: str, task: str, trip_name: str = None, location: str = None, description: str = None, reminder_message: str = None):
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
            
            async with self.bot.db_pool.acquire() as conn:
                # 驗證旅程是否存在 (排除 "未分組")
                if final_t_name != "未分組":
                    trip_exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM trips WHERE name = $1)", final_t_name)
                    if not trip_exists:
                        await interaction.followup.send(f"❌ 找不到旅程：`{final_t_name}`。請確認名稱是否正確，或先使用 `/create_trip` 建立旅程。")
                        return

                await conn.execute(
                    "INSERT INTO schedules (id, datetime, has_time, task, trip_name, location, description, reminder_message, user_id, channel_id) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
                    s_id, dt, has_time, task, final_t_name, location, description, reminder_message, interaction.user.id, interaction.channel_id
                )
            
            w_str = ""
            if dt.date() == datetime.now().date() and location:
                is_url = location.startswith("http://") or location.startswith("https://")
                if not is_url:
                    wc = self.bot.get_cog("Weather")
                    if wc:
                        info = await wc.get_weather_info(location)
                        if info: w_str = f" | 🌡️ **即時天氣：{info['condition']} {info['temp']}°C**"

            await interaction.followup.send(f"📅 已鎖定：`{time_str}` - **{task}** (分組：`{final_t_name}`){w_str}")
        except Exception as e:
            await interaction.followup.send(f"❌ 處理錯誤，請聯絡管理員。({e})")

    # --- 3. 識別 ID 查詢與編輯 ---
    @app_commands.command(name="edit_schedule", description="編輯行程基本內容")
    @app_commands.describe(
        full_task_id="選擇要編輯的行程",
        new_task="更新行程名稱 (選填)",
        new_location="更新地點或 Google Map 連結 (選填)",
        new_reminder_message="更新提醒訊息 (選填)"
    )
    @app_commands.autocomplete(full_task_id=schedule_autocomplete)
    async def edit_schedule(self, interaction: discord.Interaction, full_task_id: str, new_task: str = None, new_location: str = None, new_reminder_message: str = None):
        u_id = interaction.user.id
        async with self.bot.db_pool.acquire() as conn:
            target = await conn.fetchrow("SELECT * FROM schedules WHERE id = $1 AND user_id = $2", full_task_id, u_id)
            if not target:
                await interaction.response.send_message("❌ 找不到該筆紀錄或您無權編輯。", ephemeral=True); return

            changes = []
            updates = []
            args = []
            arg_id = 1
            if new_task and target["task"] != new_task:
                changes.append(f"🔹 把名稱從 `{target['task']}` 更新成了 `{new_task}`")
                updates.append(f"task = ${arg_id}")
                args.append(new_task)
                arg_id += 1
            if new_location and target["location"] != new_location:
                old_loc = target["location"] if target["location"] else "(無)"
                changes.append(f"📍 把地點從 `{old_loc}` 更新成了 `{new_location}`")
                updates.append(f"location = ${arg_id}")
                args.append(new_location)
                arg_id += 1
            if new_reminder_message and target["reminder_message"] != new_reminder_message:
                changes.append(f"🔔 更新了提醒訊息內容")
                updates.append(f"reminder_message = ${arg_id}")
                args.append(new_reminder_message)
                arg_id += 1
            
            if updates:
                args.append(full_task_id)
                await conn.execute(f"UPDATE schedules SET {', '.join(updates)} WHERE id = ${arg_id}", *args)

        if not changes: 
            await interaction.response.send_modal(DescriptionEditModal(dict(target), self))
        else: 
            await interaction.response.send_message(f"✨ {interaction.user.mention} 更新了旅程 **【{target['trip_name']}】** 的紀錄！\n" + "\n".join(changes))

    @app_commands.command(name="delete_schedule", description="刪除特定的行程 (需確認)")
    @app_commands.autocomplete(full_task_id=schedule_autocomplete)
    async def delete_schedule(self, interaction: discord.Interaction, full_task_id: str):
        u_id = interaction.user.id
        async with self.bot.db_pool.acquire() as conn:
            target = await conn.fetchrow("SELECT * FROM schedules WHERE id = $1", full_task_id)
            if not target:
                await interaction.response.send_message("❌ 找不到行程資料。", ephemeral=True); return

            # 權限檢查：只有建立者或旅程 owner 可以刪除
            trip = await conn.fetchrow("SELECT creator FROM trips WHERE name = $1", target["trip_name"])
            is_owner = (u_id == target["user_id"]) or (trip and trip["creator"] == u_id)
            
            if not is_owner:
                await interaction.response.send_message("❌ 您非行程建立者，無法執行刪除。", ephemeral=True); return
                
        view = DeleteConfirmView(dict(target), self)
        await interaction.response.send_message(
            f"⚠️ 您確定要刪除旅程 **【{target['trip_name']}】** 中的行程 **{target['task']}** 嗎？\n此動作無法還原。",
            view=view, ephemeral=True
        )

    @app_commands.command(name="view_details", description="查詢特定行程詳細筆記")
    @app_commands.autocomplete(full_task_id=schedule_autocomplete)
    async def view_details(self, interaction: discord.Interaction, full_task_id: str):
        btn = ScheduleDetailButton(full_task_id, "查詢中", self)
        await btn.callback(interaction)

    @app_commands.command(name="view_trip", description="檢視旅程清單")
    @app_commands.autocomplete(name=trip_autocomplete)
    async def view_trip(self, interaction: discord.Interaction, name: str):
        async with self.bot.db_pool.acquire() as conn:
            trip = await conn.fetchrow("SELECT * FROM trips WHERE name = $1", name)
            members = await conn.fetch("SELECT user_id FROM trip_members WHERE trip_name = $1", name)
            related = await conn.fetch("SELECT * FROM schedules WHERE trip_name = $1 ORDER BY datetime ASC", name)
            
        if not trip and not related:
            await interaction.response.send_message(f"❌ 查無此分組。", ephemeral=True); return
            
        embed = discord.Embed(title=f"🎒 旅行計畫表：{name}", color=discord.Color.dark_green())
        if members:
            m_list = ", ".join([f"<@{m['user_id']}>" for m in members])
            embed.add_field(name="👥 行程夥伴", value=m_list, inline=False)
            
        if trip and trip.get("note"):
            embed.add_field(name="📝 旅程備註", value=trip["note"], inline=False)

        t_fmt = lambda s: s['datetime'].strftime('%m/%d %H:%M' if s['has_time'] else '%m/%d')
        lines = []
        for s in related:
            line = f"🔹 `{t_fmt(s)}` - **{s['task']}**"
            if s.get("description"):
                desc = s['description'].replace('\n', ' ')
                if len(desc) > 20: desc = desc[:20] + "..."
                line += f" *(備註: {desc})*"
            lines.append(line)
        embed.description = "\n".join(lines) if lines else "目前尚未規劃任何行程。"
        
        if related or trip:
            view = ScheduleListView([dict(s) for s in related], dict(trip) if trip else None, self)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="list_trips", description="列出計畫清單")
    async def list_trips(self, interaction: discord.Interaction):
        u_id = interaction.user.id
        async with self.bot.db_pool.acquire() as conn:
            trips = await conn.fetch("SELECT * FROM trips")
            uncat_count = await conn.fetchval("SELECT COUNT(*) FROM schedules WHERE trip_name = '未分組' AND user_id = $1", u_id)
            
        if not trips and uncat_count == 0:
            await interaction.response.send_message("目前無資料。", ephemeral=True); return
            
        embed = discord.Embed(title="✈️ 旅程預覽", color=discord.Color.blue())
        for t in trips:
            async with self.bot.db_pool.acquire() as conn:
                m_count = await conn.fetchval("SELECT COUNT(*) FROM trip_members WHERE trip_name = $1", t['name'])
            
            period = f"`{t['start_date']}` 到 `{t['end_date']}`" if t["start_date"] else "日期未定"
            note_str = f"\n📝 備註: {t['note'][:20]}..." if t.get("note") else ""
            embed.add_field(name=f"📌 {t['name']}", value=f"📅 {period}\n👥 {m_count} 人{note_str}", inline=False)
            
        if uncat_count > 0: 
            embed.add_field(name="📂 其他分組", value="`未分組`", inline=False)
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- 測試專用指令 (測試完可刪除) ---
    if os.getenv('TRAVEL_BOT_TEST') == 'true':
        @app_commands.command(name="test_notification", description="[開發測試] 立即觸發指定行程的提醒通知")
        @app_commands.autocomplete(full_task_id=schedule_autocomplete)
        async def test_notification(self, interaction: discord.Interaction, full_task_id: str, simulate_days_left: int = 0):
            async with self.bot.db_pool.acquire() as conn:
                s = await conn.fetchrow("SELECT * FROM schedules WHERE id = $1", full_task_id)
            
            if not s:
                await interaction.response.send_message("❌ 找不到行程資料。", ephemeral=True); return
            
            from datetime import timedelta
            mock_today = s["datetime"].date() - timedelta(days=simulate_days_left)
            
            await interaction.response.send_message(f"🧪 正在模擬 {simulate_days_left} 天前的提醒發送...", ephemeral=True)
            await self._process_daily_notification(dict(s), mock_today, is_simulation=True, interaction=interaction)

    # --- 背景服務與提醒 ---
    @tasks.loop(time=time(hour=0, minute=0))
    async def check_future_schedules(self):
        if not self.bot.db_pool: return
        today = datetime.now().date()
        async with self.bot.db_pool.acquire() as conn:
            schedules = await conn.fetch("SELECT * FROM schedules")
            for s in schedules:
                await self._process_daily_notification(s, today)

    async def _process_daily_notification(self, s, today, is_simulation=False, interaction: discord.Interaction = None):
        target_date = s["datetime"].date()
        days_left = (target_date - today).days
        if days_left < 0:
            if not is_simulation:
                async with self.bot.db_pool.acquire() as conn:
                    await conn.execute("DELETE FROM schedules WHERE id = $1", s["id"])
            return
            
        pf = f"【{s['trip_name']}】" if s['trip_name'] else ""
        m_str = await self._get_mention_string(s)
        remind_msg = f"\n\n💡 **提醒訊息：**\n> {s['reminder_message']}" if s.get('reminder_message') else ""

        async def send_notification(content):
            if interaction:
                # 測試模式下，使用 ephemeral 訊息僅讓使用者看到
                await interaction.followup.send(content, ephemeral=True)
            else:
                chan = self.bot.get_channel(s["channel_id"])
                if chan:
                    await chan.send(content)
        
        if days_left == 0:
            w_info = await self._get_forecast_weather(s)
            await send_notification(f"🚩 {m_str} 今日：{pf} **{s['task']}**{w_info}{remind_msg}")
            if not is_simulation:
                async with self.bot.db_pool.acquire() as conn:
                    await conn.execute("DELETE FROM schedules WHERE id = $1", s["id"])
        elif days_left == 3 and (not s["notified_3d"] or is_simulation): 
            await send_notification(f"🔔 {m_str} 預告：{pf} **{s['task']}** 還有 3 天！{remind_msg}")
            if not is_simulation:
                async with self.bot.db_pool.acquire() as conn:
                    await conn.execute("UPDATE schedules SET notified_3d = TRUE WHERE id = $1", s["id"])
        elif days_left == 1 and (not s["notified_1d"] or is_simulation): 
            await send_notification(f"⚠️ {m_str} 強調：{pf} **{s['task']}** 就在明天！{remind_msg}")
            if not is_simulation:
                async with self.bot.db_pool.acquire() as conn:
                    await conn.execute("UPDATE schedules SET notified_1d = TRUE WHERE id = $1", s["id"])

    async def _get_mention_string(self, s):
        m_set = {s["user_id"]}
        if s["trip_name"] != "未分組":
            async with self.bot.db_pool.acquire() as conn:
                members = await conn.fetch("SELECT user_id FROM trip_members WHERE trip_name = $1", s["trip_name"])
                for m in members: m_set.add(m["user_id"])
        return " ".join([f"<@{u}>" for u in m_set])

    async def _get_forecast_weather(self, s):
        if s["location"]:
            wc = self.bot.get_cog("Weather")
            if wc:
                info = await wc.get_weather_info(s["location"])
                if info: 
                    return f" | 📍 {info['city']}：{info['condition']}，氣溫 {info['temp']}°C，風速 {info['wind']} km/h"
        return ""

async def setup(bot):
    await bot.add_cog(TravelPlanner(bot))
