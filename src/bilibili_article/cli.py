"""
命令行入口。

支持两种模式:
  1. Markdown 模式: python -m bilibili_article articles/article1
  2. 飞书云文档模式: python -m bilibili_article --lark <document_id>
"""

import os
import sys

from bilibili_article._auth import load_auth, load_lark_auth
from bilibili_article.client import BiliApiError, BiliClient
from bilibili_article.converters.lark import LarkDocxConverter
from bilibili_article.converters.markdown import MarkdownConverter
from bilibili_article.publisher import publish_article

REQUIRED_ENV = ("SESSDATA", "bili_jct", "buvid3")


def _print_auth_help() -> None:
    print("错误：缺少必要的环境变量")
    print()
    print("请在项目根目录创建 .env 文件，内容如下：")
    print()
    print("    SESSDATA=你的SESSDATA值")
    print("    bili_jct=你的bili_jct值")
    print("    buvid3=你的buvid3值")
    print()
    print("飞书模式还需额外配置：")
    print("    LARK_APP_ID=你的飞书应用App ID")
    print("    LARK_APP_SECRET=你的飞书应用App Secret")
    print()
    print("获取方式：浏览器登录 B站 后")
    print("  F12 → Application → Cookies → bilibili.com")
    print("  复制 SESSDATA、bili_jct、buvid3 三个字段的值")
    print()
    print("飞书应用需在 https://open.feishu.cn/app 创建并获取凭据。")
    sys.exit(1)


def _print_usage() -> None:
    print("用法:")
    print("  Markdown 模式:")
    print("    uv run python -m bilibili_article articles/article1")
    print()
    print("  飞书云文档模式:")
    print("    uv run python -m bilibili_article --lark <document_id>")
    print()
    print("参数:")
    print("  --lark, -l    使用飞书云文档模式，后跟文档 ID")
    print("  --category    分区 ID (默认 15=生活)")
    print("  --private     设为仅自己可见 (默认 2=公开)")
    sys.exit(1)


def main() -> None:
    # ---- 解析命令行参数 ----
    args = sys.argv[1:]
    if not args:
        _print_usage()

    lark_mode = False
    lark_doc_id: str | None = None
    category_id = 15
    private_pub = 2

    i = 0
    while i < len(args):
        if args[i] in ("--lark", "-l"):
            lark_mode = True
            i += 1
            if i < len(args) and not args[i].startswith("-"):
                lark_doc_id = args[i]
                i += 1
        elif args[i] == "--category":
            i += 1
            if i < len(args):
                category_id = int(args[i])
                i += 1
        elif args[i] == "--private":
            private_pub = 1
            i += 1
        else:
            # 位置参数：文章目录 (Markdown 模式) 或 doc_id (lark 模式)
            if lark_mode and lark_doc_id is None:
                lark_doc_id = args[i]
            elif not lark_mode:
                break  # 作为 article_dir 在循环外处理
            i += 1

    # ---- 加载 B站 认证 ----
    cfg = load_auth()
    missing = [k for k in REQUIRED_ENV if k not in cfg]
    if missing:
        _print_auth_help()

    client = BiliClient(cfg["SESSDATA"], cfg["bili_jct"], cfg["buvid3"])

    try:
        if lark_mode:
            _run_lark(client, lark_doc_id, category_id, private_pub)
        else:
            _run_markdown(client, args, category_id, private_pub)
    except BiliApiError as e:
        print(f"\n❌ API 错误 [{e.code}]: {e.message}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 运行时错误: {e}")
        sys.exit(1)


def _run_markdown(
    client: BiliClient,
    args: list[str],
    category_id: int,
    private_pub: int,
) -> None:
    """Markdown 模式：处理本地文章目录。"""
    if not args:
        print("错误：请指定文章目录")
        print("示例: uv run python -m bilibili_article articles/article1")
        sys.exit(1)

    article_dir = os.path.abspath(args[0])
    if not os.path.isdir(article_dir):
        print(f"错误：目录不存在: {article_dir}")
        sys.exit(1)

    md_path = os.path.join(article_dir, "main.md")
    if not os.path.isfile(md_path):
        raise FileNotFoundError(f"找不到 main.md: {md_path}")

    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    # 从 Markdown 提取标题
    import re

    title_match = re.search(r"^#\s+(.*)", md_content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "未命名文章"

    print(f"\n📄 专栏: {article_dir}")
    print("-" * 40)

    converter = MarkdownConverter(client, article_dir)
    payload_path = os.path.join(article_dir, "payload.json")

    result = publish_article(
        client=client,
        converter=converter,
        title=title,
        category_id=category_id,
        private_pub=private_pub,
        payload_path=payload_path,
    )
    _print_success(result)


def _run_lark(
    client: BiliClient,
    doc_id: str | None,
    category_id: int,
    private_pub: int,
) -> None:
    """飞书云文档模式：从飞书文档 ID 导入。"""
    if not doc_id:
        print("错误：请提供飞书文档 ID")
        print(
            "示例: uv run python -m bilibili_article --lark UXiMw9NeNiH3ypkyaXmc5VR7nvc"
        )
        sys.exit(1)

    lark_cfg = load_lark_auth()
    if "LARK_APP_ID" not in lark_cfg or "LARK_APP_SECRET" not in lark_cfg:
        print("错误：缺少飞书应用认证配置")
        print("请在 .env 文件中添加：")
        print("    LARK_APP_ID=你的App ID")
        print("    LARK_APP_SECRET=你的App Secret")
        sys.exit(1)

    print(f"\n📄 飞书文档: {doc_id}")
    print("-" * 40)

    converter = LarkDocxConverter(
        app_id=lark_cfg["LARK_APP_ID"],
        app_secret=lark_cfg["LARK_APP_SECRET"],
        document_id=doc_id,
        bili_client=client,
    )

    # 获取标题
    doc_info = converter.fetch_document_info()
    title = doc_info.get("title", "未命名文章")
    print(f"  标题: {title}")

    result = publish_article(
        client=client,
        converter=converter,
        title=title,
        category_id=category_id,
        private_pub=private_pub,
    )
    _print_success(result)


def _print_success(result: dict) -> None:
    aid = result["data"]["article_id"]
    print(f"\n✅ 完成！草稿 ID: {aid}")
    print(
        f"   可在创作中心查看: "
        f"https://member.bilibili.com/platform/upload/text/new-edit"
        f"?aid={aid}"
    )


if __name__ == "__main__":
    main()
