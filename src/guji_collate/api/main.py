"""HTTP API 草案：FastAPI 应用。

启动：`uvicorn guji_collate.api.main:app --reload`（需先 `pip install -e ".[api]"`）
完整契约见 `docs/api.md`。
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="古籍文献智能校勘工具 API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# TODO: 注册各阶段路由
# - POST /api/v1/ocr          书页影像 -> 文本行
# - POST /api/v1/segment      文本 -> 断句
# - POST /api/v1/punctuate    断句 -> 标点
# - POST /api/v1/collate      底本 + 参校本 -> 校勘记
# - POST /api/v1/translate    原文 -> 文白翻译
