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
    markdown_parser = subparsers.add_parser(
        "markdown",
        aliases=["md"],
        help="从本地 Markdown 文件发布",
        description="从本地 Markdown 文件发布专栏文章",
    )
    markdown_parser.add_argument(
        "markdown_file",
        help="Markdown 文件路径（图片路径相对于该文件所在目录解析）",
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

    # 文章元信息
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
    parser.add_argument(
        "--close-comments",
        action="store_true",
        help="关闭评论",
    )
    parser.add_argument(
        "--select-comments",
        action="store_true",
        help="开启精选评论",
    )
    parser.add_argument(
        "--no-original",
        action="store_false",
        dest="original",
        help="不声明为原创",
    )
    parser.add_argument(
        "--aigc",
        action="store_true",
        help="声明内容包含 AI 辅助创作",
    )
    parser.add_argument(
        "--cover",
        type=str,
        default=None,
        help="自定义封面图片路径",
    )
    parser.add_argument(
        "--publish-time",
        type=str,
        default=None,
        help=(
            "定时发布时间（UTC+8），格式：YYYY-MM-DD HH:MM，"
            "最早为当前时间 +2 小时，最晚为 7 天内"
        ),
    )
    parser.add_argument(
        "--list-id",
        type=int,
        default=0,
        help="文集 ID（0=不加入文集）",
    )
    parser.add_argument(
        "--hashtags",
        type=str,
        default=None,
        help="话题 ID，逗号分隔，如：123,456",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅转换并输出 payload，不保存到草稿箱",
    )
    parser.add_argument(
        "--update",
        type=int,
        default=None,
        metavar="ARTICLE_ID",
        help="更新已有草稿（传入草稿 ID）",
    )

    return parser


def _parse_publish_time(text: str) -> int:
    """将 'YYYY-MM-DD HH:MM' 格式的时间字符串转为 UTC 时间戳。"""
    import datetime

    dt = datetime.datetime.strptime(text, "%Y-%m-%d %H:%M").astimezone()
    # 用户输入的是北京时间 (UTC+8)，转为 UTC 时间戳
    dt_utc = dt.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
    return int(dt_utc.timestamp())


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    category_id = args.category
    private_pub = 1 if args.private else 2
    up_closed_reply = 1 if args.close_comments else 0
    comment_selected = 1 if args.select_comments else 0
    original = 1 if args.original else 0
    is_aigc = 1 if args.aigc else 0
    timer_pub_time = _parse_publish_time(args.publish_time) if args.publish_time else 0
    hashtag_ids = (
        [int(x) for x in args.hashtags.split(",") if x] if args.hashtags else None
    )
    article_id = args.update

    #  加载 B站认证
    cfg = load_auth()
    missing = [k for k in REQUIRED_ENV if k not in cfg]
    if missing:
        print(AUTH_HELP)
        sys.exit(1)

    client = BiliClient(cfg["SESSDATA"], cfg["bili_jct"], cfg["buvid3"])

    # 上传封面图
    image_urls: list[str] | None = None
    if args.dry_run and args.cover:
        print(f"  [dry-run] 跳过封面上传: {args.cover}")
    elif args.cover:
        print(f"  上传封面图: {args.cover}")
        image_info = client.upload_image(args.cover)
        image_urls = [image_info["url"]]
        print(f"    → {image_info['url']}")

    try:
        if args.mode in ("lark",):
            _run_lark(
                client,
                args.doc_id,
                dry_run=args.dry_run,
                category_id=category_id,
                private_pub=private_pub,
                up_closed_reply=up_closed_reply,
                comment_selected=comment_selected,
                original=original,
                timer_pub_time=timer_pub_time,
                list_id=args.list_id,
                image_urls=image_urls,
                is_aigc=is_aigc,
                hashtag_ids=hashtag_ids,
                article_id=article_id,
            )
        else:  # markdown / md
            _run_markdown(
                client,
                args.markdown_file,
                dry_run=args.dry_run,
                category_id=category_id,
                private_pub=private_pub,
                up_closed_reply=up_closed_reply,
                comment_selected=comment_selected,
                original=original,
                timer_pub_time=timer_pub_time,
                list_id=args.list_id,
                image_urls=image_urls,
                is_aigc=is_aigc,
                hashtag_ids=hashtag_ids,
                article_id=article_id,
            )
    except BiliApiError as e:
        print(f"\n❌ API 错误 [{e.code}]: {e.message}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 运行时错误: {e}")
        sys.exit(1)


def _run_markdown(
    client: BiliClient,
    markdown_file: str,
    *,
    dry_run: bool = False,
    category_id: int = 15,
    private_pub: int = 2,
    up_closed_reply: int = 0,
    comment_selected: int = 0,
    original: int = 0,
    timer_pub_time: int = 0,
    list_id: int = 0,
    image_urls: list[str] | None = None,
    is_aigc: int = 0,
    hashtag_ids: list[int] | None = None,
    article_id: int | None = None,
) -> None:
    """Markdown 模式：处理本地 Markdown 文件。"""
    md_path = os.path.abspath(markdown_file)
    if not os.path.isfile(md_path):
        print(f"错误：文件不存在: {md_path}")
        sys.exit(1)

    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    # 从 Markdown 提取标题
    import re

    title_match = re.search(r"^#\s+(.*)", md_content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "未命名文章"

    base_dir = os.path.dirname(md_path)

    print(f"\n📄 文件: {md_path}")
    print("-" * 40)

    converter = MarkdownConverter(client, base_dir, md_content, dry_run=dry_run)

    result = publish_article(
        client=client,
        converter=converter,
        title=title,
        category_id=category_id,
        private_pub=private_pub,
        up_closed_reply=up_closed_reply,
        comment_selected=comment_selected,
        original=original,
        timer_pub_time=timer_pub_time,
        list_id=list_id,
        image_urls=image_urls,
        is_aigc=is_aigc,
        hashtag_ids=hashtag_ids,
        article_id=article_id,
        dry_run=dry_run,
    )
    if not dry_run:
        _print_success(result)


def _run_lark(
    client: BiliClient,
    doc_id: str,
    *,
    dry_run: bool = False,
    category_id: int = 15,
    private_pub: int = 2,
    up_closed_reply: int = 0,
    comment_selected: int = 0,
    original: int = 0,
    timer_pub_time: int = 0,
    list_id: int = 0,
    image_urls: list[str] | None = None,
    is_aigc: int = 0,
    hashtag_ids: list[int] | None = None,
    article_id: int | None = None,
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
        dry_run=dry_run,
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
        up_closed_reply=up_closed_reply,
        comment_selected=comment_selected,
        original=original,
        timer_pub_time=timer_pub_time,
        list_id=list_id,
        image_urls=image_urls,
        is_aigc=is_aigc,
        hashtag_ids=hashtag_ids,
        article_id=article_id,
        dry_run=dry_run,
    )
    if not dry_run:
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
