"""
B站 Opus 专栏自动发布工具

支持两种输入源:
  1. 本地 Markdown 文章:  uv run python main.py articles/article1
  2. 飞书云文档:          uv run python main.py --lark <document_id>
"""

from bilibili_article.cli import main

if __name__ == "__main__":
    main()
