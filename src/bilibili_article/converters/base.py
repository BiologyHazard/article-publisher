"""
转换器基类。

所有输入格式转换器 (Markdown / 飞书云文档等) 均应继承此基类。
"""

from abc import ABC, abstractmethod


class BaseConverter(ABC):
    """将输入内容转换为 Opus paragraphs 列表的基类。"""

    @abstractmethod
    def convert(self) -> list[dict]:
        """执行转换，返回 Opus paragraphs 列表。"""
        ...
