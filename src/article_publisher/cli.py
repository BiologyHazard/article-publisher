"""
命令行入口。

平台作为一级子命令，输入源作为二级子命令，平台专属选项各自隔离。

用法示例:
  uv run -m article_publisher bilibili markdown articles/article1/main.md
  uv run -m article_publisher bilibili lark <doc_id>
  uv run -m article_publisher skland markdown articles/article1/main.md
  uv run -m article_publisher nga markdown articles/article1/main.md --fid 516
  uv run -m article_publisher nga lark <doc_id> --fid 516
"""

import dataclasses
import json
import sys
from argparse import (
    ArgumentParser,
    Namespace,
    RawDescriptionHelpFormatter,
    _SubParsersAction,
)
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

from article_publisher._auth import (
    BILIBILI_REQUIRED_ENV_KEYS,
    LARK_REQUIRED_ENV_KEYS,
    NGA_REQUIRED_ENV_KEYS,
    SKLAND_REQUIRED_ENV_KEYS,
    load_bilibili_auth,
    load_lark_auth,
    load_nga_auth,
    load_skland_auth,
)
from article_publisher.converters.lark.converter import (
    LarkDocxConverter,
    cleanup_temp_images,
)
from article_publisher.converters.markdown import MarkdownConverter
from article_publisher.log import logger
from article_publisher.platforms.bilibili import (
    BiliClient,
    BiliPublishConfig,
    BiliPublisher,
)
from article_publisher.platforms.nga import NgaClient, NgaPublishConfig, NgaPublisher
from article_publisher.platforms.skland.client import SklandClient
from article_publisher.platforms.skland.publisher import (
    SklandPublishConfig,
    SklandPublisher,
)
lazy from article_publisher.document import Document

AUTH_HELP = """错误：缺少必要的环境变量

请在项目根目录创建 .env 文件，内容如下：
    BILIBILI_COOKIE="你的完整 Cookie 字符串"

飞书模式还需额外配置：
    LARK_APP_ID=你的飞书应用 App ID
    LARK_APP_SECRET=你的飞书应用 App Secret

获取方式：浏览器登录 B站后
  打开创作中心，按 F12 → Network（网络），刷新页面
  选择发送到 api.bilibili.com 的已登录请求 → Request Headers（请求标头）
  复制 Cookie 的完整值（不含 Cookie: 前缀），保留所有字段
  不要使用 document.cookie，它无法读取 HttpOnly 的 SESSDATA

飞书应用需在 https://open.feishu.cn/app 创建并获取凭据。"""

LARK_AUTH_HELP = """错误：缺少飞书应用认证配置
请在 .env 文件中添加：
    LARK_APP_ID=你的App ID
    LARK_APP_SECRET=你的 App Secret
获取方式：在飞书开发者平台 https://open.feishu.cn/app 创建应用后获取。"""

SKLAND_AUTH_HELP = """错误：缺少森空岛环境变量
请在 .env 文件中添加：
    HYPERGRYPH_TOKEN=你的鹰角网络认证 token
    SKLAND_DID=你的设备 ID
获取方式：浏览器登录森空岛后，
  在控制台执行：
    localStorage.getItem('SK_TOKEN_CACHE_KEY')  # 得到 token
    localStorage.getItem('hg_sdk_device_id')    # 得到 did"""

NGA_AUTH_HELP = """错误：缺少 NGA Cookie
请在 .env 文件中添加：
    NGA_COOKIE=你的完整 Cookie 字符串

获取方式：浏览器登录 NGA 后，
  按 F12 打开开发者工具 → Application（应用程序） → Cookies → https://ngabbs.com
  全选所有 Cookie 的 "Name=Value" 格式，复制粘贴到 .env 文件中。

  示例：NGA_COOKIE=ngaPassportUid=12345; ngacn0comUserInfo=...; ..."""


class CliError(Exception):
    """CLI 执行过程中可预见的错误，由 main() 统一捕获并调用 sys.exit(1)。"""

    pass


CST = timezone(timedelta(hours=8), name="中国标准时间")
"""中国标准时间（UTC+8）"""


