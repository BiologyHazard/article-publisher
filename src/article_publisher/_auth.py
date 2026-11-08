"""
认证配置加载。

从 .env 文件或系统环境变量加载认证信息。
"""

import os
lazy from collections.abc import Iterable

from dotenv import find_dotenv, load_dotenv

from article_publisher.errors import CliError

load_dotenv(find_dotenv(usecwd=True))

LARK_REQUIRED_ENV_KEYS = ("LARK_APP_ID", "LARK_APP_SECRET")
BILIBILI_REQUIRED_ENV_KEYS = ("BILIBILI_COOKIE",)
SKLAND_REQUIRED_ENV_KEYS = ("HYPERGRYPH_TOKEN", "SKLAND_DID")
NGA_REQUIRED_ENV_KEYS = ("NGA_COOKIE",)


def load_auth(required_keys: Iterable[str]) -> dict[str, str]:
    """从 .env 文件或系统环境变量加载认证配置，忽略空白值。"""
    config: dict[str, str] = {}
    for key in required_keys:
        value = os.environ.get(key, "").strip()
        if value:
            config[key] = value
    return config


def require_auth(required_keys: Iterable[str], help_text: str) -> dict[str, str]:
    """加载认证配置；缺少任一必需项时抛出包含帮助信息的 CliError。"""
    keys = tuple(required_keys)
    config = load_auth(keys)
    if any(key not in config for key in keys):
        raise CliError(help_text)
    return config
