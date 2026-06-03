"""
Markdown → Opus 转换器。

将本地 Markdown 文件解析为 B站 Opus 格式的 paragraphs 列表。
支持图片自动上传到 B站 图床。
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from bilibili_article.client import BiliApiError, BiliClient
from bilibili_article.converters.base import BaseConverter
from bilibili_article.opus import (
    make_divider_paragraph,
    make_heading_paragraph,
    make_image_paragraph,
    make_text_node,
    make_text_paragraph,
)

if TYPE_CHECKING:
    from bilibili_article.models import InlineNode, Paragraph

# 内联 Markdown 解析：**粗体** *斜体* ~~删除线~~ `行内代码`
_INLINE_PATTERN = re.compile(
    r"~~(.*?)~~"  # ~~删除线~~
    r"|`(.*?)`"  # `行内代码`
    r"|\*\*(.*?)\*\*"  # **粗体**
    r"|\*(.*?)\*"  # *斜体*
    r"|(.)"  # 普通字符（fallback）
)


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
            if (
                nodes
                and not nodes[-1]["word"]["style"]  # type: ignore[union-attr]
                and nodes[-1]["word"]["font_level"] == "regular"  # type: ignore[union-attr]
                and not nodes[-1]["word"]["color"]  # type: ignore[union-attr]
            ):
                nodes[-1]["word"]["words"] += ch  # type: ignore[union-attr]
            else:
                nodes.append(make_text_node(ch))
    return nodes


class MarkdownConverter(BaseConverter):
    """将 Markdown 字符串转换为 Opus paragraphs 列表。"""

    def __init__(self, client: BiliClient, base_dir: str, md: str = ""):
        self.client = client
        self.base_dir = base_dir
        self._md = md

    def convert(self) -> list[Paragraph]:  # type: ignore[misc,override]
        md = self._md
        lines = md.split("\n")
        paragraphs: list[Paragraph] = []  # type: ignore[valid-type]
        buffer: list[InlineNode] = []  # type: ignore[valid-type]

        def flush():
            nonlocal buffer
            if buffer:
                paragraphs.append(make_text_paragraph(buffer))
                buffer = []

        for line in lines:
            stripped = line.strip()

            if not stripped:
                flush()
                continue

            # 标题
            h_match = re.match(r"^(#{1,3})\s+(.*)", stripped)
            if h_match:
                flush()
                level = len(h_match.group(1))
                paragraphs.append(make_heading_paragraph(h_match.group(2), level))
                continue

            # 图片 ![alt](path)
            img_match = re.match(r"!\[.*?\]\((.*?)\)", stripped)
            if img_match:
                flush()
                self._process_image(img_match, paragraphs)
                continue

            # 分隔线
            if stripped in ("---", "***", "___"):
                flush()
                paragraphs.append(make_divider_paragraph())
                continue

            # 普通行
            buffer.extend(_parse_inline(stripped))

        flush()
        return paragraphs  # type: ignore[return-type]

    def _process_image(self, match: re.Match, paragraphs: list[Paragraph]) -> None:  # type: ignore[misc]
        """处理图片：上传并追加图片段落。"""
        raw_path = match.group(1)
        img_path = (
            raw_path
            if os.path.isabs(raw_path)
            else os.path.normpath(os.path.join(self.base_dir, raw_path))
        )

        if not os.path.isfile(img_path):
            print(f"  [警告] 图片文件不存在，跳过: {img_path}")
            return

        print(f"  正在上传图片: {img_path}")
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
            print(f"    → 上传成功: {info['url']}")
        except BiliApiError as e:
            print(f"    [错误] 图片上传失败: {e}")
        except Exception as e:
            print(f"    [错误] 图片处理异常: {e}")
