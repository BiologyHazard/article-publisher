"""
多平台文章发布工具入口。

一级子命令表示能力域：
  uv run -m article_publisher publish bilibili markdown articles/article1/main.md
  uv run -m article_publisher publish bilibili lark <document_id>
  uv run -m article_publisher publish skland markdown articles/article1/main.md
  uv run -m article_publisher publish nga markdown articles/article1/main.md --fid 516
  uv run -m article_publisher cache dir|size|clean
"""

import asyncio
import sys

from article_publisher.cli import cli
from article_publisher.errors import CliError
from article_publisher.log import logger


def main() -> None:
    try:
        asyncio.run(cli())
    except CliError as exc:
        logger.error(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
