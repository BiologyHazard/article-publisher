"""
NGA Publisher — 将 IR Document 发布到 NGA 论坛。

工作流程：
1. 上传所有图片到 NGA 图床（使用与发帖相同的 session，确保 checksum 匹配）
2. 将 IR Document 转换为 NGA BBS 代码
3. 提交帖子到 post.php（自动处理附件绑定）
4. 同时保存 BBCode 到文件供检查
"""

from __future__ import annotations

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

if TYPE_CHECKING:
    from collections.abc import Sequence

    from article_publisher.platforms.nga.client import NgaClient, UploadedImage


_HEADING_SIZE: dict[int, str] = {1: "150%", 2: "130%", 3: "120%"}
"""NGA 标题字号映射，H1~H3 使用不同字号，H4+ 回退为纯粗体。"""

_INLINE_CODE_COLOR = "#c7254e"
"""NGA 行内代码颜色"""


@dataclass
class NgaPublishConfig:
    """NGA 发布配置参数。"""

    fid: str
    """目标版面 ID"""

    tid: str | None = None
    """已有帖子 ID（编辑模式时传入）"""

    pid: str | None = None
    """已有帖子内的回复 ID（编辑模式时传入）"""

    article: str | None = None
    """暂不清楚"""


# =============================================================================
# NGA Publisher
# =============================================================================


