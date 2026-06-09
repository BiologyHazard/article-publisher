"""
命令行入口。

支持多平台发布，目前实现：
  - B站 (bilibili): 支持 markdown 和 lark 两种输入源
  - 森空岛 (skland): 支持 markdown 和 lark 两种输入源
  - NGA (nga): 支持 markdown 和 lark 两种输入源，生成 BBCode 供用户自行发布

用法示例:
  uv run -m article_publisher markdown articles/article1/main.md
  uv run -m article_publisher --platform bilibili lark <doc_id>
  uv run -m article_publisher --platform skland markdown articles/article1/main.md
  uv run -m article_publisher --platform nga markdown articles/article1/main.md
  uv run -m article_publisher --platform nga markdown articles/article1/main.md --fid 516
"""

import sys
from argparse import ArgumentParser, Namespace, RawDescriptionHelpFormatter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import assert_never

from article_publisher._auth import (
    NGA_REQUIRED_ENV,
    REQUIRED_ENV,
    SKLAND_REQUIRED_ENV,
    load_auth,
    load_lark_auth,
    load_nga_auth,
    load_skland_auth,
)
from article_publisher.converters.lark import LarkDocxConverter, cleanup_temp_images
from article_publisher.converters.markdown import MarkdownConverter
from article_publisher.document import Document
from article_publisher.log import logger
from article_publisher.platforms.bilibili import (
    BiliApiError,
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

  示例：NGA_COOKIE=ngaPassportUid=12345; ngacn0comUserInfo=...; ...

此外，还需要通过 --fid 参数指定目标版块 ID。
版块 ID 可以在版块 URL 中找到，如 https://ngabbs.com/thread.php?fid=516 中的 516。"""

CST = timezone(timedelta(hours=8), name="中国标准时间")
"""中国标准时间（UTC+8）"""


def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        description="多平台文章发布工具", formatter_class=RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "--platform",
        type=str,
        default="bilibili",
        choices=["bilibili", "skland", "nga"],
        help="目标平台（默认 bilibili）",
    )

    subparsers = parser.add_subparsers(dest="mode", required=True, title="模式")

    # Markdown 子命令
    markdown_parser = subparsers.add_parser(
        "markdown",
        aliases=["md"],
        help="从本地 Markdown 文件发布",
        description="从本地 Markdown 文件发布文章",
    )
    markdown_parser.add_argument(
        "markdown_file", help="Markdown 文件路径（图片路径相对于该文件所在目录解析）"
    )

    # 飞书云文档子命令
    lark_parser = subparsers.add_parser(
        "lark", help="从飞书云文档发布", description="从飞书云文档导入并发布文章"
    )
    lark_parser.add_argument("doc_id", help="飞书云文档 ID")

    # 文章元信息（B站特定选项）
    parser.add_argument(
        "--category", type=int, default=15, help="B站分区 ID（默认 15 = 生活）"
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
        help=(
            "定时发布时间（UTC+8），格式：YYYY-MM-DD HH:MM，"
            "最早为当前时间 +2 小时，最晚为 7 天内"
        ),
    )
    parser.add_argument(
        "--list-id", type=int, default=0, help="B站文集 ID（0=不加入文集）"
    )
    parser.add_argument(
        "--hashtags", type=str, default=None, help="话题 ID，逗号分隔，如：123,456"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="仅转换并输出 payload，不保存到草稿箱"
    )
    parser.add_argument(
        "--update", type=int, default=None, help="更新已有草稿（传入草稿 ID，仅 B站）"
    )

    # NGA 特定参数
    parser.add_argument(
        "--fid",
        type=str,
        default=None,
        help="NGA 版块 ID（如 516=王者荣耀），从版块 URL 中获取",
    )
    parser.add_argument(
        "--tid",
        type=str,
        default=None,
        help="NGA 主题 ID（编辑已有帖子时传入，如 46944820）",
    )

    return parser


