"""
B站 Opus 格式数据构建器。

提供了一系列工厂函数，用于构造 Opus (新版专栏) 内容格式中的各种
段落 (paragraph) 和内联节点 (node) 数据结构。
"""

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
) -> dict:
    """构造一个 Opus 文本节点 (node_type=1)。"""
    style: dict[str, bool] = {}
    if bold:
        style["bold"] = True
    if italic:
        style["italic"] = True
    if underline:
        style["underline"] = True
    if strikethrough:
        style["strikethrough"] = True

    node: dict = {
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
    if not style:
        node["word"]["style"] = {}
    return node


def make_heading_node(words: str, level: int) -> dict:
    """构造标题节点。"""
    cfg = {
        1: {"font_size": 24, "font_level": "xxLarge"},
        2: {"font_size": 22, "font_level": "xLarge"},
        3: {"font_size": 20, "font_level": "large"},
    }.get(level, {"font_size": 20, "font_level": "large"})
    return {
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


def make_link_node(show_text: str, url: str) -> dict:
    """构造超链接节点 (node_type=4)。"""
    return {
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


def make_formula_node(latex_content: str) -> dict:
    """构造 Latex 公式节点 (node_type=5)。"""
    return {
        "node_type": 5,
        "formula": {
            "latex_content": latex_content,
        },
    }


def make_emote_node(raw_text: str) -> dict:
    """构造表情节点 (node_type=2)。"""
    return {
        "node_type": 2,
        "emote": {
            "raw_text": raw_text,
        },
    }


# =============================================================================
# 段落构建器
# =============================================================================


def make_text_paragraph(
    nodes: list[dict],
    *,
    align: int | None = None,
    indent_level: int = 0,
) -> dict:
    """构造普通文本段落 (para_type=1)。"""
    para: dict = {
        "para_type": 1,
        "format": {
            "indent": {
                "first_line_indent": 0,
                "indent": indent_level,
            },
        },
        "text": {"nodes": nodes},
    }
    if align is not None and align != 0:
        para["format"]["align"] = align
    return para


def make_heading_paragraph(words: str, level: int) -> dict:
    """构造标题段落 (para_type=9)。"""
    heading_type = {1: 1, 2: 2, 3: 3}.get(level, 3)
    return {
        "para_type": 9,
        "format": {
            "indent": {"first_line_indent": 0, "indent": 0},
            "heading_type": heading_type,
        },
        "text": {"nodes": [make_heading_node(words, level)]},
    }


def make_image_paragraph(
    img_url: str,
    width: int,
    height: int,
    size: float = 0,
    comment: str = "",
) -> dict:
    """构造图片段落 (para_type=2)。"""
    pic: dict = {
        "url": img_url,
        "width": width,
        "height": height,
        "size": size,
        "ai_gen_pic": 0,
    }
    if comment:
        pic["comment"] = comment
    return {
        "para_type": 2,
        "pic": {
            "pics": [pic],
            "style": 0,
        },
    }


def make_divider_paragraph() -> dict:
    """构造分隔线段落 (para_type=3)。"""
    return {"para_type": 3, "line": {"line_type": 1}}


def make_blockquote_paragraph(
    nodes: list[dict],
    combine_hash: str,
    *,
    align: int | None = None,
) -> dict:
    """构造引用段落 (para_type=4)。"""
    para: dict = {
        "para_type": 4,
        "format": {
            "indent": {"first_line_indent": 0, "indent": 0},
            "combine_hash": combine_hash,
        },
        "text": {"nodes": nodes},
    }
    if align is not None and align != 0:
        para["format"]["align"] = align
    return para


def make_ordered_list_paragraph(
    nodes: list[dict],
    level: int,
    order: int,
    combine_hash: str,
    *,
    align: int | None = None,
) -> dict:
    """构造有序列表段落 (para_type=5)。"""
    theme = {1: "arabic_num", 2: "lower_letter", 3: "roman_num"}.get(
        level, "arabic_num"
    )
    para: dict = {
        "para_type": 5,
        "format": {
            "align": align if align is not None else 0,
            "list_format": {
                "level": level,
                "order": order,
                "theme": theme,
            },
            "combine_hash": combine_hash,
        },
        "text": {"nodes": nodes},
    }
    return para


def make_unordered_list_paragraph(
    nodes: list[dict],
    level: int,
    order: int,
    combine_hash: str,
    *,
    align: int | None = None,
) -> dict:
    """构造无序列表段落 (para_type=6)。"""
    theme = {1: "dot", 2: "square", 3: "circle"}.get(level, "dot")
    para: dict = {
        "para_type": 6,
        "format": {
            "align": align if align is not None else 0,
            "list_format": {
                "level": level,
                "order": order,
                "theme": theme,
            },
            "combine_hash": combine_hash,
        },
        "text": {"nodes": nodes},
    }
    return para


def make_code_paragraph(content: str, lang: str = "") -> dict:
    """构造代码块段落 (para_type=8)。"""
    return {
        "para_type": 8,
        "code": {
            "lang": lang,
            "content": content,
        },
    }
