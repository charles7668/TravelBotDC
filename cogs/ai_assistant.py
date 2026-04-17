import discord
from discord import app_commands
from discord.ext import commands
from utils.llm import get_openrouter_chat
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from skills import get_current_time, get_weather
from skills.trip_tool import get_trip_tools

class AIAssistant(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ask_bot", description="詢問旅遊小助手建議 (支援資料庫與工具)")
    @app_commands.describe(question="輸入你的旅遊問題")
    async def ask_bot(self, interaction: discord.Interaction, question: str):
        await interaction.response.defer()
        
        try:
            # 獲取專屬此使用者的旅程工具
            trip_tools = get_trip_tools(self.bot.db_pool, interaction.guild_id, interaction.user.id)
            all_tools = [get_current_time, get_weather] + trip_tools
            
            # 將工具名稱對應到實例
            tool_map = {tool.name: tool for tool in all_tools}
            
            # 初始化帶有工具的 LLM
            llm = get_openrouter_chat(tools=all_tools)
            
            messages = [
                SystemMessage(content=(
                    "你是一個專業的旅遊小助手。你可以存取使用者的旅程與行程資料。\n"
                    "請先檢查當前日期時間，並根據使用者的需求調用適當的工具 (如獲取天氣或查詢旅程)。\n"
                    "回答應簡明扼要，並充滿旅遊建議。"
                )),
                HumanMessage(content=question)
            ]
            
            # 建立對話循環，處理工具調用 (最多 5 次循環以防無限迴圈)
            for _ in range(5):
                response = await llm.ainvoke(messages)
                messages.append(response)
                
                if not response.tool_calls:
                    break
                    
                # 執行工具調用
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_to_call = tool_map.get(tool_name)
                    
                    if tool_to_call:
                        print(f"[AI] 正在調用工具: {tool_name}({tool_call['args']})")
                        try:
                            # 執行非同步工具
                            tool_result = await tool_to_call.ainvoke(tool_call["args"])
                        except Exception as tool_err:
                            tool_result = f"❌ 執行工具出錯: {tool_err}"
                            
                        messages.append(ToolMessage(
                            tool_call_id=tool_call["id"],
                            content=str(tool_result)
                        ))
                    else:
                        messages.append(ToolMessage(
                            tool_call_id=tool_call["id"],
                            content=f"❌ 找不到名為 {tool_name} 的工具。"
                        ))

            embed = discord.Embed(
                title="🤖 旅遊小助手回覆",
                description=messages[-1].content,
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"詢問者: {interaction.user.display_name}")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 發生錯誤: {e}")

async def setup(bot):
    await bot.add_cog(AIAssistant(bot))
