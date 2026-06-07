"""
Markdown → Opus 转换器。

使用 mistune 将 Markdown 解析为 AST，再递归遍历 AST 转换为 B站 Opus 格式的 paragraphs 列表。
支持图片自动上传到 B站 图床。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

import mistune

from bilibili_article.client import BiliApiError, BiliClient
from bilibili_article.converters.base import BaseConverter
from bilibili_article.log import logger
from bilibili_article.opus import (
    make_blockquote_paragraph,
    make_code_paragraph,
    make_divider_paragraph,
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

# mistune AST token 类型
_Token = dict[str, Any]


# =============================================================================
# 常量
# =============================================================================

# mistune 启用插件列表
_MISTUNE_PLUGINS = ["strikethrough", "table", "footnotes", "task_lists"]

# 行内代码的前景色
_INLINE_CODE_COLOR = "#c7254e"


# =============================================================================
# 模块级辅助函数
# =============================================================================


def _collect_list_item_content(item: _Token) -> tuple[list[_Token], _Token | None]:
    """从 list_item token 中提取 mistune 内联 token 列表和嵌套列表。"""
    inline_children: list[_Token] = []
    nested_list: _Token | None = None

    for child in item.get("children", []):
        if child["type"] in ("block_text", "paragraph"):
            inline_children.extend(child.get("children", []))
        elif child["type"] == "list":
            nested_list = child

    return inline_children, nested_list


def _apply_style(nodes: list[InlineNode], **style: bool) -> list[InlineNode]:
    """将样式应用到所有 TextNode 上（支持叠加，如 bold+italic）。"""
    for node in nodes:
        if node.get("node_type") == 1:
            w = cast("dict[str, Any]", node)["word"]
            for key, val in style.items():
                if val:
                    w["style"][key] = True
                else:
                    w["style"].pop(key, None)
    return nodes


def _has_visible_text(nodes: list[InlineNode]) -> bool:
    """判断 nodes 列表中是否有可见文本内容。"""
    for n in nodes:
        if n.get("node_type") == 1:
            words = cast("dict[str, Any]", n)["word"]["words"]
            if words.strip():
                return True
        elif n.get("node_type") == 4:
            return True
    return False


# =============================================================================
# 转换器
# =============================================================================


class MarkdownConverter(BaseConverter):
    """将本地 Markdown 文件转换为 Opus paragraphs 列表。"""

    def __init__(
        self, client: BiliClient, markdown_file_path: Path, *, dry_run: bool = False
    ):
        self.client = client
        self.base_dir = markdown_file_path.resolve().parent
        with open(markdown_file_path, "r", encoding="utf-8") as f:
            self._md = f.read()
        self._dry_run = dry_run
        self._counter = 0
        self._parser = mistune.create_markdown(renderer=None, plugins=_MISTUNE_PLUGINS)

    # ==================================================================
    # 公开接口
    # ==================================================================

    def get_title(self) -> str:
        """从 Markdown 内容中提取第一个 H1 标题。"""
        for token in self._parser(self._md):
            t = cast("_Token", token)
            if t["type"] == "heading" and t["attrs"]["level"] == 1:
                return self._extract_text(t)
        return "未命名文章"

    def convert(self) -> list[Paragraph]:
        paragraphs: list[Paragraph] = []
        for token in self._parser(self._md):
            t = cast("_Token", token)
            if t["type"] == "blank_line":
                continue
            self._convert_block(t, paragraphs)
        return paragraphs

    # ==================================================================
    # Block-level conversion
    # ==================================================================

    _BLOCK_HANDLERS: ClassVar[dict[str, str]] = {
        "heading": "_handle_heading",
        "paragraph": "_handle_paragraph",
        "thematic_break": "_handle_thematic_break",
        "block_code": "_handle_block_code",
        "block_quote": "_handle_block_quote",
        "list": "_handle_list",
        "block_html": "_handle_block_html",
    }

    def _convert_block(self, token: _Token, paragraphs: list[Paragraph]) -> None:
        method_name = self._BLOCK_HANDLERS.get(token["type"])
        if method_name:
            getattr(self, method_name)(token, paragraphs)
        else:
            logger.warning(f"未支持的块类型，已跳过: {token['type']}")

    def _handle_heading(self, token: _Token, paragraphs: list[Paragraph]) -> None:
        """# ~ ### 标题"""
        paragraphs.append(
            make_heading_paragraph(self._extract_text(token), token["attrs"]["level"])
        )

    def _handle_paragraph(self, token: _Token, paragraphs: list[Paragraph]) -> None:
        """普通段落。纯图片段落会被识别为图片段落。"""
        children: list[_Token] = token.get("children", [])
        if not children:
            return

        image_indices = [i for i, c in enumerate(children) if c["type"] == "image"]

        if len(image_indices) == len(children):
            for img in children:
                self._process_image_token(img, paragraphs)
            return

        start = 0
        for idx in image_indices:
            if idx > start:
                self._try_append_text_paragraph(children[start:idx], paragraphs)
            self._process_image_token(children[idx], paragraphs)
            start = idx + 1

        if start < len(children):
            self._try_append_text_paragraph(children[start:], paragraphs)

    def _try_append_text_paragraph(
        self, children: list[_Token], paragraphs: list[Paragraph]
    ) -> None:
        """尝试从 inline children 生成文本段落，跳过空白内容。"""
        nodes = self._convert_inline(children)
        if nodes and _has_visible_text(nodes):
            paragraphs.append(make_text_paragraph(nodes))

    def _handle_thematic_break(
        self, token: _Token, paragraphs: list[Paragraph]
    ) -> None:
        """--- 分隔线"""
        paragraphs.append(make_divider_paragraph())

    def _handle_block_code(self, token: _Token, paragraphs: list[Paragraph]) -> None:
        """```lang ... ``` 代码块"""
        lang = (token.get("attrs") or {}).get("info", "") or ""
        paragraphs.append(make_code_paragraph(token["raw"], lang))

    def _handle_block_quote(self, token: _Token, paragraphs: list[Paragraph]) -> None:
        """> 引用块（支持嵌套引用）"""
        self._counter += 1
        combine_hash = f"bq_{int(time.time() * 1000000)}_{self._counter}"

        nodes: list[InlineNode] = []
        parts: list[list[InlineNode]] = []

        for child in token.get("children", []):
            if child["type"] in ("paragraph", "block_text"):
                parts.append(self._convert_inline(child.get("children", [])))
            elif child["type"] == "block_quote":
                parts.append(
                    self._convert_inline(
                        [{"type": "text", "raw": self._extract_text(child)}]
                    )
                )

        for i, part in enumerate(parts):
            if i > 0:
                nodes.append(make_text_node("\n"))
            nodes.extend(part)

        if nodes:
            paragraphs.append(make_blockquote_paragraph(nodes, combine_hash))

    def _handle_list(self, token: _Token, paragraphs: list[Paragraph]) -> None:
        """有序/无序列表（含嵌套和任务列表）"""
        self._counter += 1
        combine_hash = f"list_{int(time.time() * 1000000)}_{self._counter}"
        self._convert_list_items(
            items=token.get("children", []),
            ordered=token["attrs"]["ordered"],
            depth=token["attrs"].get("depth", 0),
            combine_hash=combine_hash,
            paragraphs=paragraphs,
        )

    def _handle_block_html(self, token: _Token, paragraphs: list[Paragraph]) -> None:
        """HTML 块 — 跳过"""
        logger.warning("HTML 块不被支持，已跳过")

    # ==================================================================
    # List helpers
    # ==================================================================

    def _convert_list_items(
        self,
        items: list[_Token],
        ordered: bool,
        depth: int,
        combine_hash: str,
        paragraphs: list[Paragraph],
    ) -> None:
        """递归转换 list_item 列表。"""
        level = min(depth + 1, 3)
        order = 1

        for item in items:
            if item["type"] not in ("list_item", "task_list_item"):
                continue

            inline_children, nested_list = _collect_list_item_content(item)

            if item["type"] == "task_list_item":
                checked = (item.get("attrs") or {}).get("checked", False)
                prefix = "✅ " if checked else "☐ "
                inline_children.insert(0, {"type": "text", "raw": prefix})

            nodes = self._convert_inline(inline_children)

            if ordered:
                paragraphs.append(
                    make_ordered_list_paragraph(nodes, level, order, combine_hash)
                )
            else:
                paragraphs.append(
                    make_unordered_list_paragraph(nodes, level, order, combine_hash)
                )
            order += 1

            if nested_list:
                self._convert_list_items(
                    items=nested_list.get("children", []),
                    ordered=nested_list["attrs"]["ordered"],
                    depth=nested_list["attrs"].get("depth", depth),
                    combine_hash=combine_hash,
                    paragraphs=paragraphs,
                )

    # ==================================================================
    # Inline conversion
    # ==================================================================

    def _convert_inline(self, children: list[_Token]) -> list[InlineNode]:
        """递归将 mistune inline tokens 转换为 Opus InlineNode 列表。

        正确处理嵌套格式，如 ``**_粗斜体_**`` 会得到 ``bold + italic`` 的文本节点。
        """
        nodes: list[InlineNode] = []
        for child in children:
            nodes.extend(self._convert_one_inline(child))
        return nodes

    def _convert_one_inline(self, token: _Token) -> list[InlineNode]:
        """转换单个 mistune inline token 为一个或多个 Opus InlineNode。"""
        t = token["type"]

        if t == "text":
            return [make_text_node(token["raw"])]

        if t == "strong":
            inner = self._convert_inline(token.get("children", []))
            return _apply_style(inner, bold=True)

        if t == "emphasis":
            inner = self._convert_inline(token.get("children", []))
            return _apply_style(inner, italic=True)

        if t == "strikethrough":
            inner = self._convert_inline(token.get("children", []))
            return _apply_style(inner, strikethrough=True)

        if t == "codespan":
            return [make_text_node(token["raw"], color=_INLINE_CODE_COLOR)]

        if t == "link":
            text = self._extract_text(token)
            return [make_link_node(text, token["attrs"]["url"])]

        if t in ("linebreak", "softbreak"):
            return [make_text_node(" ")]

        return []

    @staticmethod
    def _extract_text(token: _Token) -> str:
        """从 AST token 树中递归提取纯文本。"""
        parts: list[str] = []

        if "raw" in token:
            parts.append(token["raw"])

        for child in token.get("children", []):
            parts.append(MarkdownConverter._extract_text(child))

        return "".join(parts)

    # ==================================================================
    # Image handling
    # ==================================================================

    def _process_image_token(self, token: _Token, paragraphs: list[Paragraph]) -> None:
        """处理图片并追加图片段落。"""
        raw_url = token["attrs"]["url"]
        img_path = (
            Path(raw_url)
            if Path(raw_url).is_absolute()
            else (self.base_dir / raw_url).resolve()
        )

        if not img_path.is_file():
            logger.warning(f"图片文件不存在，跳过: {img_path}")
            return

        if self._dry_run:
            paragraphs.append(make_image_paragraph(f"file://{img_path}", 800, 600, 0))
            logger.info(f"[dry-run] 跳过上传: {img_path}")
            return

        logger.info(f"正在上传图片: {img_path}")
        try:
            info = self.client.upload_image(img_path)
            paragraphs.append(
                make_image_paragraph(
                    info["url"], info["width"], info["height"], info.get("size", 0)
                )
            )
            logger.info(f"→ 上传成功: {info['url']}")
        except BiliApiError as e:
            logger.error(f"[错误] 图片上传失败: {e}")
        except Exception as e:
            logger.error(f"[错误] 图片处理异常: {e}")
