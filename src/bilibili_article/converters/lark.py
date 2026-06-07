"""
飞书云文档 (Lark Docx) → Opus 转换器。

直接调用飞书 REST API（不使用 lark_oapi SDK），
获取文档块数据后递归遍历块树，转换为 B站 Opus 格式段落。

支持的飞书块类型：
  - text             → 普通段落
  - heading1~3       → 标题段落
  - heading4~9       → 加粗正文
  - bullet/ordered   → 列表段落
  - code             → 代码块段落
  - quote_container  → 引用段落
  - divider          → 分割线段落
  - image            → 图片段落（自动下载并上传到 B站）
  - callout/grid/table → 展平子块
"""

from __future__ import annotations

import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING, Any

import requests

from bilibili_article.client import BiliApiError, BiliClient
from bilibili_article.converters.base import BaseConverter
from bilibili_article.log import logger
from bilibili_article.opus import (
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

if TYPE_CHECKING:
    from bilibili_article.models import InlineNode, Paragraph

# =============================================================================
# 常量
# =============================================================================

LARK_API_BASE = "https://open.feishu.cn/open-apis"

# 飞书文字颜色索引 → 十六进制颜色
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
    8: "#ffd9e4",  # 红色背景
    9: "#e5ffeb",  # 浅薄荷
}
# 代码语言 ID → 名称
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

# Block type → 转换方法名
_BLOCK_CONVERTERS: dict[int, str] = {
    1: "_convert_page",
    2: "_convert_text",
    12: "_convert_bullet",
    13: "_convert_ordered",
    14: "_convert_code",
    19: "_convert_callout",
    22: "_convert_divider",
    27: "_convert_image",
    34: "_convert_quote",
}
for bt in range(3, 12):  # heading1~9
    _BLOCK_CONVERTERS[bt] = "_convert_heading"
# 展平类容器（子块自动遍历）
for bt in (24, 25, 30, 31, 32):
    _BLOCK_CONVERTERS[bt] = "_convert_skip"


# =============================================================================
# 飞书 REST 客户端
# =============================================================================


class _LarkHttpClient:
    """飞书 API 的简单 HTTP 客户端（自动管理 tenant_access_token）。"""

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "bilibili-article/0.1.0 (Python requests)"
        self._tenant_token: str | None = None

    def _ensure_token(self) -> str:
        if self._tenant_token:
            return self._tenant_token
        resp = self._session.post(
            f"{LARK_API_BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        data = resp.json()
        self._tenant_token = data["tenant_access_token"]
        assert self._tenant_token is not None
        self._session.headers["Authorization"] = f"Bearer {self._tenant_token}"
        return self._tenant_token

    def get(self, path: str, **kwargs) -> dict:
        """发送 GET 请求并返回 JSON 响应。"""
        self._ensure_token()
        resp = self._session.get(f"{LARK_API_BASE}{path}", **kwargs)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"飞书 API 错误: [{data.get('code')}] {data.get('msg')}")
        return data

    def get_bytes(self, path: str, **kwargs) -> bytes:
        """发送 GET 请求并返回原始字节（用于下载文件）。"""
        self._ensure_token()
        resp = self._session.get(f"{LARK_API_BASE}{path}", **kwargs)
        if resp.status_code != 200:
            raise RuntimeError(f"飞书文件下载失败: HTTP {resp.status_code}")
        return resp.content


# =============================================================================
# 转换器
# =============================================================================


