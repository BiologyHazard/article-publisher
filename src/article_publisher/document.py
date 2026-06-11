from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


class Alignment(Enum):
    LEFT = auto()
    CENTER = auto()
    RIGHT = auto()


@dataclass
class Node:
    """节点基类。"""

    pass


@dataclass
class InlineElement(Node):
    """行内元素基类。"""

    pass


@dataclass
class TextRun(InlineElement):
    """一段带有格式的文本。"""

    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False
    inline_code: bool = False
    color: str = ""
    link_url: str | None = None


@dataclass
class Formula(InlineElement):
    """LaTeX 公式。"""

    latex: str


@dataclass
class Block(Node):
    """块级元素基类。"""

    pass


@dataclass
class Heading(Block):
    """标题（支持富文本格式）"""

    level: int
    children: Sequence[InlineElement]
    align: Alignment = Alignment.LEFT
    indent_level: int = 0  # 0=无缩进, 1=一级, 2=二级


@dataclass
class Paragraph(Block):
    """普通文本段落。"""

    children: Sequence[InlineElement]
    align: Alignment = Alignment.LEFT
    indent_level: int = 0  # 0=无缩进, 1=一级, 2=二级


@dataclass
class ImageBlock(Block):
    """图片块。

    source 为图片来源：
    - 本地文件路径（Markdown 输入）
    - 转换器已下载到本地的文件路径（飞书等远程来源）
    Publisher 负责将 source 上传到目标平台图床。
    """

    source: str
    alt_text: str | None = None
    caption: str | None = None


@dataclass
class CodeBlock(Block):
    """代码块。"""

    language: str
    content: str


@dataclass
class Blockquote(Block):
    """引用块（可嵌套块级元素）。"""

    children: list[Block]


@dataclass
class ListItem:
    """列表项（可包含多个块级元素，支持嵌套列表）。"""

    blocks: list[Block]


@dataclass
class OrderedList(Block):
    """有序列表。"""

    items: list[ListItem]


@dataclass
class UnorderedList(Block):
    """无序列表。"""

    items: list[ListItem]


@dataclass
class Divider(Block):
    """分割线。"""

    pass


@dataclass
class Document:
    """完整文档结构"""

    title: str
    blocks: list[Block]
    cover: str | None = None
    """封面图片路径（本地文件路径，由转换器负责下载）"""
