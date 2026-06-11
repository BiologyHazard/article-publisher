from __future__ import annotations

from typing import TypedDict


class LarkApiResponse[T](TypedDict):
    """飞书 API 响应的通用数据结构。"""

    code: int
    msg: str
    data: T
