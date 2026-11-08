"""
命令行入口。

一级子命令表示能力域：`publish` 负责发布，`cache` 负责本地缓存维护；二级子命令细化到平台、输入源或具体操作。

用法示例:
  uv run -m article_publisher publish bilibili markdown articles/article1/main.md
  uv run -m article_publisher publish bilibili lark <doc_id>
  uv run -m article_publisher publish skland markdown articles/article1/main.md
  uv run -m article_publisher publish nga markdown articles/article1/main.md --fid 516
  uv run -m article_publisher publish nga lark <doc_id> --fid 516
  uv run -m article_publisher cache dir
  uv run -m article_publisher cache size
  uv run -m article_publisher cache clean
"""

import dataclasses
import json
from argparse import (
    ArgumentParser,
    Namespace,
    RawDescriptionHelpFormatter,
    _SubParsersAction,
)
from pathlib import Path
lazy from collections.abc import Callable

from article_publisher._auth import LARK_REQUIRED_ENV_KEYS, require_auth
from article_publisher.cache import CACHE_DIR, cache_size, clear_cache, format_size
from article_publisher.converters.lark.converter import LarkDocxConverter
from article_publisher.converters.markdown import MarkdownConverter
from article_publisher.errors import CliError
from article_publisher.log import logger
from article_publisher.platforms.bilibili import cli as bilibili_cli
from article_publisher.platforms.nga import cli as nga_cli
from article_publisher.platforms.skland import cli as skland_cli
lazy from article_publisher.converters.base import Converter
lazy from article_publisher.document import Document

LARK_AUTH_HELP = """错误：缺少飞书应用认证配置
请在 .env 文件中添加：
    LARK_APP_ID=你的App ID
    LARK_APP_SECRET=你的 App Secret
获取方式：在飞书开发者平台 https://open.feishu.cn/app 创建应用后获取。"""


PLATFORM_RUNNERS = {
    "bilibili": bilibili_cli.run,
    "skland": skland_cli.run,
    "nga": nga_cli.run,
}
"""平台名到发布流程的映射，键需与 `_build_parser` 中的平台子命令保持一致。"""


def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        description="多平台文章发布工具", formatter_class=RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True, title="命令")

    publish = subparsers.add_parser(
        "publish", aliases=["p"], help="把文章发布到指定平台"
    )
    platforms = publish.add_subparsers(dest="platform", required=True, title="发布平台")
    _add_platform_parser(
        platforms, "bilibili", "发布到 B站专栏", bilibili_cli.add_options
    )
    _add_platform_parser(platforms, "skland", "发布到森空岛", skland_cli.add_options)
    _add_platform_parser(platforms, "nga", "发布到 NGA", nga_cli.add_options)

    cache = subparsers.add_parser("cache", help="查看或清理本地下载缓存")
    cache_actions = cache.add_subparsers(
        dest="cache_action", required=True, title="缓存操作"
    )
    cache_actions.add_parser("dir", help="显示缓存目录路径")
    cache_actions.add_parser("size", help="显示缓存文件数量与占用空间")
    cache_actions.add_parser("clean", help="删除缓存目录下的全部文件")

    return parser


def _add_platform_parser(
    subparsers: _SubParsersAction,
    name: str,
    help_text: str,
    add_options: Callable[[ArgumentParser], None],
) -> None:
    """创建平台子命令，平台专属选项挂在输入源子命令上。"""
    platform = subparsers.add_parser(name, help=help_text)
    sources = platform.add_subparsers(dest="source", required=True, title="输入源")

    markdown = sources.add_parser(
        "markdown", aliases=["md"], help="从本地 Markdown 文件发布"
    )
    add_options(markdown)
    markdown.add_argument(
        "file", help="Markdown 文件路径（图片路径相对于该文件所在目录解析）"
    )

    lark = sources.add_parser("lark", help="从飞书云文档发布")
    add_options(lark)
    lark.add_argument("doc_id", help="飞书云文档 ID")


async def _run_publish(args: Namespace) -> None:
    """执行发布命令：转换输入源，再交由对应平台发布。"""
    run = PLATFORM_RUNNERS[args.platform]
    converter = _create_converter(args)
    try:
        logger.info("正在转换内容 ...")
        doc = await converter.convert()
        logger.info(f"转换完成，共 {len(doc.blocks)} 个段落")
        logger.info(f"标题: {doc.title}")

        if args.dry_run:
            _print_document_preview(doc)

        await run(doc, args)
    finally:
        # 下载的图片保留在缓存目录中，由 `cache clean` 手动清理
        await converter.close()


def _run_cache(args: Namespace) -> None:
    """执行缓存命令：按子命令查看或清理缓存。"""
    match args.cache_action:
        case "dir":
            print(CACHE_DIR)
        case "size":
            files, total = cache_size()
            print(f"缓存目录: {CACHE_DIR}")
            print(f"文件数量: {files}")
            print(f"占用空间: {format_size(total)}")
        case "clean":
            if clear_cache():
                print(f"已清理缓存: {CACHE_DIR}")
            else:
                print(f"缓存目录不存在，无需清理: {CACHE_DIR}")


def _create_converter(args: Namespace) -> Converter:
    """根据输入源创建转换器。"""
    if args.source in ("markdown", "md"):
        path = Path(args.file)
        if not path.is_file():
            raise CliError(f"错误：文件不存在: {path}")
        logger.info(f"📄 Markdown 文件: {path}")
        return MarkdownConverter(path)

    elif args.source == "lark":
        cfg = require_auth(LARK_REQUIRED_ENV_KEYS, LARK_AUTH_HELP)
        logger.info(f"📄 飞书云文档: {args.doc_id}")
        return LarkDocxConverter(
            app_id=cfg["LARK_APP_ID"],
            app_secret=cfg["LARK_APP_SECRET"],
            document_id=args.doc_id,
        )

    else:
        raise CliError(f"未知输入源: {args.source}")


def _print_document_preview(doc: Document) -> None:
    """在 dry-run 模式下打印转换后的完整 IR Document。"""
    logger.info("=" * 60)
    logger.info("  [dry-run] Converter IR Document 预览：")
    logger.info("=" * 60)
    print(
        json.dumps(dataclasses.asdict(doc), ensure_ascii=False, indent=2, default=str)
    )
    logger.info("=" * 60)


async def cli() -> None:
    """解析命令行参数并执行对应的一级子命令。"""
    args = _build_parser().parse_args()
    if args.command == "cache":
        _run_cache(args)
        return
    await _run_publish(args)
