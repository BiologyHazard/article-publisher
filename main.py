"""
B站 Opus 专栏自动发布工具

将本地 Markdown 文章发布到 B站 创作中心草稿箱。

用法:
    uv run python main.py articles/article1

前置条件:
    在 .env 文件中配置 SESSDATA、bili_jct、buvid3
    或通过系统环境变量设置上述三项。
"""

from bili_publisher import main

if __name__ == "__main__":
    main()
