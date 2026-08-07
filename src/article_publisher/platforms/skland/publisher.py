"""
森空岛 Publisher — 将 IR Document 发布到森空岛文章草稿箱。

草稿存储于浏览器 localStorage，本模块生成完整的 Draft JSON
并输出浏览器控制台脚本，用户粘贴后即可在森空岛编辑器中加载。

编辑模式：通过 `--item-id` 参数编辑已发布的文章，
使用 API `/web/v2/item/upd` 直接更新文章内容。
"""

from __future__ import annotations

import json
import random
import string
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from article_publisher.document import (
    Alignment,
    Block,
    Blockquote,
    CodeBlock,
    Divider,
    Document,
    Heading,
    ImageBlock,
    InlineElement,
    ListItem,
    OrderedList,
    TextRun,
    UnorderedList,
)
from article_publisher.document import Paragraph as IRParagraph
from article_publisher.platforms.base import Publisher

# 森空岛 API 对齐值: 1=左对齐, 2=居中, 3=右对齐
_ALIGN_TO_SKLAND: dict[Alignment, int] = {
    Alignment.LEFT: 1,
    Alignment.CENTER: 2,
    Alignment.RIGHT: 3,
}

if TYPE_CHECKING:
    from collections.abc import Sequence

    from article_publisher.platforms.skland.client import SklandClient


# =============================================================================
# 常量
# =============================================================================

_ELEMENT_ID_CHARS = string.ascii_letters + string.digits


# =============================================================================
# 发布配置
# =============================================================================


@dataclass
class SklandPublishConfig:
    """森空岛发布配置参数。"""

    game_id: int = 1
    """游戏分区，默认 1 = 明日方舟"""

    cate_id: int = 4
    """子分区，默认 4 = 攻略"""

    cover_path: Path | None = None
    """可选封面图路径"""

    publish_time: str | None = None
    """定时发布时间戳（字符串形式）"""

    item_id: str | None = None
    """已发布文章 ID（编辑模式时传入）"""


# =============================================================================
# 生成 elementId
# =============================================================================


def _generate_element_id() -> str:
    """生成随机的 elementId，风格与前端一致（12 位字母数字）。"""
    return "".join(random.choices(_ELEMENT_ID_CHARS, k=12))


# =============================================================================
# 森空岛 Publisher
# =============================================================================


