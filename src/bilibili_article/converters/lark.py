"""
飞书云文档 (Lark Docx) → Opus 转换器。

使用 lark_oapi SDK 获取飞书云文档的块数据，递归遍历块树，
将每个块转换为对应的 B站 Opus 格式段落。

支持的飞书块类型：
  - 文本 (text)           → 普通段落
  - 标题 H1~H3            → 标题段落
  - 标题 H4~H9            → 仿标题段落（加粗正文）
  - 无序/有序列表         → 列表段落
  - 代码块 (code)         → 代码块段落
  - 引用 (quote_container) → 引用段落
  - 分割线 (divider)      → 分割线段落
  - 图片 (image)          → 图片段落（自动下载并上传到 B站）
  - 高亮块 (callout)      → 普通正文
  - 分栏 (grid/grid_column) → 展平子块
  - 表格/电子表格         → 展平或跳过
"""

import os
import tempfile
import time
from typing import Any

import lark_oapi as lark
from lark_oapi.api.docx.v1 import (
    Block,
    ListDocumentBlockRequest,
    TextElement,
    TextRun,
)
from lark_oapi.api.drive.v1 import DownloadMediaRequest

from bilibili_article.client import BiliApiError, BiliClient
from bilibili_article.converters.base import BaseConverter
from bilibili_article.opus import (
    FONT_SIZE_REGULAR,
    make_blockquote_paragraph,
    make_code_paragraph,
    make_divider_paragraph,
    make_formula_node,
    make_heading_paragraph,
    make_image_paragraph,
    make_link_node,
    make_ordered_list_paragraph,
    make_text_node,
    make_text_paragraph,
    make_unordered_list_paragraph,
)

# ---------------------------------------------------------------------------
# Lark 颜色索引 → 实际颜色的映射（仅常见颜色）
# 参考飞书开放平台文档：text_color / background_color 索引值
# ---------------------------------------------------------------------------
_TEXT_COLOR_MAP: dict[int, str] = {
    1: "#c9272c",  # 红色
    2: "#fba518",  # 橙色
    3: "#f9d71c",  # 黄色
    4: "#3cb034",  # 绿色
    5: "#3598cd",  # 蓝色
    6: "#8e5bb5",  # 紫色
    7: "#7a7a7a",  # 灰色
    8: "#6bc3b2",  # 青色
    9: "#15848c",  # 深青
    10: "#1f8c9a",  # 靛蓝
    11: "#347ab3",  # 深蓝
    12: "#af6ba5",  # 粉紫
}

_BG_COLOR_MAP: dict[int, str] = {
    1: "#fdf2f2",  # 浅红
    2: "#fef6e8",  # 浅橙
    3: "#fef9da",  # 浅黄
    4: "#eaf7e6",  # 浅绿
    5: "#e7f1f7",  # 浅蓝
    6: "#f3edf7",  # 浅紫
    7: "#f0f0f0",  # 浅灰
    8: "#ffd9e4",  # 红色背景（特殊值，需要配 bili_theme）
    9: "#e5ffeb",  # 浅薄荷
}

# Lark 代码语言 ID → 语言名称映射
_CODE_LANG_MAP: dict[int, str] = {
    0: "PlainText",
    1: "ABAP",
    2: "Ada",
    3: "Apache",
    4: "Apex",
    5: "Assembly",
    6: "Bash",
    7: "CSharp",
    8: "C++",
    9: "C",
    10: "COBOL",
    11: "CSS",
    12: "CoffeeScript",
    13: "D",
    14: "Dart",
    15: "Delphi",
    16: "Django",
    17: "Dockerfile",
    18: "Erlang",
    19: "Fortran",
    20: "FoxPro",
    21: "Go",
    22: "Groovy",
    23: "HLSL",
    24: "HTML",
    25: "Haskell",
    26: "INI",
    27: "JSON",
    28: "Java",
    29: "JavaScript",
    30: "Julia",
    31: "Kotlin",
    32: "LaTeX",
    33: "Lisp",
    34: "Logo",
    35: "Lua",
    36: "MATLAB",
    37: "Makefile",
    38: "Markdown",
    39: "Nginx",
    40: "Objective-C",
    41: "OpenEdge",
    42: "PHP",
    43: "Perl",
    44: "PowerShell",
    45: "Prolog",
    46: "Protocol Buffer",
    47: "Python",
    48: "R",
    49: "REST",
    50: "Ruby",
    51: "Rust",
    52: "SAS",
    53: "SQL",
    54: "Scala",
    55: "Scheme",
    56: "Shell",
    57: "Solidity",
    58: "Swift",
    59: "TypeScript",
    60: "VBA",
    61: "Visual Basic",
    62: "WebAssembly",
    63: "XML",
    64: "YAML",
    65: "CSharp",
}