def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        description="多平台文章发布工具", formatter_class=RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="platform", required=True, title="目标平台")

    # Bilibili
    bili = subparsers.add_parser("bilibili", help="发布到 B站专栏")
    _add_bilibili_options(bili)
    bili_subs = bili.add_subparsers(dest="source", required=True, title="输入源")
    _add_source_parsers(bili_subs)

    # 森空岛
    skland = subparsers.add_parser("skland", help="发布到森空岛")
    _add_skland_options(skland)
    skland_subs = skland.add_subparsers(dest="source", required=True, title="输入源")
    _add_source_parsers(skland_subs)

    # NGA
    nga = subparsers.add_parser("nga", help="发布到 NGA")
    _add_nga_options(nga)
    nga_subs = nga.add_subparsers(dest="source", required=True, title="输入源")
    _add_source_parsers(nga_subs)

    return parser


def _add_source_parsers(subparsers: _SubParsersAction) -> None:
    """为指定平台创建 markdown 和 lark 两个输入源子命令"""
    md = subparsers.add_parser(
        "markdown", aliases=["md"], help="从本地 Markdown 文件发布"
    )
    md.add_argument(
        "file", help="Markdown 文件路径（图片路径相对于该文件所在目录解析）"
    )

    lark = subparsers.add_parser("lark", help="从飞书云文档发布")
    lark.add_argument("doc_id", help="飞书云文档 ID")


def _add_bilibili_options(parser: ArgumentParser) -> None:
    """添加 B站 专栏发布专属选项。"""
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
    parser.add_argument("--cover", type=str, default=None, help="自定义封面图片路径")
    parser.add_argument(
        "--publish-time",
        type=str,
        default=None,
        help="定时发布时间（UTC+8），格式：YYYY-MM-DD HH:MM",
    )
    parser.add_argument(
        "--list-id", type=int, default=0, help="文集 ID（0=不加入文集）"
    )
    parser.add_argument(
        "--hashtags", type=str, default=None, help="话题 ID，逗号分隔，如：123,456"
    )
    parser.add_argument("--dry-run", action="store_true", help="仅转换不发布")
    parser.add_argument(
        "--update", type=int, default=None, help="更新已有草稿（传入草稿 ID）"
    )
    parser.add_argument(
        "--edit", type=int, default=None, help="编辑已发布文章（传入文章 ID）"
    )


def _add_skland_options(parser: ArgumentParser) -> None:
    """添加森空岛发布专属选项。"""
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
    parser.add_argument("--cover", type=str, default=None, help="自定义封面图片路径")
    parser.add_argument("--publish-time", type=str, default=None, help="定时发布时间戳")
    parser.add_argument("--dry-run", action="store_true", help="仅转换不发布")
    parser.add_argument(
        "--item-id", type=str, default=None, help="编辑已发布文章（传入文章 ID）"
    )


