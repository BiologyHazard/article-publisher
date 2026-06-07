"""
命令行入口。

支持两种模式:
  1. Markdown 模式: python -m bilibili_article markdown <article_dir>
  2. 飞书云文档模式: python -m bilibili_article lark <document_id>
"""

import sys
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import assert_never

from bilibili_article._auth import REQUIRED_ENV, load_auth, load_lark_auth
from bilibili_article.client import BiliApiError, BiliClient
from bilibili_article.converters.lark import LarkDocxConverter
from bilibili_article.converters.markdown import MarkdownConverter
from bilibili_article.log import logger
from bilibili_article.publisher import PublishConfig, publish_article

AUTH_HELP = """错误：缺少必要的环境变量

请在项目根目录创建 .env 文件，内容如下：
    SESSDATA=你的 SESSDATA 值
    bili_jct=你的 bili_jct 值
    buvid3=你的 buvid3 值

飞书模式还需额外配置：
    LARK_APP_ID=你的飞书应用 App ID
    LARK_APP_SECRET=你的飞书应用 App Secret

获取方式：浏览器登录 B站后
  按 F12 打开开发者工具 → Application（应用程序） → Cookie → https://*.bilibili.com
  复制 SESSDATA、bili_jct、buvid3 三个字段的值

飞书应用需在 https://open.feishu.cn/app 创建并获取凭据。"""

LARK_AUTH_HELP = """错误：缺少飞书应用认证配置
请在 .env 文件中添加：
    LARK_APP_ID=你的App ID
    LARK_APP_SECRET=你的 App Secret
获取方式：在飞书开发者平台 https://open.feishu.cn/app 创建应用后获取。"""

CST = timezone(timedelta(hours=8), name="中国标准时间")
"""中国标准时间（UTC+8）"""


def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        description="B站专栏文章发布工具",
        formatter_class=RawDescriptionHelpFormatter,
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
    dt = datetime.strptime(text, "%Y-%m-%d %H:%M").astimezone(CST)
    return int(dt.timestamp())


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # 构建统一配置
    config = PublishConfig(
        category_id=args.category,
        article_id=args.update,
        private_pub=1 if args.private else 2,
        reprint=1,
        original=1 if args.original else 0,
        comment_selected=1 if args.select_comments else 0,
        up_closed_reply=1 if args.close_comments else 0,
        timer_pub_time=_parse_publish_time(args.publish_time)
        if args.publish_time
        else 0,
        list_id=args.list_id,
        is_aigc=1 if args.aigc else 0,
        hashtag_ids=(
            [int(x) for x in args.hashtags.split(",") if x] if args.hashtags else None
        ),
    )

    # 加载 B站认证
    cfg = load_auth()
    missing = [k for k in REQUIRED_ENV if k not in cfg]
    if missing:
        logger.error(AUTH_HELP)
        sys.exit(1)

    client = BiliClient(cfg["SESSDATA"], cfg["bili_jct"], cfg["buvid3"])

    # 上传封面图
    cover_path = Path(args.cover).resolve() if args.cover else None
    if args.dry_run and cover_path:
        logger.info(f"[dry-run] 跳过封面上传: {cover_path}")
    elif cover_path:
        logger.info(f"上传封面图: {cover_path}")
        image_info = client.upload_image(cover_path)
        config.image_urls = [image_info["url"]]
        logger.info(f"  → {image_info['url']}")

    try:
        if args.mode in ("markdown", "md"):
            converter = _get_markdown_converter(
                client,
                markdown_file_path=Path(args.markdown_file),
                dry_run=args.dry_run,
            )
        elif args.mode == "lark":
            converter = _get_lark_converter(
                client,
                doc_id=args.doc_id,
                dry_run=args.dry_run,
            )
        else:
            assert_never(args.mode)

        publish_article(
            client=client, converter=converter, dry_run=args.dry_run, config=config
        )
    except BiliApiError as e:
        logger.error(f"❌ API 错误 [{e.code}]: {e.message}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 运行时错误: {e}")
        sys.exit(1)


def _get_markdown_converter(
    client: BiliClient,
    markdown_file_path: Path,
    *,
    dry_run: bool,
) -> MarkdownConverter:
    """Markdown 模式：处理本地 Markdown 文件。"""

    if not markdown_file_path.is_file():
        logger.error(f"错误：文件不存在: {markdown_file_path}")
        sys.exit(1)

    logger.info(f"📄 Markdown 文件: {markdown_file_path}")

    return MarkdownConverter(client, markdown_file_path, dry_run=dry_run)


def _get_lark_converter(
    client: BiliClient,
    doc_id: str,
    *,
    dry_run: bool,
) -> LarkDocxConverter:
    """飞书云文档模式：从飞书文档 ID 导入。"""

    lark_cfg = load_lark_auth()
    if "LARK_APP_ID" not in lark_cfg or "LARK_APP_SECRET" not in lark_cfg:
        logger.error(LARK_AUTH_HELP)
        sys.exit(1)

    logger.info(f"📄 飞书云文档: {doc_id}")

    return LarkDocxConverter(
        app_id=lark_cfg["LARK_APP_ID"],
        app_secret=lark_cfg["LARK_APP_SECRET"],
        document_id=doc_id,
        bili_client=client,
        dry_run=dry_run,
    )
