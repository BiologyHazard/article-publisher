"""
B站 Opus 专栏保存草稿 Payload 的数据模型（TypedDict）。

所有类型定义对应 `docs/PAYLOAD_GUIDE.md` 中的结构说明。
使用 TypedDict 提供类型提示和 IDE 补全，无运行时开销。
"""

from __future__ import annotations

from typing import NotRequired, TypedDict

# =============================================================================
# 内联节点类型
# =============================================================================


class TextStyle(TypedDict, total=False):
    """文字样式。所有字段均为可选，缺失的样式不应用。"""

    bold: bool
    italic: bool
    underline: bool
    strikethrough: bool


class BgColor(TypedDict):
    """背景色的颜色值。"""

    color: str
    dark_color: str
    bili_theme: str


class BgStyle(TypedDict):
    """背景色样式。"""

    style: int
    color: BgColor


class WordContent(TypedDict):
    """文本节点 (node_type=1) 的 word 内容。"""

    words: str
    font_size: int
    color: str
    dark_color: str
    style: TextStyle
    font_level: str
    bili_theme: NotRequired[str]
    bg_style: NotRequired[BgStyle]


class TextNode(TypedDict):
    """文本内联节点 (node_type=1)。"""

    node_type: int
    word: WordContent


class EmoteContent(TypedDict):
    """表情节点 (node_type=2) 的 emote 内容。"""

    raw_text: str


class EmoteNode(TypedDict):
    """表情内联节点 (node_type=2)。"""

    node_type: int
    emote: EmoteContent


class LinkStyle(TypedDict, total=False):
    """链接节点的文字样式。"""

    bold: bool
    italic: bool
    strikethrough: bool
    underline: bool
    font_size: int
    font_level: str


class LinkContent(TypedDict):
    """超链接节点 (node_type=4) 的 link 内容。"""

    show_text: str
    link: str
    icon: str
    icon_suffix: str
    link_type: int
    biz_id: str
    pics: list[str]
    style: LinkStyle


class LinkNode(TypedDict):
    """超链接内联节点 (node_type=4)。"""

    node_type: int
    link: LinkContent


class FormulaContent(TypedDict):
    """公式节点 (node_type=5) 的 formula 内容。"""

    latex_content: str


class FormulaNode(TypedDict):
    """Latex 公式内联节点 (node_type=5)。"""

    node_type: int
    formula: FormulaContent


# 内联节点联合类型
InlineNode = TextNode | EmoteNode | LinkNode | FormulaNode


# =============================================================================
# 段落格式类型
# =============================================================================


class Indent(TypedDict):
    """段落缩进。"""

    first_line_indent: int
    indent: int


class TextParaFormat(TypedDict, total=False):
    """普通文本段落的 format。"""

    indent: Indent
    align: int


class HeadingParaFormat(TypedDict, total=False):
    """标题段落的 format。"""

    indent: Indent
    heading_type: int
    align: int


class ListFormatDetail(TypedDict):
    """列表格式详情。"""

    level: int
    order: int
    theme: str


class ListParaFormat(TypedDict, total=False):
    """列表段落的 format。"""

    align: int
    list_format: ListFormatDetail
    combine_hash: str


class BlockquoteParaFormat(TypedDict, total=False):
    """引用段落的 format。"""

    indent: Indent
    combine_hash: str
    align: int


# =============================================================================
# 段落类型
# =============================================================================


class TextContent(TypedDict):
    """段落中的 text 内容。"""

    nodes: list[InlineNode]  # type: ignore[misc]


class TextParagraph(TypedDict):
    """普通文本段落 (para_type=1)。"""

    para_type: int
    format: TextParaFormat
    text: TextContent


class UploadedImage(TypedDict):
    """upload_image 方法的返回值。"""

    url: str
    width: int
    height: int
    size: float


class ImagePic(UploadedImage):
    """图片段落中的单张图片信息。"""

    comment: NotRequired[str]
    ai_gen_pic: NotRequired[int]


class PicGroup(TypedDict):
    """图片段落中的 pic 组。"""

    pics: list[ImagePic]
    style: int


class ImageParagraph(TypedDict):
    """图片段落 (para_type=2)。"""

    para_type: int
    pic: PicGroup


class LineContent(TypedDict):
    """分隔线段落的 line 内容。"""

    line_type: int


class DividerParagraph(TypedDict):
    """分隔线段落 (para_type=3)。"""

    para_type: int
    line: LineContent


class BlockquoteParagraph(TypedDict):
    """引用段落 (para_type=4)。"""

    para_type: int
    format: BlockquoteParaFormat
    text: TextContent


class OrderedListParagraph(TypedDict):
    """有序列表段落 (para_type=5)。"""

    para_type: int
    format: ListParaFormat
    text: TextContent


class UnorderedListParagraph(TypedDict):
    """无序列表段落 (para_type=6)。"""

    para_type: int
    format: ListParaFormat
    text: TextContent


class CodeContent(TypedDict):
    """代码块段落的 code 内容。"""

    lang: str
    content: str


class CodeParagraph(TypedDict):
    """代码块段落 (para_type=8)。"""

    para_type: int
    code: CodeContent


class HeadingParagraph(TypedDict):
    """标题段落 (para_type=9)。"""

    para_type: int
    format: HeadingParaFormat
    text: TextContent


# 段落联合类型
Paragraph = (
    TextParagraph
    | ImageParagraph
    | DividerParagraph
    | BlockquoteParagraph
    | OrderedListParagraph
    | UnorderedListParagraph
    | CodeParagraph
    | HeadingParagraph
)


# =============================================================================
# Opus 内容体
# =============================================================================


class ContentBody(TypedDict):
    """Opus 正文内容。"""

    paragraphs: list[Paragraph]


class PubInfo(TypedDict):
    """发布信息。"""

    editor_version: str


class Attachments(TypedDict):
    """附件信息。"""

    is_aigc: int


class OpusBody(TypedDict):
    """Opus 内容体。"""

    opus_source: int
    title: str
    content: ContentBody
    pub_info: PubInfo
    attachments: Attachments


# =============================================================================
# 顶层 Payload
# =============================================================================


class ArgPayload(TypedDict, total=False):
    """arg 字段（保存草稿请求的核心负载）。"""

    type: int
    template_id: int
    category_id: int
    article_id: int  # NotRequired（新建草稿时不传）
    title: str
    private_pub: int
    reprint: int
    original: int
    list_id: int
    comment_selected: int
    up_closed_reply: int
    timer_pub_time: int
    only_fans_level: int
    only_fans_dnd: int
    image_urls: list[str]  # NotRequired（自定义封面，可选）
    hashtag_ids: list[int]  # NotRequired（话题 ID 列表，可选）
    summary: str
    opus: OpusBody


class Payload(TypedDict):
    """保存草稿请求的完整 Payload 结构。"""

    arg: ArgPayload
