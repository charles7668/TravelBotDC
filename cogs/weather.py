import discord
from discord import app_commands
from discord.ext import commands
import aiohttp

class Weather(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_weather_desc(self, code):
        weather_codes = {
            0: "晴朗 ☀️", 1: "主要晴朗 🌤️", 2: "部分多雲 ⛅", 3: "陰天 ☁️",
            45: "霧 🌫️", 51: "毛毛雨 🌧️", 61: "小雨 🌧️", 71: "小雪 ❄️",
            80: "陣雨 ⛈️", 95: "雷陣雨 ⚡"
        }
        return weather_codes.get(code, "未知天氣")

    @app_commands.command(name="weather", description="查詢指定城市的天氣 (完美支援中文地名)")
    @app_commands.describe(city="城市名稱 (例如: 台北, 東京, 大阪, 紐約)")
    async def weather(self, interaction: discord.Interaction, city: str):
        await interaction.response.defer()
        
        async with aiohttp.ClientSession() as session:
            # Step 1: 使用 Nominatim (OpenStreetMap) 獲取經緯度 - 對中文支援最完整
            geo_url = "https://nominatim.openstreetmap.org/search"
            geo_params = {
                "q": city,
                "format": "json",
                "limit": 1,
                "addressdetails": 1,
                "accept-language": "zh-TW" # 優先回傳繁體中文資訊
            }
            # Nominatim 要求必須設定 User-Agent
            headers = {
                "User-Agent": "TravelBotDC/1.0 (Contact: DiscordBotDev)"
            }
            
            async with session.get(geo_url, params=geo_params, headers=headers) as resp:
                print(f"DEBUG: 查詢城市 (Nominatim) = {city}")
                print(f"DEBUG: 參數 (geo_params) = {geo_params}")
                print(f"DEBUG: 最終請求 URL = {resp.url}")
                
                if resp.status != 200:
                    await interaction.followup.send("❌ 無法連接到 Geocoding 服務（Nominatim）。")
                    return
                
                results = await resp.json()
                if not results:
                    await interaction.followup.send(f"❌ 找不到地點 `{city}`，請嘗試更確切的名字。")
                    return
                
                location = results[0]
                lat, lon = location["lat"], location["lon"]
                display_name = location.get("display_name", city)
                # 簡化顯示名稱，通常 Nominatim 回傳很長，我們取前面兩段
                display_parts = display_name.split(",")
                short_name = ", ".join(display_parts[:2]).strip() if len(display_parts) > 1 else display_name

            # Step 2: 使用經緯度從 Open-Meteo 獲取天氣 (維持不變)
            weather_url = "https://api.open-meteo.com/v1/forecast"
            weather_params = {
                "latitude": lat,
                "longitude": lon,
                "current_weather": "true",
                "timezone": "auto"
            }
            
            async with session.get(weather_url, params=weather_params) as resp:
                if resp.status == 200:
                    weather_data = await resp.json()
                    current = weather_data["current_weather"]
                    temp = current["temperature"]
                    code = current["weathercode"]
                    desc = self.get_weather_desc(code)
                    
                    await interaction.followup.send(f"📍 **{short_name}**\n🌡️ 溫度: `{temp}°C`\n🌈 狀況: `{desc}`")
                else:
                    await interaction.followup.send("❌ 獲取天氣資料失敗。")

async def setup(bot):
    await bot.add_cog(Weather(bot))
