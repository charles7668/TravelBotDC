from langchain.tools import tool
import asyncpg

def get_trip_tools(db_pool, guild_id, user_id):
    """
    建立與資料庫互動的旅程工具。
    """
    
    @tool
    async def list_my_trips() -> str:
        """列出使用者在當前伺服器中參與的所有旅程。"""
        if not db_pool: return "❌ 資料庫未連線。"
        async with db_pool.acquire() as conn:
            records = await conn.fetch(
                "SELECT t.name, t.start_date, t.end_date FROM trips t "
                "JOIN trip_members tm ON t.name = tm.trip_name AND t.guild_id = tm.guild_id "
                "WHERE t.guild_id = $1 AND tm.user_id = $2",
                guild_id, user_id
            )
        if not records: return "你目前沒有參加任何旅程。"
        
        lines = [f"- {r['name']} ({r['start_date']} 到 {r['end_date']})" for r in records]
        return "你的旅程清單：\n" + "\n".join(lines)

    @tool
    async def get_trip_schedules(trip_name: str) -> str:
        """獲取特定旅程的所有詳細行程內容。"""
        if not db_pool: return "❌ 資料庫未連線。"
        async with db_pool.acquire() as conn:
            records = await conn.fetch(
                "SELECT task, datetime, location, description FROM schedules "
                "WHERE guild_id = $1 AND trip_name = $2 ORDER BY datetime ASC",
                guild_id, trip_name
            )
        if not records: return f"旅程 【{trip_name}】 目前沒有安排任何行程。"
        
        lines = []
        for r in records:
            loc = f" @ {r['location']}" if r['location'] else ""
            desc = f" ({r['description']})" if r['description'] else ""
            lines.append(f"- {r['datetime']}: {r['task']}{loc}{desc}")
            
        return f"【{trip_name}】的行程：\n" + "\n".join(lines)

    return [list_my_trips, get_trip_schedules]
