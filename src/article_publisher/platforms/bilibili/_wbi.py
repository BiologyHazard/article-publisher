"""
WBI 签名工具

用于 B站 API 请求的 WBI 签名。
"""

import hashlib
import time
import urllib.parse
from typing import Any

lazy import aiohttp

MIXIN_KEY_TABLE = [
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
]

BILI_API_BASE = "https://api.bilibili.com"


def get_mixin_key(raw: str) -> str:
    """对原始 key 字符串做重排，取前 32 位作为 mixin_key。"""
    return "".join(raw[i] for i in MIXIN_KEY_TABLE)[:32]


async def fetch_wbi_keys(session: aiohttp.ClientSession) -> tuple[str, str]:
    """从 /x/web-interface/nav 获取 WBI 的 img_key 和 sub_key。"""
    async with session.get(f"{BILI_API_BASE}/x/web-interface/nav") as response:
        data = await response.json()
    wbi_img = data["data"]["wbi_img"]
    img_key = wbi_img["img_url"].split("/")[-1].split(".")[0]
    sub_key = wbi_img["sub_url"].split("/")[-1].split(".")[0]
    return img_key, sub_key


def sign_wbi_params(params: dict[str, Any], mixin_key: str) -> dict[str, Any]:
    """为参数字典添加 wts 和 w_rid 签名，返回新字典。"""
    out = dict(params)
    out["wts"] = int(time.time())
    sorted_items = sorted(out.items())
    query = urllib.parse.urlencode({k: v for k, v in sorted_items if v is not None})
    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
    out["w_rid"] = w_rid
    return out