class NgaPublisher(Publisher):
    """将 IR Document 发布到 NGA 论坛。"""

    def __init__(self, client: NgaClient, config: NgaPublishConfig) -> None:
        self._client = client
        self._config = config
        self._is_modify = config.tid is not None
        # 上传后的图片缓存 (source_path → UploadedImage)
        self._uploaded_images: dict[str, UploadedImage] = {}

    async def publish(self, doc: Document, *, dry_run: bool = False) -> dict[str, Any]:
        """将 IR Document 转换为 NGA BBCode 并提交到 post.php。"""
        logger.info("正在将 IR 转换为 NGA BBCode ...")

        # 收集所有附件数据
        attachment_strings: list[str] = []
        attachment_checks: list[str] = []

        # GET /post.php 以获取 auth
        if not dry_run:
            await self._client.get_post_php(
                action="modify" if self._is_modify else "new",
                fid=self._config.fid,
                tid=self._config.tid,
                pid=self._config.pid,
                article=self._config.article,
            )

        bbcode = await self._convert_document(
            doc,
            dry_run=dry_run,
            attachment_strings=attachment_strings,
            attachment_checks=attachment_checks,
        )
        logger.info(f"转换完成，共 {len(bbcode)} 字符")

        title = doc.title
        logger.info(f"标题: {title}")

        logger.info("=" * 60)
        logger.info("  [dry-run] NGA BBS 代码预览：")
        logger.info("=" * 60)
        print(bbcode)
        logger.info("=" * 60)

        if dry_run:
            return {
                "platform": "nga",
                "status": "dry_run",
                "title": title,
                "bbcode_length": len(bbcode),
                "uploaded_images": len(self._uploaded_images),
            }

        if not attachment_strings:
            logger.warning("没有图片需要上传，直接提交文本内容。")

        # 编辑模式：先删除帖子中的旧附件（全量删除）
        if self._is_modify:
            await self._delete_old_attachments()

        # 提交帖子（与上传使用同一个 session，确保 checksum 匹配）
        logger.info(f"正在{'编辑' if self._is_modify else '提交'}帖子 ...")
        result = await self._client.submit_post(
            subject=title,
            content=bbcode,
            attachment_strings=attachment_strings,
            attachment_checks=attachment_checks,
            tid=self._config.tid,
        )

        if self._is_modify:
            logger.info(f"  -> 编辑成功！tid={self._config.tid}")
        else:
            logger.info("  -> 发布成功！")

        return {
            "platform": "nga",
            "status": "success",
            "title": title,
            "bbcode_length": len(bbcode),
            "uploaded_images": len(self._uploaded_images),
            "response": result,
            "tid": self._config.tid,
        }

    # ==================================================================
    # 编辑模式：旧附件清理
    # ==================================================================

    async def _delete_old_attachments(self) -> None:
        """删除帖子当前的所有旧附件（编辑帖子前调用）。"""
        tid = self._config.tid
        assert tid is not None  # 仅在编辑模式下调用

        logger.info("编辑模式：正在获取旧附件列表 ...")
        old_attachments = await self._client.get_recent_attachments(tid)

        if not old_attachments:
            logger.info("  → 没有旧附件需要删除。")
            return

        logger.info(f"  共 {len(old_attachments)} 个旧附件，正在逐个删除 ...")
        deleted = 0
        failed = 0
        for attach in old_attachments:
            aid = attach["name"]
            try:
                ok = await self._client.delete_attachment(tid, aid)
                if ok:
                    deleted += 1
                else:
                    failed += 1
            except Exception as e:
                logger.warning(f"  [错误] 删除附件失败 {aid}: {e}")
                failed += 1

        logger.info(f"  → 删除完成: {deleted} 成功, {failed} 失败")

    # ==================================================================
    # IR → NGA BBCode
    # ==================================================================

    async def _convert_document(
        self,
        doc: Document,
        *,
        dry_run: bool = False,
        attachment_strings: list[str] | None = None,
        attachment_checks: list[str] | None = None,
    ) -> str:
        """将 IR Document 转换为 NGA BBS 代码字符串。"""
        parts: list[str] = []

        for block in doc.blocks:
            result = await self._convert_block(
                block,
                dry_run=dry_run,
                attachment_strings=attachment_strings,
                attachment_checks=attachment_checks,
            )
            if result is not None:
                parts.append(result)

        return "\n".join(parts)

    async def _convert_block(
        self,
        block: Block,
        *,
        dry_run: bool = False,
        attachment_strings: list[str] | None = None,
        attachment_checks: list[str] | None = None,
    ) -> str | None:
        """将单个 IR Block 转换为 NGA BBS 代码字符串。"""
        if isinstance(block, Heading):
            return self._convert_heading(block)
        elif isinstance(block, IRParagraph):
            return self._convert_paragraph(block)
        elif isinstance(block, ImageBlock):
            return await self._handle_image(
                block,
                dry_run=dry_run,
                attachment_strings=attachment_strings,
                attachment_checks=attachment_checks,
            )
        elif isinstance(block, CodeBlock):
            return self._convert_codeblock(block)
        elif isinstance(block, Blockquote):
            return await self._convert_blockquote(
                block,
                dry_run=dry_run,
                attachment_strings=attachment_strings,
                attachment_checks=attachment_checks,
            )
        elif isinstance(block, OrderedList):
            return await self._convert_list(
                block,
                ordered=True,
                dry_run=dry_run,
                attachment_strings=attachment_strings,
                attachment_checks=attachment_checks,
            )
        elif isinstance(block, UnorderedList):
            return await self._convert_list(
                block,
                ordered=False,
                dry_run=dry_run,
                attachment_strings=attachment_strings,
                attachment_checks=attachment_checks,
            )
        elif isinstance(block, Divider):
            return "[h][/h]"
        return None

    # ==================================================================
    # Heading
    # ==================================================================

    def _convert_heading(self, block: Heading) -> str:
        """将标题转换为 NGA BBCode。

        NGA 无独立标题标签，用 [size]+[b] 模拟。
        H1~H3 使用不同字号，H4+ 回退为纯粗体。
        """
        inline = self._convert_inline(list(block.text.children))
        if block.level <= 3:
            size = _HEADING_SIZE.get(block.level, "120%")
            return f"[size={size}][b]{inline}[/b][/size]"
        else:
            return f"[b]{inline}[/b]"

    # ==================================================================
    # Paragraph
    # ==================================================================

    def _convert_paragraph(self, block: IRParagraph) -> str:
        """将普通段落转换为 NGA BBCode。"""
        inline = self._convert_inline(list(block.children))
        if not inline:
            return ""

        text = inline
        if block.align is Alignment.CENTER:
            text = f"[align=center]{text}[/align]"
        elif block.align is Alignment.RIGHT:
            text = f"[align=right]{text}[/align]"
        return text

    # ==================================================================
    # 内联元素
    # ==================================================================

    def _convert_inline(self, children: Sequence[InlineElement]) -> str:
        """将 IR InlineElement 列表转换为 NGA BBCode 字符串。"""
        parts: list[str] = []
        for child in children:
            if isinstance(child, TextRun):
                parts.append(self._textrun_to_bbcode(child))
        return "".join(parts)

    def _textrun_to_bbcode(self, run: TextRun) -> str:
        """将 IR TextRun 转换为 NGA BBCode 字符串。"""
        text = run.text

        if run.link_url is not None:
            return f"[url={run.link_url}]{text}[/url]"

        # 应用样式（从外到内，因为 BBCode 解析是从外到内的）
        if run.strikethrough:
            text = f"[del]{text}[/del]"
        if run.underline:
            text = f"[u]{text}[/u]"
        if run.italic:
            text = f"[i]{text}[/i]"
        if run.bold:
            text = f"[b]{text}[/b]"

        # 颜色（包括行内代码的特殊颜色）
        color = _INLINE_CODE_COLOR if run.inline_code else run.color
        if color:
            text = f"[color={color}]{text}[/color]"

        return text

    # ==================================================================
    # 图片处理
    # ==================================================================

    async def _handle_image(
        self,
        block: ImageBlock,
        *,
        dry_run: bool = False,
        attachment_strings: list[str] | None = None,
        attachment_checks: list[str] | None = None,
    ) -> str:
        """上传图片到 NGA 图床并生成 [img] BBCode。

        同时收集 attachment_str 和 attachment_check 以便后续生成控制台脚本。
        """
        img_path = Path(block.source)
        if not img_path.is_file():
            logger.warning(f"图片文件不存在，跳过: {img_path}")
            return f"  [图片缺失: {block.alt_text or img_path.name}]"

        # 检查是否已上传
        if img_path.name in self._uploaded_images:
            return self._uploaded_images[img_path.name].bbcode

        caption = block.caption or ""

        if dry_run:
            logger.info(f"[dry-run] 跳过上传: {img_path.name}")
            return f"  [图片: {img_path.name}]"

        logger.info(f"正在上传图片: {img_path.name}")
        try:
            uploaded = await self._client.upload_image(img_path)
            self._uploaded_images[img_path.name] = uploaded
            logger.info("  → 上传成功")

            # 收集附件数据
            if attachment_strings is not None:
                attachment_strings.append(uploaded.attachment_str)
            if attachment_checks is not None:
                attachment_checks.append(uploaded.attachment_check)

            bbcode = uploaded.bbcode
            if caption:
                bbcode = f"{bbcode}\n{caption}"
            return bbcode
        except Exception as e:
            logger.error(f"  [错误] 图片上传失败: {e}")
            return f"  [图片上传失败: {img_path.name}]"

    # ==================================================================
    # 代码块
    # ==================================================================

    def _convert_codeblock(self, block: CodeBlock) -> str:
        """将代码块转换为 [code] BBCode。"""
        content = block.content.rstrip("\n")
        return f"[code]\n{content}\n[/code]"

    # ==================================================================
    # 引用块
    # ==================================================================

    async def _convert_blockquote(
        self,
        block: Blockquote,
        *,
        dry_run: bool = False,
        attachment_strings: list[str] | None = None,
        attachment_checks: list[str] | None = None,
    ) -> str:
        """将引用块转换为 [quote] BBCode（支持嵌套）。"""
        children_bbcode: list[str] = []
        for child in block.children:
            result = await self._convert_block(
                child,
                dry_run=dry_run,
                attachment_strings=attachment_strings,
                attachment_checks=attachment_checks,
            )
            if result is not None:
                children_bbcode.append(result)

        if not children_bbcode:
            return ""

        inner = "\n".join(children_bbcode)
        return f"[quote]\n{inner}\n[/quote]"

    # ==================================================================
    # 列表
    # ==================================================================

    async def _convert_list(
        self,
        block: OrderedList | UnorderedList,
        *,
        ordered: bool,
        dry_run: bool = False,
        attachment_strings: list[str] | None = None,
        attachment_checks: list[str] | None = None,
    ) -> str:
        """将列表转换为 [list] BBCode（支持嵌套）。"""
        items: list[str] = []
        for item in block.items:
            item_bbcode = await self._convert_list_item(
                item,
                dry_run=dry_run,
                attachment_strings=attachment_strings,
                attachment_checks=attachment_checks,
            )
            if item_bbcode:
                items.append(item_bbcode)

        if not items:
            return ""

        inner = "\n".join(items)

        if ordered:
            return f"[list=1]\n{inner}\n[/list]"
        else:
            return f"[list]\n{inner}\n[/list]"

    async def _convert_list_item(
        self,
        item: ListItem,
        *,
        dry_run: bool = False,
        attachment_strings: list[str] | None = None,
        attachment_checks: list[str] | None = None,
    ) -> str:
        """将列表项转换为 [*] 条目，递归处理嵌套列表。"""
        parts: list[str] = []

        for child in item.blocks:
            if isinstance(child, IRParagraph):
                inline = self._convert_inline(child.children)
                if inline:
                    parts.append(inline)
            elif isinstance(child, Heading):
                inline = self._convert_inline(list(child.text.children))
                if inline:
                    parts.append(inline)
            elif isinstance(child, OrderedList):
                nested = await self._convert_list(
                    child,
                    ordered=True,
                    dry_run=dry_run,
                    attachment_strings=attachment_strings,
                    attachment_checks=attachment_checks,
                )
                if nested:
                    parts.append(nested)
            elif isinstance(child, UnorderedList):
                nested = await self._convert_list(
                    child,
                    ordered=False,
                    dry_run=dry_run,
                    attachment_strings=attachment_strings,
                    attachment_checks=attachment_checks,
                )
                if nested:
                    parts.append(nested)
            elif isinstance(child, ImageBlock):
                result = await self._handle_image(
                    child,
                    dry_run=dry_run,
                    attachment_strings=attachment_strings,
                    attachment_checks=attachment_checks,
                )
                if result:
                    parts.append(result)

        if not parts:
            return "[*]"

        return f"[*]{' '.join(parts)}"
