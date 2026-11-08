"""
NGA 命令行适配。

定义 NGA 专属选项，并负责从命令行参数到 NgaPublisher 的发布流程。
"""

lazy from argparse import ArgumentParser, Namespace

from article_publisher._auth import NGA_REQUIRED_ENV_KEYS, require_auth
from article_publisher.log import logger
from article_publisher.platforms.nga.client import NgaClient
from article_publisher.platforms.nga.publisher import NgaPublishConfig, NgaPublisher
lazy from article_publisher.document import Document

AUTH_HELP = """错误：缺少 NGA Cookie

请在 .env 文件中添加：
    NGA_COOKIE=你的完整 Cookie 字符串

获取方式：浏览器登录 NGA 后，
  按 F12 打开开发者工具 → Application（应用程序） → Cookies → https://ngabbs.com
  全选所有 Cookie 的 "Name=Value" 格式，复制粘贴到 .env 文件中。

  示例：NGA_COOKIE=ngaPassportUid=12345; ngacn0comUserInfo=...; ..."""


def add_options(parser: ArgumentParser) -> None:
    """添加 NGA 专属选项。"""
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


async def run(doc: Document, args: Namespace) -> None:
    """NGA 发布流程：加载认证、上传图片、生成 BBCode。"""
    cfg = require_auth(NGA_REQUIRED_ENV_KEYS, AUTH_HELP)

    editing = args.tid is not None
    # 编辑已有帖子时，pid=0，article=0
    pid = article = "0" if editing else None
    config = NgaPublishConfig(fid=args.fid, tid=args.tid, pid=pid, article=article)

    mode = "编辑" if editing else "发布"
    logger.info(f"NGA {mode}模式 (tid={args.tid if editing else '新帖'})")

    async with NgaClient(cookie_str=cfg["NGA_COOKIE"], fid=args.fid) as client:
        publisher = NgaPublisher(client, config=config)
        await publisher.publish(doc, dry_run=args.dry_run)
