"""
认证配置加载。

从 .env 文件或系统环境变量加载 B站 认证信息。
"""

import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

REQUIRED_ENV = ("SESSDATA", "bili_jct", "buvid3")


def load_auth() -> dict[str, str]:
    """从 .env 文件或系统环境变量加载认证配置。"""
    cfg: dict[str, str] = {}
    for key in REQUIRED_ENV:
        val = os.environ.get(key, "").strip()
        if val:
            cfg[key] = val
    return cfg


def load_lark_auth() -> dict[str, str]:
    """从 .env 文件或系统环境变量加载飞书应用认证配置。"""
    cfg: dict[str, str] = {}
    for key in ("LARK_APP_ID", "LARK_APP_SECRET"):
        val = os.environ.get(key, "").strip()
        if val:
            cfg[key] = val
    return cfg