class LarkDocxConverter(BaseConverter):
    """
    将飞书云文档转换为 B站 Opus 格式段落列表。

    用法:
        converter = LarkDocxConverter(app_id, app_secret, doc_id, bili_client)
        paragraphs = converter.convert()
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        document_id: str,
        bili_client: BiliClient,
        log_level: lark.LogLevel = lark.LogLevel.ERROR,
    ):
        self.document_id = document_id
        self.bili_client = bili_client

        self._client: lark.Client = (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .log_level(log_level)
            .build()
        )

        # 缓存：block_id → Block（树构建后可通过 children 遍历）
        self._blocks: dict[str, Block] = {}
        self._root_block_id: str = ""

        # 列表追踪：用于生成 combine_hash
        self._list_counter = 0

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def fetch_document_info(self) -> dict[str, Any]:
        """获取文档基本信息，返回包含 title 的字典。"""
        request = (
            lark.api.docx.v1.GetDocumentRequest.builder()
            .document_id(self.document_id)
            .build()
        )
        response = self._client.docx.v1.document.get(request)
        if not response.success():
            raise RuntimeError(f"获取文档信息失败: {response.code} {response.msg}")
        doc = response.data.document
        return {
            "document_id": doc.document_id,
            "title": doc.title,
            "revision_id": doc.revision_id,
        }

    def convert(self) -> list[dict]:
        """执行转换，返回 Opus paragraphs 列表。"""
        self._load_blocks()
        paragraphs: list[dict] = []
        self._walk_block(self._root_block_id, paragraphs, context={})
        return paragraphs

    # ------------------------------------------------------------------
    # 块数据加载与树构建
    # ------------------------------------------------------------------

    def _load_blocks(self) -> None:
        """从飞书 API 加载文档所有块，构建 block_id → Block 映射。"""
        items: list[Block] = []
        page_token: str = ""
        while True:
            request = (
                ListDocumentBlockRequest.builder()
                .document_id(self.document_id)
                .page_size(500)
                .page_token(page_token)
                .build()
            )
            response = self._client.docx.v1.document_block.list(request)
            if not response.success():
                raise RuntimeError(f"获取文档块失败: {response.code} {response.msg}")
            items.extend(response.data.items)
            if not response.data.has_more:
                break
            page_token = response.data.page_token

        # 构建映射并找到根节点
        for block in items:
            self._blocks[block.block_id] = block
            if block.parent_id == "":
                self._root_block_id = block.block_id

        if not self._root_block_id:
            # 如果没有 parent_id=="" 的块，第一个块就是根
            self._root_block_id = items[0].block_id if items else ""

        print(f"  已加载 {len(self._blocks)} 个块")

    # ------------------------------------------------------------------
    # 树遍历
    # ------------------------------------------------------------------

    def _walk_block(
        self,
        block_id: str,
        paragraphs: list[dict],
        context: dict,
        depth: int = 0,
    ) -> None:
        """深度优先遍历块树，将块转换为 Opus 段落。"""
        block = self._blocks.get(block_id)
        if block is None:
            return

        block_type = block.block_type
        prefix = "  " * depth

        # 根据 block_type 分发处理
        method_name = _BLOCK_CONVERTERS.get(block_type)
        if method_name:
            method = getattr(self, method_name, None)
            if method:
                method(block, paragraphs, context, prefix)

        # 递归处理子块
        if block.children:
            for child_id in block.children:
                self._walk_block(child_id, paragraphs, context, depth)

    # ------------------------------------------------------------------
    # 块转换器
    # ------------------------------------------------------------------

    def _convert_text(
        self,
        block: Block,
        paragraphs: list[dict],
        context: dict,
        prefix: str,
    ) -> None:
        """处理文本块 (block_type=2)。"""
        if block.text is None:
            return
        nodes = self._elements_to_nodes(block.text.elements)
        align = self._get_align(block.text.style)
        paragraphs.append(make_text_paragraph(nodes, align=align))

    def _convert_heading(
        self,
        block: Block,
        paragraphs: list[dict],
        context: dict,
        prefix: str,
    ) -> None:
        """处理标题块 (block_type=3~11 → heading1~heading9)。"""
        # 从 block_type 推断标题级别
        heading_level = block.block_type - 2  # 3→1, 4→2, ..., 11→9
        heading = getattr(block, f"heading{heading_level}", None)
        if heading is None:
            return
        text = self._elements_to_plain_text(heading.elements)

        if heading_level <= 3:
            paragraphs.append(make_heading_paragraph(text, heading_level))
        else:
            # H4~H9：B站不支持，用加粗正文代替
            nodes = self._elements_to_nodes(heading.elements)
            # 如果节点列表只有普通文本，改为加粗
            if len(nodes) == 1 and nodes[0]["node_type"] == 1:
                nodes[0]["word"]["style"]["bold"] = True
            paragraphs.append(make_text_paragraph(nodes))

    def _convert_bullet(
        self,
        block: Block,
        paragraphs: list[dict],
        context: dict,
        prefix: str,
    ) -> None:
        """处理无序列表块 (block_type=12)。"""
        if block.bullet is None:
            return
        # 计算列表嵌套层级
        level = self._calc_list_level(block)
        nodes = self._elements_to_nodes(block.bullet.elements)
        combine_hash = self._get_list_hash(block, level)
        order = self._calc_list_order(block, level, context, "bullet")
        align = self._get_align(block.bullet.style)

        paragraphs.append(
            make_unordered_list_paragraph(
                nodes,
                level=level,
                order=order,
                combine_hash=combine_hash,
                align=align,
            )
        )

    def _convert_ordered(
        self,
        block: Block,
        paragraphs: list[dict],
        context: dict,
        prefix: str,
    ) -> None:
        """处理有序列表块 (block_type=13)。"""
        if block.ordered is None:
            return
        level = self._calc_list_level(block)
        nodes = self._elements_to_nodes(block.ordered.elements)
        combine_hash = self._get_list_hash(block, level)
        order = self._calc_list_order(block, level, context, "ordered")
        align = self._get_align(block.ordered.style)

        paragraphs.append(
            make_ordered_list_paragraph(
                nodes,
                level=level,
                order=order,
                combine_hash=combine_hash,
                align=align,
            )
        )

    def _convert_code(
        self,
        block: Block,
        paragraphs: list[dict],
        context: dict,
        prefix: str,
    ) -> None:
        """处理代码块 (block_type=14)。"""
        if block.code is None:
            return
        # 收集代码内容（所有 text_run 的 content 拼接）
        content_parts: list[str] = []
        lang = ""
        for elem in block.code.elements or []:
            text_run = getattr(elem, "text_run", None)
            if text_run and text_run.content:
                content_parts.append(text_run.content)
        content = "".join(content_parts)

        # 获取语言
        if block.code.style and block.code.style.language is not None:
            lang = _CODE_LANG_MAP.get(block.code.style.language, "")

        if content:
            paragraphs.append(make_code_paragraph(content, lang))

    def _convert_divider(
        self,
        block: Block,
        paragraphs: list[dict],
        context: dict,
        prefix: str,
    ) -> None:
        """处理分割线 (block_type=22)。"""
        paragraphs.append(make_divider_paragraph())

    def _convert_image(
        self,
        block: Block,
        paragraphs: list[dict],
        context: dict,
        prefix: str,
    ) -> None:
        """处理图片 (block_type=27)：下载 → 上传 B站 → 追加段落。"""
        if block.image is None:
            return
        token = block.image.token
        if not token:
            return

        print(f"{prefix}正在处理图片: token={token}")
        try:
            image_data = self._download_image(token)
            # 写入临时文件
            suffix = ".png"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(image_data)
                tmp_path = tmp.name

            try:
                info = self.bili_client.upload_image(tmp_path)
                comment = ""
                if block.image.caption and block.image.caption.content:
                    comment = block.image.caption.content
                paragraphs.append(
                    make_image_paragraph(
                        info["url"],
                        info["width"],
                        info["height"],
                        info.get("size", 0),
                        comment=comment,
                    )
                )
                print(f"{prefix}  → 上传成功: {info['url']}")
            finally:
                os.unlink(tmp_path)
        except BiliApiError as e:
            print(f"{prefix}  [错误] 图片上传失败: {e}")
        except Exception as e:
            print(f"{prefix}  [错误] 图片处理异常: {e}")

    def _convert_quote(
        self,
        block: Block,
        paragraphs: list[dict],
        context: dict,
        prefix: str,
    ) -> None:
        """处理引用容器 (block_type=34) — 遍历子块并包装为引用段落。"""
        # quote_container 的子块都是 text 类型，需要将它们组合为引用段落。
        # B站 Opus 引用块的 combine_hash 需要共享同一个值。
        if not block.children:
            return

        combine_hash = f"blockquote_{int(time.time() * 1000000)}_{id(block)}"

        for child_id in block.children:
            child = self._blocks.get(child_id)
            if child is None or child.text is None:
                continue
            nodes = self._elements_to_nodes(child.text.elements)
            align = self._get_align(child.text.style)
            paragraphs.append(
                make_blockquote_paragraph(
                    nodes,
                    combine_hash=combine_hash,
                    align=align,
                )
            )

    def _convert_callout(
        self,
        block: Block,
        paragraphs: list[dict],
        context: dict,
        prefix: str,
    ) -> None:
        """处理高亮块 (block_type=19) — 以普通正文输出子块。"""
        # callout 子块会通过递归遍历自动处理
        pass

    def _convert_page(
        self,
        block: Block,
        paragraphs: list[dict],
        context: dict,
        prefix: str,
    ) -> None:
        """处理页面块 (block_type=1) — 根节点，子块会自动遍历。"""
        pass

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _elements_to_nodes(self, elements: list | None) -> list[dict]:
        """将 Lark TextElement 列表转换为 Opus 文本节点列表。"""
        nodes: list[dict] = []
        if not elements:
            return nodes

        for elem in elements:
            text_run = getattr(elem, "text_run", None)
            equation = getattr(elem, "equation", None)

            if text_run and text_run.content:
                node = self._text_run_to_node(text_run)
                nodes.append(node)
            elif equation and equation.content:
                nodes.append(make_formula_node(equation.content))

        # 合并相邻的普通文本节点
        return self._merge_text_nodes(nodes)

    def _text_run_to_node(self, text_run: TextRun) -> dict:
        """将单个 TextRun 转换为 Opus 文本节点。"""
        content = text_run.content
        style = text_run.text_element_style

        if style is None:
            return make_text_node(content)

        bold = bool(style.bold) if style.bold is not None else False
        italic = bool(style.italic) if style.italic is not None else False
        underline = bool(style.underline) if style.underline is not None else False
        strikethrough = (
            bool(style.strikethrough) if style.strikethrough is not None else False
        )
        inline_code = (
            bool(style.inline_code) if style.inline_code is not None else False
        )

        # 颜色
        color = ""
        dark_color = ""
        if inline_code:
            color = "#c7254e"
        elif style.text_color is not None:
            color = _TEXT_COLOR_MAP.get(style.text_color, "")

        # 背景色
        bg_color = ""
        if style.background_color is not None:
            bg_color = _BG_COLOR_MAP.get(style.background_color, "")

        # 处理超链接 — 使用 link 节点
        if style.link and style.link.url:
            # 需要 URL 解码
            import urllib.parse

            url = urllib.parse.unquote(style.link.url)
            return make_link_node(show_text=content, url=url)

        node = make_text_node(
            content,
            bold=bold,
            italic=italic,
            underline=underline,
            strikethrough=strikethrough,
            color=color,
            dark_color=dark_color,
        )

        # 添加背景色（特殊处理 bg_style）
        if bg_color:
            node["word"]["bg_style"] = {
                "style": 1,
                "color": {
                    "color": bg_color,
                    "dark_color": "",
                },
            }

        return node

    @staticmethod
    def _merge_text_nodes(nodes: list[dict]) -> list[dict]:
        """合并相邻的普通文本节点（无样式、无颜色、同字号）。"""
        if not nodes:
            return nodes
        merged: list[dict] = [nodes[0]]
        for node in nodes[1:]:
            last = merged[-1]
            if (
                last["node_type"] == 1
                and node["node_type"] == 1
                and not last["word"]["style"]
                and not node["word"]["style"]
                and last["word"]["font_level"] == "regular"
                and node["word"]["font_level"] == "regular"
                and not last["word"]["color"]
                and not node["word"]["color"]
                and "bg_style" not in last["word"]
                and "bg_style" not in node["word"]
            ):
                last["word"]["words"] += node["word"]["words"]
            else:
                merged.append(node)
        return merged

    @staticmethod
    def _elements_to_plain_text(elements: list | None) -> str:
        """将 Lark TextElement 列表拼接为纯文本。"""
        if not elements:
            return ""
        parts: list[str] = []
        for elem in elements:
            text_run = getattr(elem, "text_run", None)
            if text_run and text_run.content:
                parts.append(text_run.content)
            equation = getattr(elem, "equation", None)
            if equation and equation.content:
                parts.append(equation.content)
        return "".join(parts)

    @staticmethod
    def _get_align(style: Any) -> int | None:
        """从 block style 中提取对齐方式。"""
        if style is None:
            return None
        align = getattr(style, "align", None)
        if align is None:
            return None
        # Lark: 1=左, 2=居中, 3=右
        # B站 Opus: 0=左, 1=居中, 2=右
        mapping = {1: 0, 2: 1, 3: 2}
        return mapping.get(align)

    def _calc_list_level(self, block: Block) -> int:
        """计算列表项的嵌套层级（从 1 开始）。"""
        level = 1
        current_id = block.block_id
        visited = {current_id}
        while True:
            parent_block = self._blocks.get(current_id)
            if parent_block is None:
                break
            parent_id = parent_block.parent_id
            if not parent_id or parent_id in visited:
                break
            visited.add(parent_id)
            parent = self._blocks.get(parent_id)
            if parent is None:
                break
            bt = parent.block_type
            if bt in (12, 13):  # 父块也是列表
                level += 1
                current_id = parent_id
            else:
                break
        return min(level, 3)  # B站最多 3 级

    def _calc_list_order(
        self,
        block: Block,
        level: int,
        context: dict,
        list_type: str,
    ) -> int:
        """计算同一层级中的序号。"""
        key = f"{list_type}_l{level}"
        context.setdefault("list_orders", {})
        orders = context["list_orders"]
        orders[key] = orders.get(key, 0) + 1
        return orders[key]

    def _get_list_hash(self, block: Block, level: int) -> str:
        """生成或获取列表组的 combine_hash。"""
        # 对于嵌套列表，每层需要独立的 hash
        # 使用 block_id 作为唯一标识的基础
        return f"list_{int(time.time() * 1000)}_{block.block_id[-8:]}"

    def _download_image(self, file_token: str) -> bytes:
        """从飞书下载图片文件。"""
        request = DownloadMediaRequest.builder().file_token(file_token).build()
        response = self._client.drive.v1.media.download(request)
        if not response.success():
            raise RuntimeError(f"下载图片失败: {response.code} {response.msg}")
        return response.file.read()


# ---------------------------------------------------------------------------
# Block Type → 转换方法映射
# block_type 值与 block 对象上的字段名对应
# Heading1~9 使用通用的 _convert_heading_X 方法
# ---------------------------------------------------------------------------
_BLOCK_CONVERTERS: dict[int, str] = {
    1: "_convert_page",  # Page
    2: "_convert_text",  # Text
    12: "_convert_bullet",  # Bullet
    13: "_convert_ordered",  # Ordered
    14: "_convert_code",  # Code
    19: "_convert_callout",  # Callout
    22: "_convert_divider",  # Divider
    27: "_convert_image",  # Image
    34: "_convert_quote",  # QuoteContainer
}

# 动态注册 heading 转换器 (block_type 3~11 → 都指向 _convert_heading)
for bt in range(3, 12):  # 3=heading1, ..., 11=heading9
    _BLOCK_CONVERTERS[bt] = "_convert_heading"
