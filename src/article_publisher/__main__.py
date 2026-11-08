"""
多平台文章发布工具入口。

平台作为一级子命令：
  uv run -m article_publisher bilibili markdown articles/article1/main.md
  uv run -m article_publisher bilibili lark <document_id>
  uv run -m article_publisher skland markdown articles/article1/main.md
  uv run -m article_publisher nga markdown articles/article1/main.md --fid 516
"""

import asyncio

from article_publisher.cli import cli


def main() -> None:
    asyncio.run(cli())


if __name__ == "__main__":
    main()
