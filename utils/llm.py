from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv

load_dotenv()

def get_openrouter_chat(tools=None):
    """
    初始化 OpenRouter Chat 實例
    預設模型：google/gemini-2.0-flash-lite:free
    :param tools: 選擇性傳入的工具列表 (LangChain tools)
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = "https://openrouter.ai/api/v1"
    model_name = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-lite:free")

    if not api_key:
        raise ValueError("❌ 找不到 OPENROUTER_API_KEY，請檢查環境變數。")

    llm = ChatOpenAI(
        openai_api_key=api_key,
        openai_api_base=base_url,
        model=model_name,
        default_headers={
            "HTTP-Referer": "https://github.com/charles7668/TravelBotDC", # OpenRouter 建議提供
            "X-Title": "TravelBotDC",
        }
    )

    if tools:
        llm = llm.bind_tools(tools)
    
    return llm
