"""
森空岛 Publisher — 将 IR Document 发布到森空岛文章草稿箱。

草稿存储于浏览器 localStorage，本模块生成完整的 Draft JSON
并输出浏览器控制台脚本，用户粘贴后即可在森空岛编辑器中加载。
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

if TYPE_CHECKING:
    from collections.abc import Sequence

    from article_publisher.platforms.skland.client import SklandClient


# =============================================================================
# 常量
# =============================================================================

_DEFAULT_OUTPUT = "skland_draft.json"
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

    def __init__(
        self, client: SklandClient, config: SklandPublishConfig | None = None
    ) -> None:
        self._client = client
        self._config = config or SklandPublishConfig()

    def publish(self, doc: Document, *, dry_run: bool = False) -> dict[str, Any]:
        """将 IR Document 转换为森空岛草稿 JSON，保存文件并输出控制台脚本。"""
        logger.info("正在将 IR 转换为森空岛草稿格式 ...")
        draft = self._convert_document(doc, dry_run=dry_run)
        logger.info(f"转换完成，共 {len(draft['document'])} 个文档元素")

        title = doc.title
        logger.info(f"标题: {title}")

        # 输出 Draft JSON
        output_path = Path(_DEFAULT_OUTPUT)
        logger.info(f"草稿 JSON 已保存到: {output_path.resolve()}")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(draft, f, ensure_ascii=False, indent=2)

        if dry_run:
            logger.info("[dry-run] 跳过草稿导入脚本输出")
            return {
                "platform": "skland",
                "status": "dry_run",
                "title": title,
                "draft_file": str(output_path.resolve()),
            }

        # 生成并输出控制台导入脚本
        return self._output_console_script(draft)

    # ==================================================================
    # IR → 森空岛 Draft JSON
    # ==================================================================

    def _convert_document(
        self, doc: Document, *, dry_run: bool = False
    ) -> dict[str, Any]:
        """将 IR Document 转换为森空岛 Draft JSON。"""
        elements: list[dict[str, Any]] = []

        for block in doc.blocks:
            self._convert_block(block, elements, dry_run=dry_run)

        # 封面图
        cover_id = ""
        if self._config.cover_path:
            cover_path = self._config.cover_path
            if cover_path.is_file():
                if dry_run:
                    logger.info(f"[dry-run] 跳过封面上传: {cover_path}")
                else:
                    logger.info(f"上传封面图: {cover_path}")
                    uploaded = self._client.upload_image(cover_path)
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

    def _convert_block(
        self, block: Block, elements: list[dict[str, Any]], *, dry_run: bool = False
    ) -> None:
        """将单个 IR Block 转换为一个或多个森空岛文档元素。"""
        if isinstance(block, Heading):
            children = self._convert_inline_to_skland(list(block.children))
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
                if block.align:
                    ele["alignment"] = block.align
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
            if block.align:
                ele["alignment"] = block.align
            elements.append(ele)

        elif isinstance(block, ImageBlock):
            self._handle_image_block(block, elements, dry_run=dry_run)

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
                    "kind": "0",
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

    def _handle_image_block(
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
            uploaded = self._client.upload_image(img_path)
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
            if isinstance(child, (Heading, IRParagraph)):
                inline = self._convert_inline_to_skland(
                    list(child.children) if isinstance(child.children, list) else []
                )
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
            if isinstance(child, (Heading, IRParagraph)):
                inline = self._convert_inline_to_skland(
                    list(child.children) if isinstance(child.children, list) else []
                )
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
            if isinstance(child, (Heading, IRParagraph)):
                inline = self._convert_inline_to_skland(
                    list(child.children) if isinstance(child.children, list) else []
                )
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
                if not text and not child.link_url:
                    continue

                # 超链接：只显示文本（森空岛 link 是块级元素，非 inline）
                if child.link_url:
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

    def _output_console_script(self, draft: dict[str, Any]) -> dict[str, Any]:
        """
        生成并输出浏览器控制台导入脚本。
        用户复制粘贴到森空岛编辑器页面控制台即可加载草稿。
        """
        try:
            user_id = self._client.get_user_id()
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
        logger.info(f"  草稿文件: {Path(_DEFAULT_OUTPUT).resolve()}")

        return {
            "platform": "skland",
            "status": "draft_ready",
            "title": draft["model"]["title"],
            "draft_id": draft_id,
            "draft_file": str(Path(_DEFAULT_OUTPUT).resolve()),
        }
