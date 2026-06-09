"""
Markdown → IR Document 转换器。

使用 mistune 将 Markdown 解析为 AST，再递归遍历 AST 转换为
平台无关的 IR Document。图片仅记录本地路径，上传由 Publisher 负责。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar, cast

import mistune

from bilibili_article.converters.base import BaseConverter
from bilibili_article.document import (
    Block,
    Blockquote,
    CodeBlock,
    Divider,
    Document,
    Heading,
    ImageBlock,
    ListItem,
    OrderedList,
    Paragraph,
    TextRun,
    UnorderedList,
)
from bilibili_article.log import logger

# mistune AST token 类型
_Token = dict[str, Any]


# =============================================================================
# 常量
# =============================================================================

# mistune 启用插件列表
_MISTUNE_PLUGINS = ["strikethrough", "task_lists"]

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


# =============================================================================
# 转换器
# =============================================================================


class MarkdownConverter(BaseConverter):
    """将本地 Markdown 文件转换为 IR Document。"""

    def __init__(self, markdown_file_path: Path):
        self.base_dir = markdown_file_path.resolve().parent
        with open(markdown_file_path, "r", encoding="utf-8") as f:
            self._md = f.read()
        parser = mistune.create_markdown(renderer=None, plugins=_MISTUNE_PLUGINS)
        self._parsed = cast("list[dict[str, Any]]", parser(self._md))
        with open(
            markdown_file_path.with_suffix(".ast.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(self._parsed, f, ensure_ascii=False, indent=2)

    # ==================================================================
    # 公开接口
    # ==================================================================

    def get_title(self) -> str:
        """从 Markdown 内容中提取第一个 H1 标题。"""
        for token in self._parsed:
            if token["type"] == "heading" and token["attrs"]["level"] == 1:
                return self._extract_text(token)
        return "未命名文章"

    def convert(self) -> Document:
        blocks: list[Block] = []
        for token in self._parsed:
            if token["type"] == "blank_line":
                continue
            result = self._convert_block(token)
            if isinstance(result, list):
                blocks.extend(result)
            elif result is not None:
                blocks.append(result)
        title = self.get_title()
        return Document(title=title, blocks=blocks)

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

    def _convert_block(self, token: _Token) -> Block | list[Block] | None:
        """将单个 mistune block token 转换为 IR Block(s)。"""
        method_name = self._BLOCK_HANDLERS.get(token["type"])
        if method_name:
            return getattr(self, method_name)(token)
        logger.warning(f"未支持的块类型，已跳过: {token['type']}")
        return None

    def _handle_heading(self, token: _Token) -> Heading:
        """# ~ ### 标题（支持富文本格式）"""
        level = token["attrs"]["level"]
        children = self._convert_inline(token.get("children", []))
        return Heading(level=level, children=children)

    def _handle_paragraph(self, token: _Token) -> Block | None:
        """普通段落。纯图片段落（含 softbreak 间隔）返回多个 ImageBlock。"""
        children: list[_Token] = token.get("children", [])
        if not children:
            return None

        image_indices = [i for i, c in enumerate(children) if c["type"] == "image"]

        # 纯图片段落（允许 softbreak/linebreak 间隔）
        non_image = [
            c
            for i, c in enumerate(children)
            if i not in image_indices and c["type"] not in ("softbreak", "linebreak")
        ]
        if image_indices and not non_image:
            # 纯图片，中间只有换行：收集所有 ImageBlock
            image_blocks: list[ImageBlock] = []
            for idx in image_indices:
                img = self._process_image_token(children[idx])
                if img is not None:
                    image_blocks.append(img)
            # 返回多个 ImageBlock → 交给 convert() 展平
            if len(image_blocks) == 1:
                return image_blocks[0]
            if len(image_blocks) > 1:
                return image_blocks  # type: ignore[return-value]
            return None

        # 图文混合段落：分割为文本段落 + 图片
        result_blocks: list[Block] = []
        start = 0
        for idx in image_indices:
            if idx > start:
                text_block = self._make_text_block(children[start:idx])
                if text_block is not None:
                    result_blocks.append(text_block)
            img_block = self._process_image_token(children[idx])
            if img_block is not None:
                result_blocks.append(img_block)
            start = idx + 1

        if start < len(children):
            text_block = self._make_text_block(children[start:])
            if text_block is not None:
                result_blocks.append(text_block)

        if len(result_blocks) == 1:
            return result_blocks[0]

        # 多个段落以 Blockquote 包裹
        if result_blocks:
            return Blockquote(children=result_blocks)
        return None

    def _make_text_block(self, children: list[_Token]) -> Paragraph | None:
        """从 inline children 生成 IR Paragraph。"""
        text_runs = self._convert_inline(children)
        if text_runs:
            return Paragraph(children=text_runs)
        return None

    def _handle_thematic_break(self, token: _Token) -> Divider:
        """--- 分隔线"""
        return Divider()

    def _handle_block_code(self, token: _Token) -> CodeBlock:
        """```lang ... ``` 代码块"""
        lang = (token.get("attrs") or {}).get("info", "") or ""
        return CodeBlock(language=lang, content=token["raw"])

    def _handle_block_quote(self, token: _Token) -> Blockquote:
        """> 引用块（支持嵌套引用）"""
        children: list[Block] = []

        for child in token.get("children", []):
            if child["type"] in ("paragraph", "block_text"):
                text_runs = self._convert_inline(child.get("children", []))
                if text_runs:
                    children.append(Paragraph(children=text_runs))
            elif child["type"] == "block_quote":
                # 嵌套引用：递归处理
                nested = self._handle_block_quote(child)
                children.append(nested)

        return Blockquote(children=children)

    def _handle_list(self, token: _Token) -> OrderedList | UnorderedList:
        """有序/无序列表（含嵌套和任务列表）"""
        ordered = token["attrs"]["ordered"]
        items: list[ListItem] = []

        for item in token.get("children", []):
            if item["type"] not in ("list_item", "task_list_item"):
                continue

            inline_children, nested_list = _collect_list_item_content(item)

            if item["type"] == "task_list_item":
                checked = (item.get("attrs") or {}).get("checked", False)
                prefix = "✅ " if checked else "☐ "
                inline_children.insert(0, {"type": "text", "raw": prefix})

            item_blocks: list[Block] = []

            # 列表项文本内容
            text_runs = self._convert_inline(inline_children)
            if text_runs:
                item_blocks.append(Paragraph(children=text_runs))

            # 嵌套列表
            if nested_list:
                nested = self._handle_list(nested_list)
                item_blocks.append(nested)

            items.append(ListItem(blocks=item_blocks))

        if ordered:
            return OrderedList(items=items)
        return UnorderedList(items=items)

    def _handle_block_html(self, token: _Token) -> None:
        """HTML 块 — 跳过"""
        html_preview = token.get("raw", "")[:60]
        logger.warning(f"HTML 块不被支持，已跳过: {html_preview!r}")
        return

    # ==================================================================
    # Inline conversion
    # ==================================================================

    def _convert_inline(self, children: list[_Token]) -> list[TextRun]:
        """递归将 mistune inline tokens 转换为 IR TextRun 列表。"""
        runs: list[TextRun] = []
        for child in children:
            runs.extend(self._convert_one_inline(child))
        return runs

    def _convert_one_inline(self, token: _Token) -> list[TextRun]:
        """转换单个 mistune inline token 为一个或多个 IR TextRun。"""
        t = token["type"]

        if t == "text":
            return [TextRun(text=token["raw"])]

        if t == "strong":
            inner = self._convert_inline(token.get("children", []))
            for run in inner:
                run.bold = True
            return inner

        if t == "emphasis":
            inner = self._convert_inline(token.get("children", []))
            for run in inner:
                run.italic = True
            return inner

        if t == "strikethrough":
            inner = self._convert_inline(token.get("children", []))
            for run in inner:
                run.strikethrough = True
            return inner

        if t == "codespan":
            return [
                TextRun(text=token["raw"], inline_code=True, color=_INLINE_CODE_COLOR)
            ]

        if t == "link":
            text = self._extract_text(token)
            return [TextRun(text=text, link_url=token["attrs"]["url"])]

        if t in ("linebreak", "softbreak"):
            return [TextRun(text=" ")]

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

    def _process_image_token(self, token: _Token) -> ImageBlock | None:
        """处理图片 token，返回 ImageBlock（仅记录路径，不上传）。"""
        raw_url = token["attrs"]["url"]
        img_path = (
            Path(raw_url)
            if Path(raw_url).is_absolute()
            else (self.base_dir / raw_url).resolve()
        )

        if not img_path.is_file():
            logger.warning(f"图片文件不存在，跳过: {img_path}")
            return None

        attrs = token.get("attrs") or {}
        alt_text = attrs.get("alt", "")
        # Markdown 图片标题语法: ![alt](url "title") → 用作 caption/描述
        caption = attrs.get("title") or attrs.get("alt", "")
        logger.info(f"  发现图片: {img_path}")
        return ImageBlock(source=str(img_path), alt_text=alt_text, caption=caption)
