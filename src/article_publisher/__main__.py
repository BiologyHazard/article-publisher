"""
多平台文章发布工具入口。

支持两种输入源:
  1. 本地 Markdown 文章:  uv run -m article_publisher markdown articles/article1/main.md
  2. 飞书云文档:          uv run -m article_publisher lark <document_id>
"""

from article_publisher.cli import main

if __name__ == "__main__":
    main()
