"""
B站 Publisher — 将 IR Document 发布到 B站 Opus 专栏草稿箱。
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
lazy from collections.abc import Sequence

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
from article_publisher.platforms.bilibili._wbi import BILI_API_BASE
from article_publisher.platforms.bilibili.client import BiliApiError
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
lazy from article_publisher.platforms.bilibili.client import BiliClient
lazy from article_publisher.platforms.bilibili.models import (
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
    """草稿 ID（更新已有草稿时传入）"""
    edit_article_id: int | None = None
    """已发布文章 ID（编辑已发布文章时传入）"""
    edit_dyn_id_str: str | None = None
    """已发布文章的动态 ID（编辑时可选，内部自动获取）"""
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

    async def _get_article_detail(self, article_id: int) -> dict[str, Any]:
        """获取已发布文章的详情（用于编辑模式）。"""
        from urllib.parse import urlencode

        url = f"{BILI_API_BASE}/x/article/creative/article/view"
        params = await self.client.sign({"id": article_id, "csrf": self.client.csrf})
        query = urlencode(params)
        resp = await self.client.request("GET", f"{url}?{query}")
        result = await resp.json()
        if result.get("code") != 0:
            raise BiliApiError(
                result.get("code", -1),
                result.get("message", "获取文章详情失败"),
                result,
            )
        return result["data"]

    async def publish(self, doc: Document, *, dry_run: bool = False) -> dict[str, Any]:
        """将 IR Document 发布到 B站 草稿箱或编辑已发布文章。"""
        self._dry_run = dry_run
        config = self.config
        is_edit = config.edit_article_id is not None

        if is_edit:
            logger.info(f"编辑模式: article_id={config.edit_article_id}")

            if dry_run:
                dyn_id_str = "DRY_RUN_DYN_ID"
                mid = "0"
            else:
                # 获取文章详情以获取 dyn_id_str
                article_detail = await self._get_article_detail(config.edit_article_id)
                dyn_id_str = article_detail.get("dyn_id_str", "")
                logger.info(f"  动态 ID: {dyn_id_str}")

                # 获取用户 mid 用于生成 upload_id
                nav_resp = await self.client.request(
                    "GET", f"{BILI_API_BASE}/x/web-interface/nav"
                )
                nav_data = await nav_resp.json()
                mid = nav_data.get("data", {}).get("mid", "0")

        # 处理封面图
        await self._handle_cover(doc)

        logger.info("正在将 IR 转换为 B站 Opus 格式 ...")
        paragraphs = await self._convert_document(doc)
        logger.info(f"转换完成，共 {len(paragraphs)} 个段落")

        title = doc.title
        summary = _build_summary(doc)
        logger.info(f"标题: {title}")
        logger.info(f"摘要: {summary}")

        if is_edit:
            # ---- 编辑已发布文章 ----
            timestamp = int(time.time() * 1000)
            upload_id = f"{mid}_{timestamp}_{timestamp % 10000}"

            # 构建 opus 内容体（与草稿格式一致）
            opus_body: dict[str, Any] = {
                "opus_source": 2,
                "title": title,
                "content": {"paragraphs": paragraphs},
                "pub_info": {"editor_version": "eva3-4.0.0"},
                "article": {
                    "category_id": config.category_id,
                    "list_id": config.list_id,
                    "originality": config.original,
                    "reproduced": 2 if config.reprint == 1 else 1,
                    "cover": (
                        [{"url": url} for url in (config.image_urls or [])]
                        if config.image_urls
                        else []
                    ),
                },
            }

            # 处理话题
            topic = None
            if config.hashtag_ids:
                # 简化处理：默认使用第一个话题
                topic = {"id": config.hashtag_ids[0], "name": ""}

            logger.info("正在编辑已发布文章 ...")
            result = await self.client.edit_opus(
                dyn_id_str=dyn_id_str,
                upload_id=upload_id,
                opus=opus_body,
                option={
                    "aigc": config.is_aigc,
                    "close_comment": config.up_closed_reply,
                    "up_choose_comment": config.comment_selected,
                },
                topic=topic,
            )
            dyn_id = result["data"]["dyn_id_str"]
            logger.info(f"✅ 编辑成功！动态 ID: {dyn_id}")
            return result
        else:
            # ---- 保存到草稿箱 ----
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
