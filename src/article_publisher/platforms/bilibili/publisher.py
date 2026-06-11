"""
B站 Publisher — 将 IR Document 发布到 B站 Opus 专栏草稿箱。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from article_publisher.document import (
    Block,
    Blockquote,
    CodeBlock,
    Divider,
    Document,
    Formula,
    Heading,
    ImageBlock,
    InlineElement,
    ListItem,
    OrderedList,
    TextRun,
    UnorderedList,
)
from article_publisher.document import Paragraph as IRParagraph
from article_publisher.platforms.bilibili.opus import (
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
    from collections.abc import Sequence

    from article_publisher.platforms.bilibili.client import BiliClient
    from article_publisher.platforms.bilibili.models import (
        ArgPayload,
        InlineNode,
        Paragraph,
        Payload,
    )


@dataclass
class BiliPublishConfig:
    """B站 发布配置参数集合。"""

    category_id: int = 15
    article_id: int | None = None
    private_pub: int = 2
    reprint: int = 1
    original: int = 1
    comment_selected: int = 0
    up_closed_reply: int = 0
    timer_pub_time: int = 0
    list_id: int = 0
    image_urls: list[str] | None = None
    is_aigc: int = 0
    hashtag_ids: list[int] | None = None
    cover_path: Path | None = None
    """命令行传入的自定义封面图片路径，优先于 doc.cover"""


def _build_summary(doc: Document) -> str:
    """从 IR Document 中提取纯文本摘要（取前 200 字）。"""
    texts: list[str] = []

    def _inline_text(children: Sequence[InlineElement]) -> str:
        parts: list[str] = []
        for c in children:
            if isinstance(c, TextRun):
                parts.append(c.text)
            elif isinstance(c, Formula):
                parts.append(c.latex)
        return "".join(parts)

    def extract_text_from_blocks(blocks: list[Block]) -> None:
        for block in blocks:
            if isinstance(block, Heading):
                texts.append(_inline_text(block.text.children))
            elif isinstance(block, IRParagraph):
                texts.append(_inline_text(block.children))
            elif isinstance(block, CodeBlock):
                texts.append(block.content)
            elif isinstance(block, Blockquote):
                extract_text_from_blocks(block.children)
            elif isinstance(block, (OrderedList, UnorderedList)):
                for item in block.items:
                    extract_text_from_blocks(item.blocks)

    extract_text_from_blocks(doc.blocks)
    full = "".join(texts)
    return full[:200].replace("\n", " ")


class BiliPublisher:
    """将 IR Document 发布到 B站 专栏草稿箱。"""

    def __init__(self, client: BiliClient, config: BiliPublishConfig) -> None:
        self.client = client
        self.config = config
        self._counter = 0

    async def _handle_cover(self, doc: Document) -> None:
        """处理封面图。

        优先级：
        1. config.image_urls 已设置（由外部提前上传）
        2. config.cover_path（CLI --cover 传入）
        3. doc.cover（由转换器从源文档提取）
        """
        if self.config.image_urls:
            return

        cover = self.config.cover_path or doc.cover
        if not cover:
            return

        cover = cover.resolve()
        if self._dry_run:
            logger.info(f"[dry-run] 跳过封面上传: {cover}")
        else:
            logger.info(f"上传封面图: {cover}")
            image_info = await self.client.upload_image(cover)
            self.config.image_urls = [image_info["url"]]
            logger.info(f"  → {image_info['url']}")

    async def publish(self, doc: Document, *, dry_run: bool = False) -> dict[str, Any]:
        """将 IR Document 发布到 B站 草稿箱。"""
        self._dry_run = dry_run
        config = self.config

        # 处理封面图
        await self._handle_cover(doc)

        logger.info("正在将 IR 转换为 B站 Opus 格式 ...")
        paragraphs = await self._convert_document(doc)
        logger.info(f"转换完成，共 {len(paragraphs)} 个段落")

        title = doc.title
        summary = _build_summary(doc)
        logger.info(f"标题: {title}")
        logger.info(f"摘要: {summary}")

        arg: ArgPayload = {
            "type": 4,
            "template_id": 1,
            "category_id": config.category_id,
            "title": title,
            "private_pub": config.private_pub,
            "reprint": config.reprint,
            "original": config.original,
            "list_id": config.list_id,
            "comment_selected": config.comment_selected,
            "up_closed_reply": config.up_closed_reply,
            "timer_pub_time": config.timer_pub_time,
            "only_fans_level": 0,
            "only_fans_dnd": 0,
            "summary": summary,
            "opus": {
                "opus_source": 2,
                "title": title,
                "content": {"paragraphs": paragraphs},
                "pub_info": {"editor_version": "eva3-3.0.0"},
                "attachments": {"is_aigc": config.is_aigc},
            },
        }
        if config.article_id is not None:
            arg["article_id"] = config.article_id
        if config.image_urls:
            arg["image_urls"] = config.image_urls
        if config.hashtag_ids:
            arg["hashtag_ids"] = config.hashtag_ids

        payload: Payload = {"arg": arg}

        logger.info("Payload: ")
        payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
        print(payload_json)

        if dry_run:
            return {}

        logger.info("正在保存到草稿箱 ...")
        result = await self.client.save_draft(payload)
        aid = result["data"]["article_id"]
        logger.info(f"✅ 成功！草稿 ID: {aid}")
        logger.info(
            f"可在创作中心查看: https://member.bilibili.com/platform/upload/text/new-edit?aid={aid}"
        )
        return result

    async def _convert_document(self, doc: Document) -> list[Paragraph]:
        """将 IR Document 的 blocks 转换为 B站 Opus paragraphs 列表。"""
        paragraphs: list[Paragraph] = []
        for block in doc.blocks:
            await self._convert_block(block, paragraphs)
        return paragraphs

    async def _convert_block(self, block: Block, paragraphs: list[Paragraph]) -> None:
        """将单个 IR Block 转换为零个或多个 B站 Opus paragraphs。"""
        if isinstance(block, Heading):
            nodes = self._convert_inline(list(block.text.children))
            if block.level <= 3:
                paragraphs.append(
                    make_heading_paragraph(nodes, block.level, align=block.text.align)
                )
            else:
                # H4~H9 回退为粗体文本段落（重建节点以避免突变原节点）
                styled_nodes: list[InlineNode] = []
                for node in nodes:
                    if isinstance(node, dict) and node.get("node_type") == 1:
                        word = node.get("word")
                        if isinstance(word, dict):
                            styled_nodes.append(
                                make_text_node(
                                    word.get("words", ""),
                                    bold=True,
                                    font_size=word.get("font_size", 17),
                                    font_level=word.get("font_level", "regular"),
                                    color=word.get("color", ""),
                                    dark_color=word.get("dark_color", ""),
                                )
                            )
                        else:
                            styled_nodes.append(node)
                    else:
                        styled_nodes.append(node)
                paragraphs.append(
                    make_text_paragraph(
                        styled_nodes,
                        align=block.text.align,
                        indent_level=block.text.indent_level,
                    )
                )

        elif isinstance(block, IRParagraph):
            nodes = self._convert_inline(block.children)
            if nodes:
                paragraphs.append(
                    make_text_paragraph(
                        nodes, align=block.align, indent_level=block.indent_level
                    )
                )

        elif isinstance(block, ImageBlock):
            await self._handle_image(block, paragraphs)

        elif isinstance(block, CodeBlock):
            paragraphs.append(make_code_paragraph(block.content, block.language))

        elif isinstance(block, Blockquote):
            await self._handle_blockquote(block, paragraphs)

        elif isinstance(block, OrderedList):
            self._handle_list(block, ordered=True, paragraphs=paragraphs)

        elif isinstance(block, UnorderedList):
            self._handle_list(block, ordered=False, paragraphs=paragraphs)

        elif isinstance(block, Divider):
            paragraphs.append(make_divider_paragraph())

    async def _handle_image(
        self, block: ImageBlock, paragraphs: list[Paragraph]
    ) -> None:
        """上传图片到 B站 图床并追加图片段落。"""
        img_path = Path(block.source)
        if not img_path.is_file():
            logger.warning(f"图片文件不存在，跳过: {img_path}")
            return

        if self._dry_run:
            logger.info(f"[dry-run] 跳过上传: {img_path}")
            return

        logger.info(f"正在上传图片: {img_path}")
        try:
            info = await self.client.upload_image(img_path)
            paragraphs.append(
                make_image_paragraph(
                    info["url"],
                    info["width"],
                    info["height"],
                    info.get("size", 0),
                    comment=block.caption or "",
                )
            )
            logger.info(f"  → 上传成功: {info['url']}")
        except Exception as e:
            logger.error(f"  [错误] 图片上传失败: {e}")

    async def _handle_blockquote(
        self, block: Blockquote, paragraphs: list[Paragraph]
    ) -> None:
        """将 IR Blockquote 转换为 B站 引用段落（共享 combine_hash）。"""
        if not block.children:
            return
        self._counter += 1
        combine_hash = f"bq_{int(time.time() * 1000000)}_{self._counter}"
        await self._emit_blockquote_children(block.children, combine_hash, paragraphs)

    async def _emit_blockquote_children(
        self, children: list[Block], combine_hash: str, paragraphs: list[Paragraph]
    ) -> None:
        """递归展平 Blockquote 子块（含嵌套 Blockquote 和 ImageBlock）。"""
        for child in children:
            if isinstance(child, Heading):
                nodes = self._convert_inline(list(child.text.children))
                paragraphs.append(make_blockquote_paragraph(nodes, combine_hash))
            elif isinstance(child, IRParagraph):
                nodes = self._convert_inline(list(child.children))
                if nodes:
                    paragraphs.append(make_blockquote_paragraph(nodes, combine_hash))
            elif isinstance(child, ImageBlock):
                await self._handle_image(child, paragraphs)
            elif isinstance(child, Blockquote):
                # 嵌套引用：递归展平，共享同一个 combine_hash
                await self._emit_blockquote_children(
                    child.children, combine_hash, paragraphs
                )

    def _handle_list(
        self,
        block: OrderedList | UnorderedList,
        ordered: bool,
        paragraphs: list[Paragraph],
    ) -> None:
        """将 IR 列表转换为 B站 列表段落（共享 combine_hash，递归处理嵌套）。"""
        if not block.items:
            return
        self._counter += 1
        combine_hash = f"list_{int(time.time() * 1000000)}_{self._counter}"
        self._emit_list_items(block.items, ordered, 1, combine_hash, paragraphs)

    def _emit_list_items(
        self,
        items: list[ListItem],
        ordered: bool,
        level: int,
        combine_hash: str,
        paragraphs: list[Paragraph],
    ) -> None:
        """递归将列表项展平为 B站 列表段落。"""
        if level > 3 or not items:
            return
        for order, item in enumerate(items, start=1):
            # 提取当前项文本
            nodes = self._extract_list_item_text(item)
            if nodes:
                if ordered:
                    paragraphs.append(
                        make_ordered_list_paragraph(nodes, level, order, combine_hash)
                    )
                else:
                    paragraphs.append(
                        make_unordered_list_paragraph(nodes, level, order, combine_hash)
                    )

            # 递归处理嵌套列表
            for child in item.blocks:
                if isinstance(child, OrderedList):
                    self._emit_list_items(
                        child.items, True, level + 1, combine_hash, paragraphs
                    )
                elif isinstance(child, UnorderedList):
                    self._emit_list_items(
                        child.items, False, level + 1, combine_hash, paragraphs
                    )

    def _extract_list_item_text(self, item: ListItem) -> list[InlineNode]:
        """从 ListItem 中提取文本节点（忽略嵌套列表）。"""
        nodes: list[InlineNode] = []
        for child in item.blocks:
            if isinstance(child, Heading):
                nodes.extend(self._convert_inline(list(child.text.children)))
            elif isinstance(child, IRParagraph):
                nodes.extend(self._convert_inline(list(child.children)))
            elif isinstance(child, (OrderedList, UnorderedList)):
                continue  # 嵌套列表由 _handle_list 内部处理
        return nodes

    def _convert_inline(self, children: Sequence[InlineElement]) -> list[InlineNode]:
        """将 IR InlineElement 列表转换为 B站 InlineNode 列表。"""
        nodes: list[InlineNode] = []
        for child in children:
            if isinstance(child, TextRun):
                nodes.append(self._textrun_to_node(child))
            elif isinstance(child, Formula):
                nodes.append(make_formula_node(child.latex))
        return self._merge_text_nodes(nodes)

    @staticmethod
    def _textrun_to_node(run: TextRun) -> InlineNode:
        """将 IR TextRun 转换为 B站 文本节点或链接节点。"""
        if run.link_url is not None:
            return make_link_node(show_text=run.text, url=run.link_url)
        color = run.color
        if run.inline_code and not color:
            color = "#c7254e"
        return make_text_node(
            run.text,
            bold=run.bold,
            italic=run.italic,
            underline=run.underline,
            strikethrough=run.strikethrough,
            color=color,
        )

    @staticmethod
    def _merge_text_nodes(nodes: list[InlineNode]) -> list[InlineNode]:
        """合并相邻的无样式普通文本节点（减少 payload 体积）。"""
        if not nodes:
            return nodes

        merged: list[InlineNode] = [nodes[0]]
        for node in nodes[1:]:
            last = merged[-1]
            if (
                isinstance(last, dict)
                and isinstance(node, dict)
                and last.get("node_type") == 1
                and node.get("node_type") == 1
            ):
                last_word = last.get("word", {})
                node_word = node.get("word", {})
                if (
                    not last_word.get("style")
                    and not node_word.get("style")
                    and last_word.get("font_level") == "regular"
                    and node_word.get("font_level") == "regular"
                    and not last_word.get("color")
                    and not node_word.get("color")
                    and "bg_style" not in last_word
                    and "bg_style" not in node_word
                ):
                    last_word["words"] = last_word.get("words", "") + node_word.get(
                        "words", ""
                    )
                else:
                    merged.append(node)
            else:
                merged.append(node)
        return merged
