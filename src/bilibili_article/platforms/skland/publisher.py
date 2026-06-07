"""
森空岛 Publisher — 空代码。

TODO: 实现森空岛 API 对接。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from bilibili_article.platforms.base import Publisher

if TYPE_CHECKING:
    from bilibili_article.document import Document


class SklandPublisher(Publisher):
    """将 IR Document 发布到森空岛（空实现）。"""

    def __init__(self) -> None:
        pass

    def publish(self, doc: Document, *, dry_run: bool = False) -> dict[str, Any]:
        logger.info("=" * 50)
        logger.info("  [森空岛] 发布功能尚未实现")
        logger.info("=" * 50)
        logger.info(f"  标题: {doc.title}")
        logger.info(f"  段落数: {len(doc.blocks)}")

        if not dry_run:
            logger.info("  ⏳ 等待后续实现 ...")

        return {"platform": "skland", "status": "stub", "title": doc.title}