class SklandPublisher(Publisher):
    """将 IR Document 发布到森空岛草稿箱。"""

    def __init__(self, client: SklandClient, config: SklandPublishConfig) -> None:
        self._client = client
        self._config = config

    async def publish(self, doc: Document, *, dry_run: bool = False) -> dict[str, Any]:
        """将 IR Document 发布到森空岛（草稿箱或编辑已发布文章）。"""
        config = self._config
        is_edit = config.item_id is not None

        if is_edit:
            logger.info(f"编辑模式: item_id={config.item_id}")
            return await self._publish_edit(doc, dry_run=dry_run)

        # ---- 草稿模式 ----
        logger.info("正在将 IR 转换为森空岛草稿格式 ...")
        draft = await self._convert_document(doc, dry_run=dry_run)
        logger.info(f"转换完成，共 {len(draft['document'])} 个文档元素")

        title = doc.title
        logger.info(f"标题: {title}")

        if dry_run:
            logger.info("[dry-run] 跳过草稿导入脚本输出")
            return {"platform": "skland", "status": "dry_run", "title": title}

        # 生成并输出控制台导入脚本
        return await self._output_console_script(draft)

    # ==================================================================
    # IR → 森空岛 Draft JSON
    # ==================================================================

    async def _convert_document(
        self, doc: Document, *, dry_run: bool = False
    ) -> dict[str, Any]:
        """将 IR Document 转换为森空岛 Draft JSON。"""
        elements: list[dict[str, Any]] = []

        for block in doc.blocks:
            await self._convert_block(block, elements, dry_run=dry_run)

        # 封面图
        cover_id = ""
        if self._config.cover_path:
            cover_path = self._config.cover_path
            if cover_path.is_file():
                if dry_run:
                    logger.info(f"[dry-run] 跳过封面上传: {cover_path}")
                else:
                    logger.info(f"上传封面图: {cover_path}")
                    uploaded = await self._client.upload_image(cover_path)
                    cover_id = uploaded.image_id
            else:
                logger.warning(f"封面文件不存在，忽略: {cover_path}")

        # 构建 model
        model: dict[str, Any] = {
            "viewKind": 3,
            "origin": 1,
            "isAIGCStatementOn": False,
            "downloadEnable": 1,
            "title": doc.title,
            "tags": [],
            "imageCoverIndex": cover_id,
            "imageList": [],
            "gameId": self._config.game_id,
            "cateId": self._config.cate_id,
        }

        if self._config.publish_time:
            model["prePublishOn"] = True
            model["publishedAtTs"] = self._config.publish_time

        return {"version": 2, "model": model, "document": elements}

    async def _convert_block(
        self, block: Block, elements: list[dict[str, Any]], *, dry_run: bool = False
    ) -> None:
        """将单个 IR Block 转换为一个或多个森空岛文档元素。"""
        if isinstance(block, Heading):
            children = self._convert_inline_to_skland(list(block.text.children))
            if block.level <= 3:
                elements.append(
                    {
                        "elementId": _generate_element_id(),
                        "type": "header",
                        "level": block.level,
                        "children": children,
                    }
                )
            else:
                # H4+ 回退为粗体段落
                bold_children = (
                    [{**c, "bold": True} for c in children]
                    if children
                    else [{"text": ""}]
                )
                ele: dict[str, Any] = {
                    "elementId": _generate_element_id(),
                    "type": "paragraph",
                    "children": bold_children,
                }
                if block.text.align is not Alignment.LEFT:
                    ele["alignment"] = _ALIGN_TO_SKLAND[block.text.align]
                elements.append(ele)

        elif isinstance(block, IRParagraph):
            children = self._convert_inline_to_skland(list(block.children))
            if not children:
                children = [{"text": ""}]
            ele: dict[str, Any] = {
                "elementId": _generate_element_id(),
                "type": "paragraph",
                "children": children,
            }
            if block.align is not Alignment.LEFT:
                ele["alignment"] = _ALIGN_TO_SKLAND[block.align]
            elements.append(ele)

        elif isinstance(block, ImageBlock):
            await self._handle_image_block(block, elements, dry_run=dry_run)

        elif isinstance(block, CodeBlock):
            self._handle_code_block(block, elements)

        elif isinstance(block, Blockquote):
            self._handle_blockquote(block, elements)

        elif isinstance(block, OrderedList):
            elements.append(self._build_list_element(block, ordered=True))

        elif isinstance(block, UnorderedList):
            elements.append(self._build_list_element(block, ordered=False))

        elif isinstance(block, Divider):
            elements.append(
                {
                    "elementId": _generate_element_id(),
                    "type": "dividing-line",
                    "kind": "4",
                    "children": [{"text": ""}],
                }
            )

    # ==================================================================
    # 代码块（回退）
    # ==================================================================

    @staticmethod
    def _handle_code_block(block: CodeBlock, elements: list[dict[str, Any]]) -> None:
        """森空岛无独立代码块，回退为带标记的普通段落。"""
        lines = block.content.split("\n")
        for i, line in enumerate(lines):
            prefix = f"```{block.language}" if i == 0 else ""
            text = f"{prefix}{line}" if prefix else line
            elements.append(
                {
                    "elementId": _generate_element_id(),
                    "type": "paragraph",
                    "children": [{"text": text}],
                }
            )

    # ==================================================================
    # 图片处理
    # ==================================================================

    async def _handle_image_block(
        self,
        block: ImageBlock,
        elements: list[dict[str, Any]],
        *,
        dry_run: bool = False,
    ) -> None:
        """上传图片并构建 image-wrapper 元素。"""
        img_path = Path(block.source)
        if not img_path.is_file():
            logger.warning(f"图片文件不存在，跳过: {img_path}")
            return

        if dry_run:
            logger.info(f"[dry-run] 跳过上传: {img_path}")
            return

        logger.info(f"正在上传图片: {img_path}")
        try:
            uploaded = await self._client.upload_image(img_path)
            elements.append(self._build_image_wrapper(uploaded, block.caption))
            logger.info(f"  → 上传成功: {uploaded.url}")
        except Exception as e:
            logger.error(f"  [错误] 图片上传失败: {e}")

    @staticmethod
    def _build_image_wrapper(uploaded: Any, caption: str | None) -> dict[str, Any]:
        """构建森空岛 image-wrapper 元素。"""
        return {
            "elementId": _generate_element_id(),
            "type": "image-wrapper",
            "children": [
                {
                    "file": {},
                    "elementId": _generate_element_id(),
                    "type": "image",
                    "children": [{"text": ""}],
                    "image": {
                        "width": uploaded.width,
                        "height": uploaded.height,
                        "url": uploaded.url,
                        "size": uploaded.size,
                        "format": "",
                        "id": uploaded.image_id,
                    },
                },
                {
                    "elementId": _generate_element_id(),
                    "type": "image-brief",
                    "children": [{"text": caption or ""}],
                },
            ],
        }

    # ==================================================================
    # 引用块处理
    # ==================================================================

    def _handle_blockquote(
        self, block: Blockquote, elements: list[dict[str, Any]]
    ) -> None:
        """将 IR Blockquote 转换为森空岛 quote 元素。"""
        if not block.children:
            return

        quote_children: list[dict[str, Any]] = []
        for child in block.children:
            if isinstance(child, IRParagraph):
                inline = self._convert_inline_to_skland(child.children)
                quote_children.append(
                    {
                        "elementId": _generate_element_id(),
                        "type": "paragraph",
                        "children": inline or [{"text": ""}],
                    }
                )
            elif isinstance(child, Heading):
                inline = self._convert_inline_to_skland(list(child.text.children))
                quote_children.append(
                    {
                        "elementId": _generate_element_id(),
                        "type": "paragraph",
                        "children": inline or [{"text": ""}],
                    }
                )
            elif isinstance(child, Blockquote):
                # 森空岛 quote 不支持嵌套，展平为外层 quote 的 paragraph
                self._flatten_blockquote(child, quote_children)
            elif isinstance(child, ImageBlock):
                quote_children.append(
                    {
                        "elementId": _generate_element_id(),
                        "type": "paragraph",
                        "children": [
                            {"text": f"  [图片: {child.alt_text or child.source}]"}
                        ],
                    }
                )

        if quote_children:
            elements.append(
                {
                    "elementId": _generate_element_id(),
                    "type": "quote",
                    "children": quote_children,
                }
            )

    def _flatten_blockquote(
        self, block: Blockquote, target: list[dict[str, Any]]
    ) -> None:
        """递归展平嵌套的 Blockquote。"""
        for child in block.children:
            if isinstance(child, IRParagraph):
                inline = self._convert_inline_to_skland(child.children)
                target.append(
                    {
                        "elementId": _generate_element_id(),
                        "type": "paragraph",
                        "children": inline or [{"text": ""}],
                    }
                )
            elif isinstance(child, Heading):
                inline = self._convert_inline_to_skland(list(child.text.children))
                target.append(
                    {
                        "elementId": _generate_element_id(),
                        "type": "paragraph",
                        "children": inline or [{"text": ""}],
                    }
                )
            elif isinstance(child, Blockquote):
                self._flatten_blockquote(child, target)

    # ==================================================================
    # 列表处理
    # ==================================================================

    def _build_list_element(
        self, block: OrderedList | UnorderedList, *, ordered: bool
    ) -> dict[str, Any]:
        """将 IR 列表转换为森空岛列表元素（递归构建）。"""
        list_type = "ordered-list" if ordered else "unordered-list"
        items: list[dict[str, Any]] = []

        for item in block.items:
            items.append(self._build_list_item(item))

        return {
            "elementId": _generate_element_id(),
            "type": list_type,
            "children": items,
        }

    def _build_list_item(self, item: ListItem) -> dict[str, Any]:
        """将 IR ListItem 转换为森空岛 list-item 元素。"""
        children: list[dict[str, Any]] = []

        for child in item.blocks:
            if isinstance(child, IRParagraph):
                inline = self._convert_inline_to_skland(child.children)
                children.append(
                    {
                        "elementId": _generate_element_id(),
                        "type": "list-item-text",
                        "alignment": 1,
                        "children": inline or [{"text": ""}],
                    }
                )
            elif isinstance(child, Heading):
                inline = self._convert_inline_to_skland(list(child.text.children))
                children.append(
                    {
                        "elementId": _generate_element_id(),
                        "type": "list-item-text",
                        "alignment": 1,
                        "children": inline or [{"text": ""}],
                    }
                )
            elif isinstance(child, OrderedList):
                children.append(self._build_list_element(child, ordered=True))
            elif isinstance(child, UnorderedList):
                children.append(self._build_list_element(child, ordered=False))

        return {
            "elementId": _generate_element_id(),
            "type": "list-item",
            "children": children,
        }

    # ==================================================================
    # 内联元素转换
    # ==================================================================

    @staticmethod
    def _convert_inline_to_skland(
        children: Sequence[InlineElement],
    ) -> list[dict[str, Any]]:
        """将 IR InlineElement 列表转换为森空岛 InlineText 列表。"""
        result: list[dict[str, Any]] = []

        for child in children:
            if isinstance(child, TextRun):
                text = child.text
                if not text and child.link_url is None:
                    continue

                # 超链接：只显示文本（森空岛 link 是块级元素，非 inline）
                if child.link_url is not None:
                    result.append({"text": text})
                    continue

                node: dict[str, Any] = {"text": text}

                if child.bold:
                    node["bold"] = True
                if child.italic:
                    node["italic"] = True
                if child.underline:
                    node["underline"] = True
                if child.strikethrough:
                    node["del"] = True
                if child.color:
                    node["color"] = child.color

                result.append(node)

        # 合并相邻的纯文本节点
        return SklandPublisher._merge_text_nodes(result)

    @staticmethod
    def _merge_text_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """合并相邻的无样式纯文本节点。"""
        if not nodes:
            return nodes

        merged: list[dict[str, Any]] = [nodes[0]]
        for node in nodes[1:]:
            last = merged[-1]
            # 如果上一个和当前都是纯文本（只有 text 键），则合并
            if set(last.keys()) == {"text"} and set(node.keys()) == {"text"}:
                last["text"] += node["text"]
            else:
                merged.append(node)
        return merged

    # ==================================================================
    # 控制台脚本输出
    # ==================================================================

    async def _output_console_script(self, draft: dict[str, Any]) -> dict[str, Any]:
        """
        生成并输出浏览器控制台导入脚本。
        用户复制粘贴到森空岛编辑器页面控制台即可加载草稿。
        """
        try:
            user_id = await self._client.get_user_id()
        except Exception as e:
            logger.warning(f"获取用户 ID 失败: {e}")
            user_id = "USER_ID"

        draft_id = _generate_element_id()
        draft_json = json.dumps(draft, ensure_ascii=False)

        script = f"""// 森空岛草稿导入脚本
const userId = '{user_id}';
const draftId = '{draft_id}';
const data = {draft_json};

localStorage.setItem(`editor_draft_${{userId}}_${{draftId}}`, JSON.stringify(data));

const list = JSON.parse(localStorage.getItem(`editor_draft_list_${{userId}}`) || '[]');
list.unshift({{
    draftId: draftId,
    updateTime: Date.now(),
    title: data.model.title,
    cover: data.model.imageCoverIndex || '',
    viewKind: 3,
}});
localStorage.setItem(`editor_draft_list_${{userId}}`, JSON.stringify(list));

window.open(`https://www.skland.com/editor/article?draftId=${{draftId}}`, '_blank');"""

        logger.info("=" * 60)
        logger.info("  森空岛草稿已就绪！请在浏览器中执行以下步骤：")
        logger.info("=" * 60)
        logger.info("  1. 打开 https://www.skland.com/editor/article")
        logger.info("  2. 按 F12 打开开发者工具 → 控制台(Console)")
        logger.info("  3. 粘贴并执行以下 JavaScript：")
        logger.info("-" * 60)
        print(script)
        logger.info("-" * 60)
        logger.info(f"  草稿 ID: {draft_id}")

        return {
            "platform": "skland",
            "status": "draft_ready",
            "title": draft["model"]["title"],
            "draft_id": draft_id,
        }

    # ==================================================================
    # 编辑模式
    # ==================================================================

    async def _publish_edit(
        self, doc: Document, *, dry_run: bool = False
    ) -> dict[str, Any]:
        """编辑已发布的森空岛文章。"""
        config = self._config
        assert config.item_id is not None

        # 获取现有文章详情（tags、volumeId 等）
        if dry_run:
            logger.info("[dry-run] 跳过获取文章详情")
            detail: dict[str, Any] = {"item": {}, "tags": []}
        else:
            logger.info(f"获取文章详情: {config.item_id}")
            detail = await self._client.get_item_detail(config.item_id)
            logger.info(f"  标题: {detail['item'].get('title', '')}")

        existing_item = detail.get("item", {})
        existing_tags = detail.get("tags", [])

        # 上传封面图
        cover_image_id = existing_item.get("coverImageId", "")
        if config.cover_path:
            cover_path = config.cover_path
            if cover_path.is_file():
                if dry_run:
                    logger.info(f"[dry-run] 跳过封面上传: {cover_path}")
                else:
                    logger.info(f"上传封面图: {cover_path}")
                    uploaded = await self._client.upload_image(cover_path)
                    cover_image_id = uploaded.image_id
            else:
                logger.warning(f"封面文件不存在，忽略: {cover_path}")

        # 转换文档内容为森空岛 block 格式
        logger.info("正在将 IR 转换为森空岛 block 格式 ...")
        blocks = await self._convert_to_blocks(doc, dry_run=dry_run)
        logger.info(f"转换完成，共 {len(blocks)} 个 block")

        # 生成文档 ID（复用现有或生成新 ID）
        doc_id = existing_item.get("document", {}).get("id", _generate_element_id())

        # 构建 blockMap
        block_map: dict[str, dict[str, Any]] = {}
        block_ids: list[str] = []
        for block in blocks:
            bid = block["id"]
            block_ids.append(bid)
            block_map[bid] = block

        # 构建更新负载
        tag_ids = [t.get("id") for t in existing_tags if t.get("id")]

        update_payload: dict[str, Any] = {
            "id": config.item_id,
            "volumeId": existing_item.get("volumeId", ""),
            "title": doc.title,
            "gameId": config.game_id,
            "cateId": config.cate_id,
            "viewKind": existing_item.get("viewKind", 3),
            "origin": existing_item.get("origin", 1),
            "tags": existing_tags,
            "tagIds": tag_ids,
            "document": {
                "id": doc_id,
                "version": "1.0.0",
                "blockIds": block_ids,
                "blockMap": block_map,
            },
            "downloadEnable": existing_item.get("downloadEnable", 1),
            "coverImageId": cover_image_id,
            "cover": {"id": cover_image_id},
            "imageList": existing_item.get("imageList", []),
            "videoList": existing_item.get("videoList", []),
            "prePublishOn": existing_item.get("prePublishOn", False),
            "isAIGCStatementOn": existing_item.get("isAIGCStatementOn", False),
        }

        if config.publish_time:
            update_payload["prePublishOn"] = True
            update_payload["publishedAtTs"] = config.publish_time

        if dry_run:
            logger.info("=" * 60)
            logger.info("  [dry-run] 编辑 Payload 预览：")
            logger.info("=" * 60)
            print(json.dumps(update_payload, ensure_ascii=False, indent=2)[:3000])
            logger.info("=" * 60)
            return {
                "platform": "skland",
                "status": "dry_run",
                "title": doc.title,
                "item_id": config.item_id,
                "blocks": len(blocks),
            }

        logger.info("正在更新已发布文章 ...")
        result = await self._client.update_item(update_payload)
        logger.info(f"✅ 编辑成功！文章 ID: {config.item_id}")
        return {
            "platform": "skland",
            "status": "success",
            "title": doc.title,
            "item_id": config.item_id,
            "blocks": len(blocks),
            "response": result,
        }

    # ==================================================================
    # IR → 森空岛 Block 格式（用于编辑模式）
    # ==================================================================

    async def _convert_to_blocks(
        self, doc: Document, *, dry_run: bool = False
    ) -> list[dict[str, Any]]:
        """将 IR Document 转换为森空岛 block 列表（item/upd 格式）。"""
        blocks: list[dict[str, Any]] = []
        # 使用一个固定的 parentId（文档根 ID）
        parent_id = _generate_element_id()

        for block in doc.blocks:
            await self._convert_block_to_block(
                block, blocks, parent_id, dry_run=dry_run
            )

        return blocks

    async def _convert_block_to_block(
        self,
        block: Block,
        blocks: list[dict[str, Any]],
        parent_id: str,
        *,
        dry_run: bool = False,
    ) -> None:
        """将单个 IR Block 转换为森空岛 block。"""
        if isinstance(block, Heading):
            heading_map = {1: "heading1", 2: "heading2", 3: "heading3"}
            kind = heading_map.get(block.level, "heading3")
            inline = self._convert_inline_to_block_elements(list(block.text.children))
            blocks.append(
                {
                    "kind": "text",
                    "id": _generate_element_id(),
                    "parentId": parent_id,
                    "align": "left",
                    "text": {"inlineElements": inline, "kind": kind},
                }
            )

        elif isinstance(block, IRParagraph):
            inline = self._convert_inline_to_block_elements(list(block.children))
            blocks.append(
                {
                    "kind": "text",
                    "id": _generate_element_id(),
                    "parentId": parent_id,
                    "align": "left",
                    "text": {"inlineElements": inline, "kind": "body"},
                }
            )

        elif isinstance(block, ImageBlock):
            await self._handle_image_block_to_block(
                block, blocks, parent_id, dry_run=dry_run
            )

        elif isinstance(block, CodeBlock):
            # 代码块回退为文本段落
            lines = block.content.split("\n")
            for i, line in enumerate(lines):
                prefix = f"```{block.language}" if i == 0 else ""
                text = f"{prefix}{line}" if prefix else line
                blocks.append(
                    {
                        "kind": "text",
                        "id": _generate_element_id(),
                        "parentId": parent_id,
                        "align": "left",
                        "text": {
                            "inlineElements": [
                                {"kind": "text", "text": {"text": text}}
                            ],
                            "kind": "body",
                        },
                    }
                )

        elif isinstance(block, Blockquote):
            # 引用块回退为文本段落
            self._convert_blockquote_to_block(block, blocks, parent_id)

        elif isinstance(block, (OrderedList, UnorderedList)):
            # 列表回退为文本段落
            for item in block.items:
                self._convert_list_item_to_block(item, blocks, parent_id)

        elif isinstance(block, Divider):
            blocks.append(
                {
                    "kind": "horizontalLine",
                    "id": _generate_element_id(),
                    "parentId": parent_id,
                    "align": "left",
                    "horizontalLine": {"kind": "4"},
                }
            )

    def _convert_blockquote_to_block(
        self, block: Blockquote, blocks: list[dict[str, Any]], parent_id: str
    ) -> None:
        """将引用块转换为文本 blocks。"""
        for child in block.children:
            if isinstance(child, IRParagraph):
                inline = self._convert_inline_to_block_elements(list(child.children))
                blocks.append(
                    {
                        "kind": "text",
                        "id": _generate_element_id(),
                        "parentId": parent_id,
                        "align": "left",
                        "text": {"inlineElements": inline, "kind": "body"},
                    }
                )
            elif isinstance(child, Heading):
                heading_map = {1: "heading1", 2: "heading2", 3: "heading3"}
                kind = heading_map.get(child.level, "heading3")
                inline = self._convert_inline_to_block_elements(
                    list(child.text.children)
                )
                blocks.append(
                    {
                        "kind": "text",
                        "id": _generate_element_id(),
                        "parentId": parent_id,
                        "align": "left",
                        "text": {"inlineElements": inline, "kind": kind},
                    }
                )
            elif isinstance(child, ImageBlock):
                blocks.append(
                    {
                        "kind": "text",
                        "id": _generate_element_id(),
                        "parentId": parent_id,
                        "align": "left",
                        "text": {
                            "inlineElements": [
                                {
                                    "kind": "text",
                                    "text": {
                                        "text": f"[图片: {child.alt_text or child.source}]"
                                    },
                                }
                            ],
                            "kind": "body",
                        },
                    }
                )

    def _convert_list_item_to_block(
        self, item: "ListItem", blocks: list[dict[str, Any]], parent_id: str
    ) -> None:
        """将列表项转换为文本 block。"""
        for child in item.blocks:
            if isinstance(child, IRParagraph):
                inline = self._convert_inline_to_block_elements(list(child.children))
                if inline:
                    blocks.append(
                        {
                            "kind": "text",
                            "id": _generate_element_id(),
                            "parentId": parent_id,
                            "align": "left",
                            "text": {"inlineElements": inline, "kind": "body"},
                        }
                    )
            elif isinstance(child, Heading):
                heading_map = {1: "heading1", 2: "heading2", 3: "heading3"}
                kind = heading_map.get(child.level, "heading3")
                inline = self._convert_inline_to_block_elements(
                    list(child.text.children)
                )
                blocks.append(
                    {
                        "kind": "text",
                        "id": _generate_element_id(),
                        "parentId": parent_id,
                        "align": "left",
                        "text": {"inlineElements": inline, "kind": kind},
                    }
                )

    async def _handle_image_block_to_block(
        self,
        block: ImageBlock,
        blocks: list[dict[str, Any]],
        parent_id: str,
        *,
        dry_run: bool = False,
    ) -> None:
        """上传图片并构建 image block。"""
        img_path = Path(block.source)
        if not img_path.is_file():
            logger.warning(f"图片文件不存在，跳过: {img_path}")
            return

        if dry_run:
            blocks.append(
                {
                    "kind": "text",
                    "id": _generate_element_id(),
                    "parentId": parent_id,
                    "align": "left",
                    "text": {
                        "inlineElements": [
                            {
                                "kind": "text",
                                "text": {"text": f"[图片: {block.source}]"},
                            }
                        ],
                        "kind": "body",
                    },
                }
            )
            return

        logger.info(f"正在上传图片: {img_path}")
        try:
            uploaded = await self._client.upload_image(img_path)
            blocks.append(
                {
                    "kind": "image",
                    "id": _generate_element_id(),
                    "parentId": parent_id,
                    "align": "left",
                    "image": {
                        "id": uploaded.image_id,
                        "url": uploaded.url,
                        "width": uploaded.width,
                        "height": uploaded.height,
                        "format": "",
                        "size": uploaded.size,
                        "description": block.caption or "",
                        "isAIGC": False,
                    },
                }
            )
            logger.info(f"  → 上传成功: {uploaded.url}")
        except Exception as e:
            logger.error(f"  [错误] 图片上传失败: {e}")

    @staticmethod
    def _convert_inline_to_block_elements(
        children: Sequence["InlineElement"],
    ) -> list[dict[str, Any]]:
        """将 IR InlineElement 列表转换为森空岛 block inlineElements。"""
        elements: list[dict[str, Any]] = []
        for child in children:
            from article_publisher.document import TextRun

            if isinstance(child, TextRun):
                text = child.text
                if not text:
                    continue
                # 森空岛 block 格式暂不支持复杂的 inline 样式
                elements.append({"kind": "text", "text": {"text": text}})
        return elements
