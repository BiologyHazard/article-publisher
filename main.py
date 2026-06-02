"""
B站 专栏程序化发布工具 - 入口
==============================
将本地 Markdown 文章发布到 B站 创作中心草稿箱。

快速开始:
    python main.py articles/article1

首次运行会引导你输入 Cookie 信息并保存到 config.json。
"""

import sys
from bili_publisher import main

if __name__ == "__main__":
    main()
