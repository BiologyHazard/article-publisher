"""
认证配置加载。

从 .env 文件或系统环境变量加载 B站 认证信息。
"""

import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

REQUIRED_ENV = ("SESSDATA", "bili_jct", "buvid3")

SKLAND_REQUIRED_ENV = ("HYPERGRYPH_TOKEN", "SKLAND_DID")

NGA_REQUIRED_ENV = ("NGA_COOKIE",)
"""NGA 发布所需的认证环境变量。

NGA_COOKIE: 完整的 Cookie 字符串，从浏览器 F12 → Application → Cookies
中复制所有以 nga.cn 为域名的 Cookie（格式如 "key1=value1; key2=value2"）。
"""


def load_auth() -> dict[str, str]:
    """从 .env 文件或系统环境变量加载 B站 认证配置。"""
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


def load_skland_auth() -> dict[str, str]:
    """从 .env 文件或系统环境变量加载森空岛认证配置。"""
    cfg: dict[str, str] = {}
    for key in SKLAND_REQUIRED_ENV:
        val = os.environ.get(key, "").strip()
        if val:
            cfg[key] = val
    return cfg


def load_nga_auth() -> dict[str, str]:
    """从 .env 文件或系统环境变量加载 NGA 认证配置。"""
    cfg: dict[str, str] = {}
    for key in NGA_REQUIRED_ENV:
        val = os.environ.get(key, "").strip()
        if val:
            cfg[key] = val
    return cfg
