"""
B站 Opus 格式数据构建器。

提供了一系列工厂函数，用于构造 Opus (新版专栏) 内容格式中的各种
段落 (paragraph) 和内联节点 (node) 数据结构。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from bilibili_article.document import Alignment

# B站 Opus API 对齐值: 0=左对齐, 1=居中, 2=右对齐
_ALIGN_TO_OPUS: dict[Alignment, int] = {
    Alignment.LEFT: 0,
    Alignment.CENTER: 1,
    Alignment.RIGHT: 2,
}

if TYPE_CHECKING:
    from article_publisher.platforms.bilibili.models import (
        BlockquoteParagraph,
        CodeParagraph,
        DividerParagraph,
        EmoteNode,
        FormulaNode,
        HeadingParagraph,
        ImageParagraph,
        ImagePic,
        InlineNode,
        LinkNode,
        OrderedListParagraph,
        TextNode,
        TextParagraph,
        TextStyle,
        UnorderedListParagraph,
    )

# =============================================================================
# 文本节点常量
# =============================================================================

FONT_SIZE_REGULAR = 17
FONT_SIZE_H1 = 24
FONT_SIZE_H2 = 22
FONT_SIZE_H3 = 20


# =============================================================================
# 内联节点构建器
# =============================================================================


def make_text_node(
    words: str,
    *,
    font_size: int = FONT_SIZE_REGULAR,
    font_level: str = "regular",
    bold: bool = False,
    italic: bool = False,
    underline: bool = False,
    strikethrough: bool = False,
    color: str = "",
    dark_color: str = "",
) -> TextNode:
    """构造一个 Opus 文本节点 (node_type=1)。"""
    style: TextStyle = {}
    if bold:
        style["bold"] = True
    if italic:
        style["italic"] = True
    if underline:
        style["underline"] = True
    if strikethrough:
        style["strikethrough"] = True

    node: TextNode = {
        "node_type": 1,
        "word": {
            "words": words,
            "font_size": font_size,
            "color": color,
            "dark_color": dark_color,
            "style": style,
            "font_level": font_level,
        },
    }
    return node


def make_heading_node(words: str, level: int) -> TextNode:
    """构造标题节点。"""
    cfg = _HEADING_FONT_CFG.get(level, _HEADING_FONT_CFG[3])
    node: TextNode = {
        "node_type": 1,
        "word": {
            "words": words,
            "font_size": cfg["font_size"],
            "color": "",
            "dark_color": "",
            "style": {},
            "font_level": cfg["font_level"],
        },
    }
    return node


class _HeadingFontCfg(TypedDict):
    """标题级别字体配置。"""

    font_size: int
    font_level: str


_HEADING_FONT_CFG: dict[int, _HeadingFontCfg] = {
    1: {"font_size": 24, "font_level": "xxLarge"},
    2: {"font_size": 22, "font_level": "xLarge"},
    3: {"font_size": 20, "font_level": "large"},
}
"""标题级别对应的字体配置。"""


def make_link_node(show_text: str, url: str) -> LinkNode:
    """构造超链接节点 (node_type=4)。"""
    node: LinkNode = {
        "node_type": 4,
        "link": {
            "show_text": show_text,
            "link": url,
            "icon": "",
            "icon_suffix": "",
            "link_type": 16,
            "biz_id": "",
            "pics": [],
            "style": {
                "bold": False,
                "italic": False,
                "strikethrough": False,
                "underline": False,
                "font_size": 0,
                "font_level": "regular",
            },
        },
    }
    return node


def make_formula_node(latex_content: str) -> FormulaNode:
    """构造 Latex 公式节点 (node_type=5)。"""
    node: FormulaNode = {"node_type": 5, "formula": {"latex_content": latex_content}}
    return node


def make_emote_node(raw_text: str) -> EmoteNode:
    """构造表情节点 (node_type=2)。"""
    node: EmoteNode = {"node_type": 2, "emote": {"raw_text": raw_text}}
    return node


# =============================================================================
# 段落构建器
# =============================================================================


def make_text_paragraph(
    nodes: list[InlineNode], *, align: Alignment = Alignment.LEFT, indent_level: int = 0
) -> TextParagraph:
    """构造普通文本段落 (para_type=1)。"""
    para: TextParagraph = {
        "para_type": 1,
        "format": {"indent": {"first_line_indent": 0, "indent": indent_level}},
        "text": {"nodes": nodes},
    }
    if align is not Alignment.LEFT:
        para["format"]["align"] = _ALIGN_TO_OPUS[align]
    return para


def make_heading_paragraph(
    nodes: list[InlineNode], level: int, *, align: Alignment = Alignment.LEFT
) -> HeadingParagraph:
    """构造标题段落 (para_type=9)，支持富文本内联节点。"""
    heading_type = {1: 1, 2: 2, 3: 3}.get(level, 3)
    cfg = _HEADING_FONT_CFG.get(level, _HEADING_FONT_CFG[3])
    styled_nodes = [_apply_heading_style(n, cfg) for n in nodes]
    para: HeadingParagraph = {
        "para_type": 9,
        "format": {
            "indent": {"first_line_indent": 0, "indent": 0},
            "heading_type": heading_type,
        },
        "text": {"nodes": styled_nodes},
    }
    if align is not Alignment.LEFT:
        para["format"]["align"] = _ALIGN_TO_OPUS[align]
    return para


def _apply_heading_style(node: InlineNode, cfg: _HeadingFontCfg) -> InlineNode:
    """对文本节点应用标题级别字体样式。"""
    if isinstance(node, dict) and node.get("node_type") == 1:
        word = node.get("word", {})
        if isinstance(word, dict):
            word["font_size"] = cfg["font_size"]
            word["font_level"] = cfg["font_level"]
    return node


def make_image_paragraph(
    img_url: str, width: int, height: int, size: float = 0, comment: str = ""
) -> ImageParagraph:
    """构造图片段落 (para_type=2)。"""
    pic: ImagePic = {
        "url": img_url,
        "width": width,
        "height": height,
        "size": size,
        "ai_gen_pic": 0,
    }
    if comment:
        pic["comment"] = comment
    para: ImageParagraph = {"para_type": 2, "pic": {"pics": [pic], "style": 0}}
    return para


def make_divider_paragraph() -> DividerParagraph:
    """构造分隔线段落 (para_type=3)。"""
    para: DividerParagraph = {"para_type": 3, "line": {"line_type": 1}}
    return para


def make_blockquote_paragraph(
    nodes: list[InlineNode], combine_hash: str, *, align: Alignment | None = None
) -> BlockquoteParagraph:
    """构造引用段落 (para_type=4)。"""
    para: BlockquoteParagraph = {
        "para_type": 4,
        "format": {
            "indent": {"first_line_indent": 0, "indent": 0},
            "combine_hash": combine_hash,
        },
        "text": {"nodes": nodes},
    }
    if align is not None and align is not Alignment.LEFT:
        para["format"]["align"] = _ALIGN_TO_OPUS[align]
    return para


def make_ordered_list_paragraph(
    nodes: list[InlineNode],
    level: int,
    order: int,
    combine_hash: str,
    *,
    align: Alignment | None = None,
) -> OrderedListParagraph:
    """构造有序列表段落 (para_type=5)。"""
    theme = {1: "arabic_num", 2: "lower_letter", 3: "roman_num"}.get(
        level, "arabic_num"
    )
    para: OrderedListParagraph = {
        "para_type": 5,
        "format": {
            "align": _ALIGN_TO_OPUS[align]
            if align is not None
            else _ALIGN_TO_OPUS[Alignment.LEFT],
            "list_format": {"level": level, "order": order, "theme": theme},
            "combine_hash": combine_hash,
        },
        "text": {"nodes": nodes},
    }
    return para


def make_unordered_list_paragraph(
    nodes: list[InlineNode],
    level: int,
    order: int,
    combine_hash: str,
    *,
    align: Alignment | None = None,
) -> UnorderedListParagraph:
    """构造无序列表段落 (para_type=6)。"""
    theme = {1: "dot", 2: "square", 3: "circle"}.get(level, "dot")
    para: UnorderedListParagraph = {
        "para_type": 6,
        "format": {
            "align": _ALIGN_TO_OPUS[align]
            if align is not None
            else _ALIGN_TO_OPUS[Alignment.LEFT],
            "list_format": {"level": level, "order": order, "theme": theme},
            "combine_hash": combine_hash,
        },
        "text": {"nodes": nodes},
    }
    return para


def make_code_paragraph(content: str, lang: str = "") -> CodeParagraph:
    """构造代码块段落 (para_type=8)。"""
    para: CodeParagraph = {"para_type": 8, "code": {"lang": lang, "content": content}}
    return para
