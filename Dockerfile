# 使用 official uv image 作為基底，這可以加快安裝速度並減少映像檔大小
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

# 設定工作目錄
WORKDIR /app

# 複製依賴文件
COPY pyproject.toml uv.lock ./

# 安裝依賴 (使用 --frozen 確保與 uv.lock 一致)
# 使用 --no-install-project 僅安裝依賴，方便快取
RUN uv sync --frozen --no-install-project --no-dev

# ----------------- 運行階段 -----------------
FROM python:3.12-slim-bookworm

WORKDIR /app

# 從 builder 階段複製虛擬環境
COPY --from=builder /app/.venv /app/.venv

# 複製程式碼
COPY bot.py ./
COPY cogs/ ./cogs/

# 設定環境變數
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# 啟動命令
CMD ["python", "bot.py"]