def _parse_publish_time(text: str) -> int:
    """将 'YYYY-MM-DD HH:MM' 格式的时间字符串转为 UTC 时间戳。"""
    dt = datetime.strptime(text, "%Y-%m-%d %H:%M").astimezone(CST)
    return int(dt.timestamp())


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # 1. 创建 Converter
    # ------------------------------------------------------------------
    try:
        if args.mode in ("markdown", "md"):
            converter = _get_markdown_converter(
                markdown_file_path=Path(args.markdown_file)
            )
        elif args.mode == "lark":
            converter = _get_lark_converter(doc_id=args.doc_id)
        else:
            assert_never(args.mode)
    except Exception as e:
        logger.error(f"❌ 转换器初始化失败: {e}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 2. 转换内容为 IR Document
    # ------------------------------------------------------------------
    logger.info("正在转换内容 ...")
    doc = converter.convert()
    logger.info(f"转换完成，共 {len(doc.blocks)} 个段落")
    logger.info(f"标题: {doc.title}")

    # ------------------------------------------------------------------
    # 3. 根据目标平台创建 Publisher 并发布
    # ------------------------------------------------------------------
    platform = args.platform

    try:
        if platform == "bilibili":
            _run_bilibili(doc, args)
        elif platform == "skland":
            _run_skland(doc, args)
        elif platform == "nga":
            _run_nga(doc, args)
        else:
            assert_never(platform)
    finally:
        # 清理临时图片文件（仅飞书模式会产生）
        _cleanup_lark_temp_images(args.mode)


def _cleanup_lark_temp_images(mode: str) -> None:
    """清理飞书转换器产生的临时图片目录。"""
    if mode != "lark":
        return
    cleanup_temp_images()


def _run_bilibili(doc: Document, args: Namespace) -> None:
    """B站 发布流程：设置认证、封面、配置，然后发布。"""

    # 加载认证
    cfg = load_auth()
    missing = [k for k in REQUIRED_ENV if k not in cfg]
    if missing:
        logger.error(AUTH_HELP)
        sys.exit(1)

    client = BiliClient(cfg["SESSDATA"], cfg["bili_jct"], cfg["buvid3"])

    # 构建配置
    config = BiliPublishConfig(
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

    # 上传封面图
    _handle_cover(client, config, args)

    # 发布
    publisher = BiliPublisher(client, config=config)
    try:
        publisher.publish(doc, dry_run=args.dry_run)
    except BiliApiError as e:
        logger.error(f"❌ API 错误 [{e.code}]: {e.message}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 运行时错误: {e}")
        sys.exit(1)


def _run_skland(doc: Document, args: Namespace) -> None:
    """森空岛 发布流程：设置认证、封面、配置，然后发布。"""

    cfg = load_skland_auth()
    missing = [k for k in SKLAND_REQUIRED_ENV if k not in cfg]
    if missing:
        logger.error(SKLAND_AUTH_HELP)
        sys.exit(1)

    client = SklandClient(cfg["HYPERGRYPH_TOKEN"], cfg["SKLAND_DID"])

    config = SklandPublishConfig(
        cover_path=Path(args.cover).resolve() if args.cover else None,
        publish_time=args.publish_time,
    )

    publisher = SklandPublisher(client, config=config)
    try:
        publisher.publish(doc, dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"❌ 运行时错误: {e}")
        sys.exit(1)


def _run_nga(doc: Document, args: Namespace) -> None:
    """NGA 发布流程：加载 Cookie、上传图片、生成 BBCode。"""

    fid = args.fid
    if not fid:
        logger.error("NGA 模式需要指定 --fid 参数（版块 ID）")
        logger.info("版块 ID 可在版块 URL 中找到，如 thread.php?fid=516 中的 516")
        sys.exit(1)

    cfg = load_nga_auth()
    missing = [k for k in NGA_REQUIRED_ENV if k not in cfg]
    if missing:
        logger.error(NGA_AUTH_HELP)
        sys.exit(1)

    client = NgaClient(cookie_str=cfg["NGA_COOKIE"], fid=fid)
    config = NgaPublishConfig(fid=fid, tid=args.tid)
    publisher = NgaPublisher(client, config=config)

    mode = "编辑" if args.tid else "发布"
    logger.info(f"NGA {mode}模式 (tid={args.tid if args.tid else '新帖'})")

    try:
        publisher.publish(doc, dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"❌ 运行时错误: {e}")
        sys.exit(1)


def _handle_cover(
    client: BiliClient, config: BiliPublishConfig, args: Namespace
) -> None:
    """上传封面图到 B站 图床并更新配置。"""
    cover_path = Path(args.cover).resolve() if args.cover else None
    if args.dry_run and cover_path:
        logger.info(f"[dry-run] 跳过封面上传: {cover_path}")
    elif cover_path:
        logger.info(f"上传封面图: {cover_path}")
        image_info = client.upload_image(cover_path)
        config.image_urls = [image_info["url"]]
        logger.info(f"  → {image_info['url']}")


def _get_markdown_converter(markdown_file_path: Path) -> MarkdownConverter:
    """创建 Markdown 转换器。"""
    if not markdown_file_path.is_file():
        logger.error(f"错误：文件不存在: {markdown_file_path}")
        sys.exit(1)

    logger.info(f"📄 Markdown 文件: {markdown_file_path}")
    return MarkdownConverter(markdown_file_path)


def _get_lark_converter(doc_id: str) -> LarkDocxConverter:
    """创建飞书云文档转换器。"""
    lark_cfg = load_lark_auth()
    if "LARK_APP_ID" not in lark_cfg or "LARK_APP_SECRET" not in lark_cfg:
        logger.error(LARK_AUTH_HELP)
        sys.exit(1)

    logger.info(f"📄 飞书云文档: {doc_id}")
    return LarkDocxConverter(
        app_id=lark_cfg["LARK_APP_ID"],
        app_secret=lark_cfg["LARK_APP_SECRET"],
        document_id=doc_id,
    )
