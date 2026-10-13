"""请求元信息：请求 ID 与限流用的客户端标识。

三处路由（collate / analyze / compare）此前各自抄了一份同名私有函数；重复的代价不是
代码量，而是**改动容易漏一处**（比如给反代加一层取 IP 的规则）。抽到这里做唯一副本。
"""

from __future__ import annotations

import secrets
from datetime import datetime

from fastapi import Request


def new_request_id() -> str:
    """形如 req_20261013_ab12cd。形状见 API.md 各端点响应示例，便于日志检索。"""
    return f"req_{datetime.now().strftime('%Y%m%d')}_{secrets.token_hex(3)}"


def client_key(request: Request) -> str:
    """取客户端标识用于限流；部署在反向代理后时认 X-Forwarded-For 的第一跳。"""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
