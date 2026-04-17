import aiohttp
import urllib.parse
from langchain.tools import tool

# WMO Weather interpretation codes (WW)
WEATHER_MAP = {
    0: "☀️ 晴朗",
    1: "🌤️ 大致天晴", 2: "⛅ 多雲", 3: "☁️ 陰天",
    45: "🌫️ 有霧", 48: "🌫️ 霧淞",
    51: "🌧️ 輕微毛毛雨", 53: "🌧️ 毛毛雨", 55: "🌧️ 密集毛毛雨",
    61: "🌧️ 小雨", 63: "🌧️ 中雨", 65: "🌧️ 大雨",
    71: "❄️ 小雪", 73: "❄️ 中雪", 75: "❄️ 大雪",
    80: "🌦️ 陣雨", 81: "🌦️ 局部陣雨", 82: "🌦️ 激烈陣雨",
    95: "⚡ 雷雨", 96: "⚡ 伴隨冰雹的雷雨", 99: "⚡ 強烈雷陣雨"
}

@tool
async def get_weather(location: str) -> str:
    """
    根據地名或 Google Maps 連結查詢當前的天氣資訊。
    Args:
        location: 城市名稱 (例如：台北) 或 Google Maps 連結。
    """
    try:
        lat, lon = None, None
        display_name = location

        async with aiohttp.ClientSession() as session:
            # 使用 Nominatim 進行地理編碼
            encoded_city = urllib.parse.quote(location)
            geo_url = f"https://nominatim.openstreetmap.org/search?q={encoded_city}&format=json&limit=1"
            headers = {"User-Agent": "TravelBotDC/1.1"}
            
            async with session.get(geo_url, headers=headers) as resp:
                if resp.status != 200:
                    return f"❌ 無法查詢地點：{location} (API 錯誤)"
                geo_data = await resp.json()
                if not geo_data:
                    return f"❌ 找不到地點：{location}"
                lat, lon = geo_data[0]["lat"], geo_data[0]["lon"]
                display_name = geo_data[0]["display_name"]

            # 查詢 Open-Meteo 天氣 API
            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
            async with session.get(weather_url) as resp:
                if resp.status == 200:
                    w_data = await resp.json()
                    curr = w_data["current_weather"]
                    code = curr.get("weathercode", 0)
                    condition = WEATHER_MAP.get(code, "❓ 未知氣候")
                    return (
                        f"🌡️ {display_name} 的天氣資訊：\n"
                        f"- 狀況：{condition}\n"
                        f"- 溫度：{curr['temperature']}°C\n"
                        f"- 風速：{curr['windspeed']} km/h"
                    )
                return f"❌ 無法獲取天氣資訊：{location} (天氣 API 錯誤)"
    except Exception as e:
        return f"❌ 查詢過程發生錯誤：{str(e)}"
