"""
Markdown → Opus 转换器。

将本地 Markdown 文件解析为 B站 Opus 格式的 paragraphs 列表。
支持图片自动上传到 B站 图床。
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, TypeGuard

from bilibili_article.client import BiliApiError, BiliClient
from bilibili_article.converters.base import BaseConverter
from bilibili_article.log import logger
from bilibili_article.opus import (
    make_divider_paragraph,
    make_heading_paragraph,
    make_image_paragraph,
    make_ordered_list_paragraph,
    make_text_node,
    make_text_paragraph,
    make_unordered_list_paragraph,
)

if TYPE_CHECKING:
    from bilibili_article.models import InlineNode, Paragraph, TextNode


# 列表检测正则：无序列表（- * +）和有序列表（1. 2. ...）
_UNORDERED_LIST_RE = re.compile(r"^(\s*)([-*+])\s+(.*)")
_ORDERED_LIST_RE = re.compile(r"^(\s*)(\d+)\.\s+(.*)")


def _detect_list_item(line: str) -> tuple[str, int, str] | None:
    """检测行是否为列表项。返回 (type, level, text) 或 None。"""
    # 缩进决定层级：每 2 个空格升一级，最大 3 级
    leading_spaces = len(line) - len(line.lstrip())
    level = min(leading_spaces // 2 + 1, 3)

    u_match = _UNORDERED_LIST_RE.match(line)
    if u_match:
        return ("unordered", level, u_match.group(3))

    o_match = _ORDERED_LIST_RE.match(line)
    if o_match:
        return ("ordered", level, o_match.group(3))

    return None


# 内联 Markdown 解析：**粗体** *斜体* ~~删除线~~ `行内代码`
_INLINE_PATTERN = re.compile(
    r"~~(.*?)~~"  # ~~删除线~~
    r"|`(.*?)`"  # `行内代码`
    r"|\*\*(.*?)\*\*"  # **粗体**
    r"|\*(.*?)\*"  # *斜体*
    r"|(.)"  # 普通字符（fallback）
)


def _is_text_node(node: InlineNode) -> TypeGuard[TextNode]:
    """判断 InlineNode 是否为 TextNode（node_type == 1）。"""
    return node.get("node_type") == 1


def _parse_inline(text: str) -> list[InlineNode]:
    """将一行纯文本解析为 Opus 文本节点列表。"""
    nodes: list[InlineNode] = []

    for match in _INLINE_PATTERN.finditer(text):
        if match.group(1) is not None:  # ~~删除线~~
            nodes.append(make_text_node(match.group(1), strikethrough=True))
        elif match.group(2) is not None:  # `行内代码`
            nodes.append(make_text_node(match.group(2), color="#c7254e"))
        elif match.group(3) is not None:  # **粗体**
            nodes.append(make_text_node(match.group(3), bold=True))
        elif match.group(4) is not None:  # *斜体*
            nodes.append(make_text_node(match.group(4), italic=True))
        elif match.group(5) is not None:  # 普通字符
            ch = match.group(5)
            if nodes and _is_text_node(nodes[-1]):
                last = nodes[-1]
                if (
                    not last["word"]["style"]
                    and last["word"]["font_level"] == "regular"
                    and not last["word"]["color"]
                ):
                    last["word"]["words"] += ch
                else:
                    nodes.append(make_text_node(ch))
            else:
                nodes.append(make_text_node(ch))
    return nodes


class _ListGroupBuilder:
    """列表分组构建器，管理连续列表项的分组和输出。"""

    def __init__(self) -> None:
        self._items: list[dict] = []
        self._type: str | None = None
        self._hash: str = ""
        self._active: bool = False
        self._counter: int = 0

    @property
    def is_active(self) -> bool:
        return self._active

    def start(self, item_type: str) -> None:
        """开始一个新的列表组。"""
        self._counter += 1
        self._type = item_type
        self._hash = f"list_{int(time.time() * 1000000)}_{self._counter}"
        self._items = []
        self._active = True

    def add_item(self, text: str, level: int, order: int) -> None:
        """添加一个列表项。"""
        self._items.append({"level": level, "order": order, "text": text})

    def flush(self, paragraphs: list[Paragraph]) -> None:
        """输出所有缓存的列表项并重置状态。"""
        if not self._active:
            return
        for item in self._items:
            nodes = _parse_inline(item["text"])
            if self._type == "ordered":
                paragraphs.append(
                    make_ordered_list_paragraph(
                        nodes,
                        level=item["level"],
                        order=item["order"],
                        combine_hash=self._hash,
                    )
                )
            else:
                paragraphs.append(
                    make_unordered_list_paragraph(
                        nodes,
                        level=item["level"],
                        order=item["order"],
                        combine_hash=self._hash,
                    )
                )
        self._items = []
        self._active = False
        self._type = None
        self._hash = ""

    def should_start_new_group(self, item_type: str, consecutive_blank: bool) -> bool:
        """判断是否需要开始新列表组。"""
        return not self._active or item_type != self._type or consecutive_blank


def _get_list_order(stripped: str, item_type: str) -> int:
    """计算列表项序号。"""
    if item_type == "ordered":
        m = re.match(r"^(?:\s*)(\d+)\.", stripped)
        return int(m.group(1)) if m else 1
    return 1


class MarkdownConverter(BaseConverter):
    """将本地 Markdown 文件转换为 Opus paragraphs 列表。"""

    def __init__(
        self,
        client: BiliClient,
        markdown_file_path: Path,
        *,
        dry_run: bool = False,
    ):
        self.client = client
        self.base_dir = markdown_file_path.resolve().parent
        with open(markdown_file_path, "r", encoding="utf-8") as f:
            self._md = f.read()
        self._dry_run = dry_run

    def convert(self) -> list[Paragraph]:  # type: ignore[misc,override]
        md = self._md
        lines = md.split("\n")
        paragraphs: list[Paragraph] = []  # type: ignore[valid-type]
        buffer: list[InlineNode] = []  # type: ignore[valid-type]
        list_builder = _ListGroupBuilder()
        consecutive_blank = False

        def flush():
            nonlocal buffer
            if buffer:
                paragraphs.append(make_text_paragraph(buffer))
                buffer = []

        for line in lines:
            stripped = line.strip()

            # 空行 — 中断当前列表组
            if not stripped:
                flush()
                list_builder.flush(paragraphs)
                consecutive_blank = True
                continue

            # 标题
            h_match = re.match(r"^(#{1,3})\s+(.*)", stripped)
            if h_match:
                flush()
                list_builder.flush(paragraphs)
                level = len(h_match.group(1))
                paragraphs.append(make_heading_paragraph(h_match.group(2), level))
                consecutive_blank = False
                continue

            # 图片 ![alt](path)
            img_match = re.match(r"!\[.*?\]\((.*?)\)", stripped)
            if img_match:
                flush()
                list_builder.flush(paragraphs)
                self._process_image(img_match, paragraphs)
                consecutive_blank = False
                continue

            # 分隔线
            if stripped in ("---", "***", "___"):
                flush()
                list_builder.flush(paragraphs)
                paragraphs.append(make_divider_paragraph())
                consecutive_blank = False
                continue

            # 列表检测
            list_info = _detect_list_item(line)
            if list_info:
                flush()  # 刷新之前的文本缓存
                item_type, level, text = list_info

                if list_builder.should_start_new_group(item_type, consecutive_blank):
                    list_builder.flush(paragraphs)
                    list_builder.start(item_type)

                order = _get_list_order(stripped, item_type)
                list_builder.add_item(text, level, order)
                consecutive_blank = False
                continue

            # 普通行 — 刷新列表组
            list_builder.flush(paragraphs)
            buffer.extend(_parse_inline(stripped))
            consecutive_blank = False

        flush()
        list_builder.flush(paragraphs)
        return paragraphs  # type: ignore[return-type]

    def _process_image(self, match: re.Match, paragraphs: list[Paragraph]) -> None:  # type: ignore[misc]
        """处理图片：上传并追加图片段落。"""
        raw_path = match.group(1)
        img_path = (
            Path(raw_path)
            if Path(raw_path).is_absolute()
            else (self.base_dir / raw_path).resolve()
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
                    info["url"],
                    info["width"],
                    info["height"],
                    info.get("size", 0),
                )
            )
            logger.info(f"→ 上传成功: {info['url']}")
        except BiliApiError as e:
            logger.error(f"[错误] 图片上传失败: {e}")
        except Exception as e:
            logger.error(f"[错误] 图片处理异常: {e}")
