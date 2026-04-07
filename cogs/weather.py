import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import urllib.parse
import re

class Weather(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # WMO Weather interpretation codes (WW)
        self.weather_map = {
            0: "☀️ 晴朗",
            1: "🌤️ 大致天晴", 2: "⛅ 多雲", 3: "☁️ 陰天",
            45: "🌫️ 有霧", 48: "🌫️ 霧淞",
            51: "🌧️ 輕微毛毛雨", 53: "🌧️ 毛毛雨", 55: "🌧️ 密集毛毛雨",
            61: "🌧️ 小雨", 63: "🌧️ 中雨", 65: "🌧️ 大雨",
            71: "❄️ 小雪", 73: "❄️ 中雪", 75: "❄️ 大雪",
            80: "🌦️ 陣雨", 81: "🌦️ 局部陣雨", 82: "🌦️ 激烈陣雨",
            95: "⚡ 雷雨", 96: "⚡ 伴隨冰雹的雷雨", 99: "⚡ 強烈雷陣雨"
        }

    async def _extract_coords_from_url(self, url: str):
        """從 Google Maps 網址中提取座標，支援縮網址。"""
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            async with aiohttp.ClientSession() as session:
                # 處理縮網址 (maps.app.goo.gl, goo.gl/maps)
                if "maps.app.goo.gl" in url or "goo.gl/maps" in url:
                    async with session.get(url, allow_redirects=True, headers=headers) as resp:
                        url = str(resp.url)
                
                print(f"[DEBUG] Expanded Google Maps URL: {url}")
                
                # 模式 1: @lat,lon
                match1 = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
                if match1:
                    return float(match1.group(1)), float(match1.group(2))
                
                # 模式 2: ll=lat,lon (常見於舊版或特定導航連結)
                match2 = re.search(r'll=(-?\d+\.\d+),(-?\d+\.\d+)', url)
                if match2:
                    return float(match2.group(1)), float(match2.group(2))

                # 模式 3: !3dLat!4dLon (Google Maps 內部參數格式)
                match3 = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', url)
                if match3:
                    return float(match3.group(1)), float(match3.group(2))

                # 模式 4: 從 query 參數提取
                parsed = urllib.parse.urlparse(url)
                params = urllib.parse.parse_qs(parsed.query)
                if 'q' in params:
                    q_match = re.search(r'(-?\d+\.\d+),(-?\d+\.\d+)', params['q'][0])
                    if q_match:
                        return float(q_match.group(1)), float(q_match.group(2))
            return None
        except Exception as e:
            print(f"[DEBUG] Extraction error: {e}")
            return None

    async def get_weather_info(self, location_input: str):
        """根據地名或 Google Maps 網址獲取天氣資訊。"""
        print(f"[DEBUG] Processing weather info for: {location_input}")
        
        # 設定連線逾時
        timeout = aiohttp.ClientTimeout(total=10)
        
        try:
            lat, lon = None, None
            display_name = location_input

            # 判斷是否為網址
            if location_input.startswith("http"):
                coords = await self._extract_coords_from_url(location_input)
                if coords:
                    lat, lon = coords
                    display_name = "地圖指定位置"
                    print(f"[DEBUG] Coordinates extracted from URL: {lat}, {lon}")
                else:
                    print(f"[DEBUG] Failed to extract coordinates from URL.")
            
            # 如果不是網址，或是網址提取失敗，則使用地名搜尋 (Nominatim)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                if lat is None:
                    encoded_city = urllib.parse.quote(location_input)
                    geo_url = f"https://nominatim.openstreetmap.org/search?q={encoded_city}&format=json&limit=1"
                    headers = {"User-Agent": "TravelBotDC/1.1"}
                    
                    async with session.get(geo_url, headers=headers) as resp:
                        if resp.status != 200:
                            print(f"[DEBUG] Nominatim API error: {resp.status}")
                            return None
                        geo_data = await resp.json()
                        if not geo_data:
                            print(f"[DEBUG] Nominatim found no location for: {location_input}")
                            return None
                        lat, lon = geo_data[0]["lat"], geo_data[0]["lon"]
                        display_name = geo_data[0]["display_name"].split(",")[0]
                        print(f"[DEBUG] Nominatim found: {display_name} ({lat}, {lon})")

                # 查詢 Open-Meteo 天氣 API (加入重試機制)
                weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
                print(f"[DEBUG] Weather URL: {weather_url}")
                max_retries = 3
                for attempt in range(max_retries):
                    async with session.get(weather_url) as resp:
                        print(f"[DEBUG] Weather response: {resp}")
                        if resp.status == 200:
                            w_data = await resp.json()
                            curr = w_data["current_weather"]
                            print(f"[DEBUG] Weather data received: {curr}")
                            
                            code = curr.get("weathercode", 0)
                            condition = self.weather_map.get(code, "❓ 未知氣候")
                            
                            return {
                                "city": display_name,
                                "temp": curr["temperature"],
                                "wind": curr["windspeed"],
                                "condition": condition
                            }
                        else:
                            error_text = await resp.text()
                            print(f"[DEBUG] Open-Meteo API error (Attempt {attempt+1}/{max_retries}): {resp.status}")
                            print(f"[DEBUG] Response body: {error_text[:200]}")
                            if attempt < max_retries - 1:
                                import asyncio
                                await asyncio.sleep(2) # 等待 2 秒後重試
                            else:
                                return None
        except aiohttp.ClientConnectorError as e:
            print(f"[DEBUG] Network connection error: {e}")
            return None
        except Exception as e:
            print(f"[DEBUG] Weather error in get_weather_info: {e}")
            return None

    @app_commands.command(name="weather", description="查詢指定城市或 Google Maps 連結的天氣")
    async def weather(self, interaction: discord.Interaction, location: str):
        await interaction.response.defer()
        info = await self.get_weather_info(location)
        if not info:
            await interaction.followup.send(f"❌ 找不到地點或無法解析連結：`{location}`。")
            return

        embed = discord.Embed(title=f"🌡️ 天氣預報：{info['city']}", color=discord.Color.blue())
        embed.add_field(name="目前狀況", value=info["condition"], inline=False)
        embed.add_field(name="現在溫度", value=f"{info['temp']}°C", inline=True)
        embed.add_field(name="風速", value=f"{info['wind']} km/h", inline=True)
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Weather(bot))
