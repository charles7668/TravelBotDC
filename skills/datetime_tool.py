from langchain.tools import tool
from datetime import datetime

@tool
def get_current_time() -> str:
    """獲取目前的日期與時間，用於回答需要考慮當前時間的問題。"""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S (%A)")
