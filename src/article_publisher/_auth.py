"""
认证配置加载。

从 .env 文件或系统环境变量加载认证信息。
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from dotenv import find_dotenv, load_dotenv

if TYPE_CHECKING:
    from collections.abc import Iterable

load_dotenv(find_dotenv(usecwd=True))

LARK_REQUIRED_ENV_KEYS = ["LARK_APP_ID", "LARK_APP_SECRET"]
BILIBILI_REQUIRED_ENV_KEYS = ["BILIBILI_COOKIE"]
SKLAND_REQUIRED_ENV_KEYS = ["HYPERGRYPH_TOKEN", "SKLAND_DID"]
NGA_REQUIRED_ENV_KEYS = ["NGA_COOKIE"]


def load_auth(required_keys: Iterable[str]) -> dict[str, str]:
    """从 .env 文件或系统环境变量加载认证配置。"""
    config: dict[str, str] = {}
    for key in required_keys:
        value = os.environ.get(key)
        if value is not None:
            config[key] = value
    return config


def load_lark_auth() -> dict[str, str]:
    """从 .env 文件或系统环境变量加载飞书应用认证配置。"""
    cfg: dict[str, str] = {}
    for key in LARK_REQUIRED_ENV_KEYS:
        val = os.environ.get(key, "").strip()
        if val:
            cfg[key] = val
    return cfg


def load_bilibili_auth() -> dict[str, str]:
    """从 .env 文件或系统环境变量加载 B站认证配置。"""
    cfg: dict[str, str] = {}
    for key in BILIBILI_REQUIRED_ENV_KEYS:
        val = os.environ.get(key, "").strip()
        if val:
            cfg[key] = val
    return cfg


def load_skland_auth() -> dict[str, str]:
    """从 .env 文件或系统环境变量加载森空岛认证配置。"""
    cfg: dict[str, str] = {}
    for key in SKLAND_REQUIRED_ENV_KEYS:
        val = os.environ.get(key)
        if val is not None:
            cfg[key] = val
    return cfg


def load_nga_auth() -> dict[str, str]:
    """从 .env 文件或系统环境变量加载 NGA 认证配置。"""
    cfg: dict[str, str] = {}
    for key in NGA_REQUIRED_ENV_KEYS:
        val = os.environ.get(key, "").strip()
        if val:
            cfg[key] = val
    return cfg
