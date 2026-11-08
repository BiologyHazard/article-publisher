"""
森空岛命令行适配。

定义森空岛专属选项，并负责从命令行参数到 SklandPublisher 的发布流程。
"""

from pathlib import Path
lazy from argparse import ArgumentParser, Namespace

from article_publisher._auth import SKLAND_REQUIRED_ENV_KEYS, require_auth
from article_publisher.platforms.skland.client import SklandClient
from article_publisher.platforms.skland.publisher import (
    SklandPublishConfig,
    SklandPublisher,
)
lazy from article_publisher.document import Document

AUTH_HELP = """错误：缺少森空岛环境变量

请在 .env 文件中添加：
    HYPERGRYPH_TOKEN=你的鹰角网络认证 token
    SKLAND_DID=你的设备 ID

获取方式：浏览器登录森空岛后，
  在控制台执行：
    localStorage.getItem('SK_TOKEN_CACHE_KEY')  # 得到 token
    localStorage.getItem('hg_sdk_device_id')    # 得到 did"""


def add_options(parser: ArgumentParser) -> None:
    """添加森空岛专属选项。"""
    parser.add_argument(
        "--game-id",
        type=int,
        default=None,
        help="游戏分区（新草稿默认 1 = 明日方舟；编辑时默认保留原分区）",
    )
    parser.add_argument(
        "--cate-id",
        type=int,
        default=None,
        help="子分区（新草稿默认 4 = 攻略；编辑时默认保留原分区）",
    )
    parser.add_argument("--cover", type=Path, default=None, help="自定义封面图片路径")
    parser.add_argument("--publish-time", type=str, default=None, help="定时发布时间戳")
    parser.add_argument("--dry-run", action="store_true", help="仅转换不发布")
    parser.add_argument(
        "--item-id", type=str, default=None, help="编辑已发布文章（传入文章 ID）"
    )


async def run(doc: Document, args: Namespace) -> None:
    """森空岛发布流程：加载认证、构建配置、发布。"""
    cfg = require_auth(SKLAND_REQUIRED_ENV_KEYS, AUTH_HELP)

    config = SklandPublishConfig(
        game_id=args.game_id,
        cate_id=args.cate_id,
        cover_path=args.cover.resolve() if args.cover else None,
        publish_time=args.publish_time,
        item_id=args.item_id,
    )

    async with SklandClient(cfg["HYPERGRYPH_TOKEN"], cfg["SKLAND_DID"]) as client:
        publisher = SklandPublisher(client, config=config)
        await publisher.publish(doc, dry_run=args.dry_run)
