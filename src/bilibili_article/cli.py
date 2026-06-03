"""
命令行入口。

支持两种模式:
  1. Markdown 模式: python -m bilibili_article markdown <article_dir>
  2. 飞书云文档模式: python -m bilibili_article lark <document_id>
"""

import argparse
import os
import sys

from bilibili_article._auth import load_auth, load_lark_auth
from bilibili_article.client import BiliApiError, BiliClient
from bilibili_article.converters.lark import LarkDocxConverter
from bilibili_article.converters.markdown import MarkdownConverter
from bilibili_article.publisher import publish_article

REQUIRED_ENV = ("SESSDATA", "bili_jct", "buvid3")

AUTH_HELP = """错误：缺少必要的环境变量

请在项目根目录创建 .env 文件，内容如下：

    SESSDATA=你的 SESSDATA 值
    bili_jct=你的 bili_jct 值
    buvid3=你的 buvid3 值

飞书模式还需额外配置：
    LARK_APP_ID=你的飞书应用 App ID
    LARK_APP_SECRET=你的飞书应用 App Secret

获取方式：浏览器登录 B站后
  F12 → Application → Cookies → bilibili.com
  复制 SESSDATA、bili_jct、buvid3 三个字段的值

飞书应用需在 https://open.feishu.cn/app 创建并获取凭据。"""

LARK_AUTH_HELP = """错误：缺少飞书应用认证配置
请在 .env 文件中添加：
    LARK_APP_ID=你的App ID
    LARK_APP_SECRET=你的 App Secret
获取方式：在飞书开发者平台 https://open.feishu.cn/app 创建应用后获取。"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="B站专栏文章发布工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="mode", required=True, title="模式")

    # Markdown 子命令
    md_parser = subparsers.add_parser(
        "markdown",
        aliases=["md"],
        help="从本地 Markdown 文件发布",
        description="从本地 Markdown 目录发布专栏文章",
    )
    md_parser.add_argument(
        "article_dir",
        help="文章目录（须包含 main.md 和 images/ 子目录）",
    )

    # 飞书云文档子命令
    lark_parser = subparsers.add_parser(
        "lark",
        help="从飞书云文档发布",
        description="从飞书云文档导入并发布专栏文章",
    )
    lark_parser.add_argument(
        "doc_id",
        help="飞书云文档 ID",
    )

    # 公共选项
    parser.add_argument(
        "--category",
        type=int,
        default=15,
        help="分区 ID（默认 15 = 生活）",
    )
    parser.add_argument(
        "--private",
        action="store_true",
        help="设为仅自己可见",
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    category_id = args.category
    private_pub = 1 if args.private else 2

    #  加载 B站认证
    cfg = load_auth()
    missing = [k for k in REQUIRED_ENV if k not in cfg]
    if missing:
        print(AUTH_HELP)
        sys.exit(1)

    client = BiliClient(cfg["SESSDATA"], cfg["bili_jct"], cfg["buvid3"])

    try:
        if args.mode in ("lark",):
            _run_lark(client, args.doc_id, category_id, private_pub)
        else:  # markdown / md
            _run_markdown(client, args.article_dir, category_id, private_pub)
    except BiliApiError as e:
        print(f"\n❌ API 错误 [{e.code}]: {e.message}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 运行时错误: {e}")
        sys.exit(1)


def _run_markdown(
    client: BiliClient,
    article_dir: str,
    category_id: int,
    private_pub: int,
) -> None:
    """Markdown 模式：处理本地文章目录。"""
    article_dir = os.path.abspath(article_dir)
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
    doc_id: str,
    category_id: int,
    private_pub: int,
) -> None:
    """飞书云文档模式：从飞书文档 ID 导入。"""
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

    payload_path = f"payload_lark_{doc_id}.json"

    result = publish_article(
        client=client,
        converter=converter,
        title=title,
        category_id=category_id,
        private_pub=private_pub,
        payload_path=payload_path,
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
