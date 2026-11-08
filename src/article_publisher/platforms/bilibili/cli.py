"""
B站 命令行适配。

定义 B站 专属选项，并负责从命令行参数到 BiliPublisher 的完整发布流程。
"""

from argparse import ArgumentParser, ArgumentTypeError, Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from article_publisher._auth import BILIBILI_REQUIRED_ENV_KEYS, require_auth
from article_publisher.errors import CliError
from article_publisher.platforms.bilibili.client import BiliClient
from article_publisher.platforms.bilibili.publisher import (
    BiliPublishConfig,
    BiliPublisher,
)
lazy from article_publisher.document import Document

_CST = timezone(timedelta(hours=8), name="中国标准时间")
"""中国标准时间（UTC+8）。"""

AUTH_HELP = """错误：缺少 B站 Cookie

请在项目根目录创建 .env 文件，内容如下：
    BILIBILI_COOKIE="你的完整 Cookie 字符串"

获取方式：浏览器登录 B站后
  打开创作中心，按 F12 → Network（网络），刷新页面
  选择发送到 api.bilibili.com 的已登录请求 → Request Headers（请求标头）
  复制 Cookie 的完整值（不含 Cookie: 前缀），保留所有字段
  不要使用 document.cookie，它无法读取 HttpOnly 的 SESSDATA"""


def _publish_time(text: str) -> int:
    """将 UTC+8 的 'YYYY-MM-DD HH:MM' 解析为 UTC 时间戳。"""
    try:
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=_CST)
    except ValueError as exc:
        raise ArgumentTypeError(
            f"时间格式应为 'YYYY-MM-DD HH:MM'，收到 {text!r}"
        ) from exc
    return int(dt.timestamp())


def _hashtag_ids(text: str) -> list[int]:
    """将逗号分隔的话题 ID 字符串解析为整数列表。"""
    try:
        return [int(item) for item in text.split(",") if item.strip()]
    except ValueError as exc:
        raise ArgumentTypeError(f"话题 ID 必须为整数，收到 {text!r}") from exc


def add_options(parser: ArgumentParser) -> None:
    """添加 B站 专属选项。"""
    parser.add_argument(
        "--category", type=int, default=15, help="分区 ID（默认 15 = 生活）"
    )
    parser.add_argument("--private", action="store_true", help="设为仅自己可见")
    parser.add_argument("--close-comments", action="store_true", help="关闭评论")
    parser.add_argument("--select-comments", action="store_true", help="开启精选评论")
    parser.add_argument(
        "--no-original", action="store_false", dest="original", help="不声明为原创"
    )
    parser.add_argument("--aigc", action="store_true", help="声明内容包含 AI 辅助创作")
    parser.add_argument("--cover", type=Path, default=None, help="自定义封面图片路径")
    parser.add_argument(
        "--publish-time",
        type=_publish_time,
        default=0,
        metavar="'YYYY-MM-DD HH:MM'",
        help="定时发布时间（UTC+8）",
    )
    parser.add_argument(
        "--list-id", type=int, default=0, help="文集 ID（0=不加入文集）"
    )
    parser.add_argument(
        "--hashtags",
        type=_hashtag_ids,
        default=None,
        metavar="ID,ID,...",
        help="话题 ID，逗号分隔，如：123,456",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅转换不发布")

    target = parser.add_mutually_exclusive_group()
    target.add_argument(
        "--update", type=int, default=None, help="更新已有草稿（传入草稿 ID）"
    )
    target.add_argument(
        "--edit", type=int, default=None, help="编辑已发布文章（传入文章 ID）"
    )


async def run(doc: Document, args: Namespace) -> None:
    """B站 发布流程：加载认证、构建配置、发布。"""
    cfg = require_auth(BILIBILI_REQUIRED_ENV_KEYS, AUTH_HELP)

    config = BiliPublishConfig(
        category_id=args.category,
        article_id=args.update,
        edit_article_id=args.edit,
        private_pub=1 if args.private else 2,
        original=1 if args.original else 0,
        comment_selected=1 if args.select_comments else 0,
        up_closed_reply=1 if args.close_comments else 0,
        timer_pub_time=args.publish_time,
        list_id=args.list_id,
        is_aigc=1 if args.aigc else 0,
        hashtag_ids=args.hashtags,
        cover_path=args.cover.resolve() if args.cover else None,
    )

    try:
        client = BiliClient(cookie_str=cfg["BILIBILI_COOKIE"])
    except ValueError as exc:
        raise CliError(str(exc)) from exc

    async with client:
        publisher = BiliPublisher(client, config=config)
        await publisher.publish(doc, dry_run=args.dry_run)
