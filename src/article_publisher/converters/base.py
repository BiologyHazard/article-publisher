"""
转换器基类。

所有输入格式转换器 (Markdown / 飞书云文档等) 均应继承此基类。
输出统一为平台无关的 IR Document。
"""

from abc import ABC, abstractmethod

lazy from article_publisher.document import Document


class Converter(ABC):
    """将输入内容转换为 IR Document 的基类。"""

    @abstractmethod
    async def convert(self) -> Document:
        """执行转换，返回平台无关的 IR Document。"""
        ...
