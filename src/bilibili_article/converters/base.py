"""
转换器基类。

所有输入格式转换器 (Markdown / 飞书云文档等) 均应继承此基类。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bilibili_article.models import Paragraph


class BaseConverter(ABC):
    """将输入内容转换为 Opus paragraphs 列表的基类。"""

    @abstractmethod
    def convert(self) -> list[Paragraph]:
        """执行转换，返回 Opus paragraphs 列表。"""
        ...

    @abstractmethod
    def get_title(self) -> str:
        """从原始内容中提取文档标题。"""
        ...