class LarkDocxConverter(BaseConverter):
    """将飞书云文档转换为 B站 Opus 格式段落列表。"""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        document_id: str,
        bili_client: BiliClient,
        *,
        dry_run: bool = False,
    ):
        self.document_id = document_id
        self.bili_client = bili_client
        self._dry_run = dry_run
        self._lark = _LarkHttpClient(app_id, app_secret)

        # block_id → block dict
        self._blocks: dict[str, dict] = {}
        self._root_block_id: str = ""

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def fetch_document_info(self) -> dict[str, Any]:
        """获取文档基本信息。"""
        data = self._lark.get(f"/docx/v1/documents/{self.document_id}")
        doc = data["data"]["document"]
        return {
            "document_id": doc["document_id"],
            "title": doc["title"],
            "revision_id": doc["revision_id"],
        }

    def convert(self) -> list[Paragraph]:  # type: ignore[misc]
        """执行转换，返回 Opus paragraphs 列表。"""
        self._load_blocks()
        paragraphs: list[Paragraph] = []
        self._walk_block(self._root_block_id, paragraphs, context={})
        return paragraphs

    # ------------------------------------------------------------------
    # 块数据加载
    # ------------------------------------------------------------------

    def _load_blocks(self) -> None:
        """分页加载所有块，构建 block_id → block_dict 映射。"""
        items: list[dict] = []  # raw API response items
        page_token = ""
        while True:
            params = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = self._lark.get(
                f"/docx/v1/documents/{self.document_id}/blocks",
                params=params,
            )
            items.extend(data["data"]["items"])
            if not data["data"].get("has_more"):
                break
            page_token = data["data"]["page_token"]

        # 构建映射并找到根节点
        for block in items:
            bid = block["block_id"]
            self._blocks[bid] = block
            if block.get("parent_id") == "":
                self._root_block_id = bid

        if not self._root_block_id and items:
            # 如果没有 parent_id=="" 的块，第一个块就是根
            self._root_block_id = items[0]["block_id"]

        logger.info(f"  已加载 {len(self._blocks)} 个块")

    # ------------------------------------------------------------------
    # 树遍历
    # ------------------------------------------------------------------

    def _walk_block(
        self,
        block_id: str,
        paragraphs: list[Paragraph],
        context: dict,
        depth: int = 0,
    ) -> None:
        """深度优先遍历块树，将块转换为 Opus 段落。"""
        block = self._blocks.get(block_id)
        if block is None:
            return

        block_type = block["block_type"]
        prefix = "  " * depth

        # 根据 block_type 分发处理
        method_name = _BLOCK_CONVERTERS.get(block_type)
        if method_name:
            method = getattr(self, method_name, None)
            if method:
                method(block, paragraphs, context, prefix)

        # 递归处理子块
        for child_id in block.get("children") or []:
            self._walk_block(child_id, paragraphs, context, depth)

    # ------------------------------------------------------------------
    # 块转换器
    # ------------------------------------------------------------------

    def _convert_text(
        self, block: dict, paragraphs: list[Paragraph], context: dict, prefix: str
    ) -> None:
        """处理文本块 (block_type=2)。"""
        text = block.get("text")
        if not text:
            return
        nodes = self._elements_to_nodes(text.get("elements", []))
        align = self._get_align(text.get("style"))
        paragraphs.append(make_text_paragraph(nodes, align=align))

    def _convert_page(
        self, block: dict, paragraphs: list[Paragraph], context: dict, prefix: str
    ) -> None:
        """处理页面块 (block_type=1) — 根节点，子块会自动遍历。"""
        pass

    def _convert_skip(
        self, block: dict, paragraphs: list[Paragraph], context: dict, prefix: str
    ) -> None:
        pass

    def _convert_heading(
        self, block: dict, paragraphs: list[Paragraph], context: dict, prefix: str
    ) -> None:
        """处理标题块 (block_type=3~11 → heading1~heading9)。"""
        # 从 block_type 推断标题级别
        heading_level = block["block_type"] - 2  # 3→1, ..., 11→9
        heading_key = f"heading{heading_level}"
        heading = block.get(heading_key)
        if not heading:
            return
        text = self._elements_to_plain_text(heading.get("elements", []))

        if heading_level <= 3:
            paragraphs.append(make_heading_paragraph(text, heading_level))
        else:
            # H4~H9：B站不支持，用加粗正文代替
            nodes = self._elements_to_nodes(heading.get("elements", []))
            # 如果节点列表只有普通文本，改为加粗
            if len(nodes) == 1 and nodes[0]["node_type"] == 1:
                nodes[0]["word"]["style"]["bold"] = True  # type: ignore[union-attr]
            paragraphs.append(make_text_paragraph(nodes))

    def _convert_bullet(
        self, block: dict, paragraphs: list[Paragraph], context: dict, prefix: str
    ) -> None:
        """处理无序列表块 (block_type=12)。"""
        bullet = block.get("bullet")
        if not bullet:
            return
        # 计算列表嵌套层级
        level = self._calc_list_level(block)
        nodes = self._elements_to_nodes(bullet.get("elements", []))
        combine_hash = self._get_list_hash(block, level)
        order = self._calc_list_order(block, level, context, "bullet")
        align = self._get_align(bullet.get("style"))

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
        self, block: dict, paragraphs: list[Paragraph], context: dict, prefix: str
    ) -> None:
        ordered = block.get("ordered")
        if not ordered:
            return
        level = self._calc_list_level(block)
        nodes = self._elements_to_nodes(ordered.get("elements", []))
        combine_hash = self._get_list_hash(block, level)
        order = self._calc_list_order(block, level, context, "ordered")
        align = self._get_align(ordered.get("style"))

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
        self, block: dict, paragraphs: list[Paragraph], context: dict, prefix: str
    ) -> None:
        """处理代码块 (block_type=14)。"""
        code = block.get("code")
        if not code:
            return
        # 收集代码内容（所有 text_run 的 content 拼接）
        content_parts: list[str] = []
        lang = ""
        for elem in code.get("elements", []):
            text_run = elem.get("text_run")
            if text_run and text_run.get("content"):
                content_parts.append(text_run["content"])
        content = "".join(content_parts)

        # 获取语言
        code_style = code.get("style") or {}
        lang_id = code_style.get("language")
        if lang_id is not None:
            lang = _CODE_LANG_MAP.get(lang_id, "")

        if content:
            paragraphs.append(make_code_paragraph(content, lang))

    def _convert_divider(
        self, block: dict, paragraphs: list[Paragraph], context: dict, prefix: str
    ) -> None:
        """处理分割线 (block_type=22)。"""
        paragraphs.append(make_divider_paragraph())

    def _convert_image(
        self, block: dict, paragraphs: list[Paragraph], context: dict, prefix: str
    ) -> None:
        """处理图片 (block_type=27)：下载 → 上传 B站 → 追加段落。"""
        image = block.get("image")
        if not image:
            return
        token = image.get("token")
        if not token:
            return

        logger.info(f"{prefix}正在处理图片: token={token}")

        if self._dry_run:
            caption = (image.get("caption") or {}).get("content", "")
            paragraphs.append(
                make_image_paragraph(
                    f"lark://{token}",
                    800,
                    600,
                    0,
                    comment=caption,
                )
            )
            logger.info(f"{prefix}  [dry-run] 跳过下载和上传: token={token}")
            return

        try:
            image_data = self._download_image(token)
            # 写入临时文件
            suffix = ".png"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(image_data)
                tmp_path = Path(tmp.name)

            try:
                info = self.bili_client.upload_image(tmp_path)
                caption = (image.get("caption") or {}).get("content", "")
                paragraphs.append(
                    make_image_paragraph(
                        info["url"],
                        info["width"],
                        info["height"],
                        info.get("size", 0),
                        comment=caption,
                    )
                )
                logger.info(f"{prefix}  → 上传成功: {info['url']}")
            finally:
                tmp_path.unlink()
        except BiliApiError as e:
            logger.error(f"{prefix}  [错误] 图片上传失败: {e}")
        except Exception as e:
            logger.error(f"{prefix}  [错误] 图片处理异常: {e}")

    def _convert_quote(
        self, block: dict, paragraphs: list[Paragraph], context: dict, prefix: str
    ) -> None:
        """处理引用容器 (block_type=34) — 遍历子块并包装为引用段落。"""
        # quote_container 的子块都是 text 类型，需要将它们组合为引用段落。
        # B站 Opus 引用块的 combine_hash 需要共享同一个值。
        if not block.get("children"):
            return
        combine_hash = f"blockquote_{int(time.time() * 1000000)}_{block['block_id']}"
        for child_id in block["children"]:
            child = self._blocks.get(child_id)
            if child is None:
                continue
            text = child.get("text")
            if not text:
                continue
            nodes = self._elements_to_nodes(text.get("elements", []))
            align = self._get_align(text.get("style"))
            paragraphs.append(
                make_blockquote_paragraph(
                    nodes,
                    combine_hash=combine_hash,
                    align=align,
                )
            )

    def _convert_callout(
        self, block: dict, paragraphs: list[Paragraph], context: dict, prefix: str
    ) -> None:
        """处理高亮块 (block_type=19) — 以普通正文输出子块。"""
        # callout 子块会通过递归遍历自动处理
        pass

    # ------------------------------------------------------------------
    # 内联元素转换
    # ------------------------------------------------------------------

    def _elements_to_nodes(self, elements: list) -> list[InlineNode]:  # type: ignore[return,misc]
        """将飞书元素列表转换为 Opus 文本节点列表。"""
        nodes: list[InlineNode] = []  # type: ignore[valid-type]
        for elem in elements:
            text_run = elem.get("text_run")
            equation = elem.get("equation")
            if text_run and text_run.get("content"):
                nodes.append(self._text_run_to_node(text_run))
            elif equation and equation.get("content"):
                nodes.append(make_formula_node(equation["content"]))

        # 合并相邻的普通文本节点
        return self._merge_text_nodes(nodes)  # type: ignore[return-type]

    def _text_run_to_node(self, text_run: dict) -> InlineNode:  # type: ignore[misc]
        """将单个 text_run 转换为 Opus 文本节点。"""
        content = text_run["content"]
        style = text_run.get("text_element_style") or {}

        bold = style.get("bold", False) is True
        italic = style.get("italic", False) is True
        underline = style.get("underline", False) is True
        strikethrough = style.get("strikethrough", False) is True
        inline_code = style.get("inline_code", False) is True

        # 颜色
        color = ""
        dark_color = ""
        if inline_code:
            color = "#c7254e"
        elif style.get("text_color") is not None:
            color = _TEXT_COLOR_MAP.get(style["text_color"], "")

        # 背景色
        bg_color = ""
        if style.get("background_color") is not None:
            bg_color = _BG_COLOR_MAP.get(style["background_color"], "")

        # 超链接
        link = style.get("link")
        if link and link.get("url"):
            # 需要 URL 解码
            url = urllib.parse.unquote(link["url"])
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
                "color": {"color": bg_color, "dark_color": "", "bili_theme": ""},
            }
        return node

    @staticmethod
    def _merge_text_nodes(nodes: list[InlineNode]) -> list[InlineNode]:
        """合并相邻的普通文本节点（无样式、无颜色、同字号）。"""
        if not nodes:
            return nodes
        merged = [nodes[0]]
        for node in nodes[1:]:
            last = merged[-1]
            if (
                last["node_type"] == 1
                and node["node_type"] == 1
                and not last["word"]["style"]  # type: ignore[union-attr]
                and not node["word"]["style"]  # type: ignore[union-attr]
                and last["word"]["font_level"] == "regular"  # type: ignore[union-attr]
                and node["word"]["font_level"] == "regular"  # type: ignore[union-attr]
                and not last["word"]["color"]  # type: ignore[union-attr]
                and not node["word"]["color"]  # type: ignore[union-attr]
                and "bg_style" not in last["word"]  # type: ignore[union-attr]
                and "bg_style" not in node["word"]  # type: ignore[union-attr]
            ):
                last["word"]["words"] += node["word"]["words"]  # type: ignore[union-attr]
            else:
                merged.append(node)
        return merged

    @staticmethod
    def _elements_to_plain_text(elements: list) -> str:
        """将 Lark TextElement 列表拼接为纯文本。"""
        if not elements:
            return ""
        parts: list[str] = []
        for elem in elements:
            text_run = elem.get("text_run")
            if text_run and text_run.get("content"):
                parts.append(text_run["content"])
            equation = elem.get("equation")
            if equation and equation.get("content"):
                parts.append(equation["content"])
        return "".join(parts)

    @staticmethod
    def _get_align(style: dict | None) -> int | None:
        """从 block style 中提取对齐方式。"""
        if not style:
            return None
        align = style.get("align")
        if align is None:
            return None
        # Lark: 1=左, 2=居中, 3=右 → B站: 0=左, 1=居中, 2=右
        return {1: 0, 2: 1, 3: 2}.get(align)

    # ------------------------------------------------------------------
    # 列表辅助
    # ------------------------------------------------------------------

    def _calc_list_level(self, block: dict) -> int:
        """计算列表项的嵌套层级（从 1 开始）。"""
        level = 1
        current_id = block["block_id"]
        visited = {current_id}
        while True:
            parent_block = self._blocks.get(current_id)
            if not parent_block:
                break
            parent_id = parent_block.get("parent_id", "")
            if not parent_id or parent_id in visited:
                break
            visited.add(parent_id)
            parent = self._blocks.get(parent_id)
            if not parent:
                break
            if parent["block_type"] in (12, 13):
                level += 1
                current_id = parent_id
            else:
                break
        return min(level, 3)

    @staticmethod
    def _calc_list_order(block: dict, level: int, context: dict, list_type: str) -> int:
        """计算同一层级中的序号。"""
        key = f"{list_type}_l{level}"
        context.setdefault("list_orders", {})
        orders = context["list_orders"]
        orders[key] = orders.get(key, 0) + 1
        return orders[key]

    @staticmethod
    def _get_list_hash(block: dict, level: int) -> str:
        """生成或获取列表组的 combine_hash。"""
        # 对于嵌套列表，每层需要独立的 hash
        # 使用 block_id 作为唯一标识的基础
        return f"list_{int(time.time() * 1000)}_{block['block_id'][-8:]}"

    # ------------------------------------------------------------------
    # 文件下载
    # ------------------------------------------------------------------

    def _download_image(self, file_token: str) -> bytes:
        """从飞书下载图片文件。"""
        return self._lark.get_bytes(f"/drive/v1/medias/{file_token}/download")