def _add_nga_options(parser: ArgumentParser) -> None:
    """添加 NGA 发布专属选项。"""
    parser.add_argument(
        "--fid",
        type=str,
        required=True,
        help="版块 ID（如 516=王者荣耀），从版块 URL 中获取",
    )
    parser.add_argument(
        "--tid",
        type=str,
        default=None,
        help="主题 ID（编辑已有帖子时传入，如 46944820）",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅转换不发布")


def _parse_publish_time(text: str) -> int:
    """将 'YYYY-MM-DD HH:MM' 格式的时间字符串转为 UTC 时间戳。"""
    dt = datetime.strptime(text, "%Y-%m-%d %H:%M").astimezone(CST)
    return int(dt.timestamp())


async def cli() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # 创建 converter
    try:
        if args.source in ("markdown", "md"):
            converter = _get_markdown_converter(markdown_file_path=Path(args.file))
        elif args.source == "lark":
            converter = _get_lark_converter(doc_id=args.doc_id)
        else:
            raise ValueError(f"未知输入源: {args.source}")

        # 转换内容为 Document 对象
        logger.info("正在转换内容 ...")
        doc = await converter.convert()
        logger.info(f"转换完成，共 {len(doc.blocks)} 个段落")
        logger.info(f"标题: {doc.title}")

        # dry-run 模式下打印 converter 处理后的完整中间表示
        if args.dry_run:
            logger.info("=" * 60)
            logger.info("  [dry-run] Converter IR Document 预览：")
            logger.info("=" * 60)
            print(json.dumps(dataclasses.asdict(doc), ensure_ascii=False, indent=2))
            logger.info("=" * 60)

        # 根据平台创建 publisher 并发布
        if args.platform == "bilibili":
            await _run_bilibili(doc, args)
        elif args.platform == "skland":
            await _run_skland(doc, args)
        elif args.platform == "nga":
            await _run_nga(doc, args)
        else:
            raise ValueError(f"未知平台: {args.platform}")
    except CliError:
        sys.exit(1)
    finally:
        if args.source == "lark":
            await _cleanup_lark(cast("LarkDocxConverter", converter))


async def _cleanup_lark(converter: LarkDocxConverter) -> None:
    """关闭飞书客户端连接，并清理飞书转换器产生的临时图片目录。"""

    await converter.close()
    cleanup_temp_images()


async def _run_bilibili(doc: Document, args: Namespace) -> None:
    """B站 发布流程：设置认证、封面、配置，然后发布。"""

    # 加载认证
    cfg = load_bilibili_auth()
    missing = [k for k in BILIBILI_REQUIRED_ENV_KEYS if k not in cfg]
    if missing:
        logger.error(AUTH_HELP)
        raise CliError()

    # 构建配置
    # 检查编辑模式
    if args.edit and args.update:
        logger.error("错误：--edit 和 --update 不能同时使用")
        raise CliError()

    config = BiliPublishConfig(
        category_id=args.category,
        article_id=args.update,
        edit_article_id=args.edit,
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
        cover_path=Path(args.cover).resolve() if args.cover else None,
    )

    try:
        client = BiliClient(cookie_str=cfg["BILIBILI_COOKIE"])
    except ValueError as exc:
        logger.error(str(exc))
        raise CliError() from exc

    async with client:
        publisher = BiliPublisher(client, config=config)
        await publisher.publish(doc, dry_run=args.dry_run)


async def _run_skland(doc: Document, args: Namespace) -> None:
    """森空岛 发布流程：设置认证、封面、配置，然后发布。"""

    cfg = load_skland_auth()
    missing = [k for k in SKLAND_REQUIRED_ENV_KEYS if k not in cfg]
    if missing:
        logger.error(SKLAND_AUTH_HELP)
        raise CliError()

    config = SklandPublishConfig(
        game_id=args.game_id,
        cate_id=args.cate_id,
        cover_path=Path(args.cover).resolve() if args.cover else None,
        publish_time=args.publish_time,
        item_id=args.item_id,
    )

    async with SklandClient(cfg["HYPERGRYPH_TOKEN"], cfg["SKLAND_DID"]) as client:
        publisher = SklandPublisher(client, config=config)
        await publisher.publish(doc, dry_run=args.dry_run)


async def _run_nga(doc: Document, args: Namespace) -> None:
    """NGA 发布流程：加载 Cookie、上传图片、生成 BBCode。"""

    cfg = load_nga_auth()
    missing = [k for k in NGA_REQUIRED_ENV_KEYS if k not in cfg]
    if missing:
        logger.error(NGA_AUTH_HELP)
        raise CliError()

    pid = article = None
    if args.tid is not None:
        pid = article = "0"  # 编辑已有帖子时，pid=0，article=0

    config = NgaPublishConfig(fid=args.fid, tid=args.tid, pid=pid, article=article)

    mode = "编辑" if args.tid else "发布"
    logger.info(f"NGA {mode}模式 (tid={args.tid if args.tid else '新帖'})")

    async with NgaClient(cookie_str=cfg["NGA_COOKIE"], fid=args.fid) as client:
        publisher = NgaPublisher(client, config=config)
        await publisher.publish(doc, dry_run=args.dry_run)


def _get_markdown_converter(markdown_file_path: Path) -> MarkdownConverter:
    """创建 Markdown 转换器。"""
    if not markdown_file_path.is_file():
        logger.error(f"错误：文件不存在: {markdown_file_path}")
        raise CliError()

    logger.info(f"📄 Markdown 文件: {markdown_file_path}")
    return MarkdownConverter(markdown_file_path)


def _get_lark_converter(doc_id: str) -> LarkDocxConverter:
    """创建飞书云文档转换器。"""
    cfg = load_lark_auth()
    missing = [k for k in LARK_REQUIRED_ENV_KEYS if k not in cfg]
    if missing:
        logger.error(LARK_AUTH_HELP)
        raise CliError()

    logger.info(f"📄 飞书云文档: {doc_id}")
    return LarkDocxConverter(
        app_id=cfg["LARK_APP_ID"], app_secret=cfg["LARK_APP_SECRET"], document_id=doc_id
    )
