import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import urllib.parse

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

    async def get_weather_info(self, city: str):
        try:
            encoded_city = urllib.parse.quote(city)
            geo_url = f"https://nominatim.openstreetmap.org/search?q={encoded_city}&format=json&limit=1"
            headers = {"User-Agent": "TravelBotDC/1.1"}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(geo_url, headers=headers) as resp:
                    if resp.status != 200: return None
                    geo_data = await resp.json()
                    if not geo_data: return None
                    lat, lon = geo_data[0]["lat"], geo_data[0]["lon"]
                    display_name = geo_data[0]["display_name"].split(",")[0]

                weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
                async with session.get(weather_url) as resp:
                    if resp.status != 200: return None
                    w_data = await resp.json()
                    curr = w_data["current_weather"]
                    
                    # 獲取中文描述
                    code = curr.get("weathercode", 0)
                    condition = self.weather_map.get(code, "❓ 未知氣候")
                    
                    return {
                        "city": display_name,
                        "temp": curr["temperature"],
                        "wind": curr["windspeed"],
                        "condition": condition # 新增狀況
                    }
        except:
            return None

    @app_commands.command(name="weather", description="查詢指定城市的天氣 (完美支援中文地名)")
    async def weather(self, interaction: discord.Interaction, city: str):
        await interaction.response.defer()
        info = await self.get_weather_info(city)
        if not info:
            await interaction.followup.send(f"❌ 找不到城市 `{city}`。")
            return

        embed = discord.Embed(title=f"🌡️ 天氣預報：{info['city']}", color=discord.Color.blue())
        embed.add_field(name="目前狀況", value=info["condition"], inline=False) # 顯示狀況
        embed.add_field(name="現在溫度", value=f"{info['temp']}°C", inline=True)
        embed.add_field(name="風速", value=f"{info['wind']} km/h", inline=True)
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Weather(bot))
