"""
Publisher 抽象基类。

所有目标平台的 Publisher 均应继承此类。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from article_publisher.document import Document


class Publisher(ABC):
    """将 IR Document 发布到目标平台的抽象基类。"""

    @abstractmethod
    def publish(self, doc: Document, *, dry_run: bool = False) -> dict[str, Any]:
        """将 IR Document 发布到目标平台，返回 API 响应。"""
        ...
