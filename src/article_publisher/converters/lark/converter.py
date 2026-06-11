import shutil
import urllib.parse

from article_publisher.converters.base import Converter
from article_publisher.converters.lark.client import LarkClient
from article_publisher.converters.lark.consts import (
    ALIGN_KEY_MAP,
    CODE_LANG_MAP,
    LARK_TO_ALIGNMENT,
    TEMP_IMAGES_DIR,
    TEXT_COLOR_MAP,
)
from article_publisher.converters.lark.models import Block as LarkBlock
from article_publisher.converters.lark.models import Document as LarkDocument
from article_publisher.converters.lark.models import TextElement
from article_publisher.converters.lark.models import TextRun as LarkTextRun
from article_publisher.document import (
    Alignment,
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
    Paragraph,
    TextRun,
    UnorderedList,
)
from article_publisher.log import logger


class LarkDocxConverter(Converter):
    """将飞书云文档转换为 IR Document。"""

    def __init__(self, app_id: str, app_secret: str, document_id: str) -> None:
        self._document_id = document_id
        self._client = LarkClient(app_id, app_secret)
        self._blocks: dict[str, LarkBlock] = {}
        self._root_block_id: str = ""
        self._document: LarkDocument | None = None

    async def _get_document(self) -> LarkDocument:
        """获取飞书文档基本信息（标题、封面等），并缓存结果。"""

        if self._document is not None:
            return self._document

        data = await self._client.get_document(self._document_id)
        self._document = data["document"]
        return self._document

    async def get_title(self) -> str:
        """从飞书文档基本信息中提取标题。"""

        document = await self._get_document()
        return document["title"]

    async def convert(self) -> Document:
        """执行转换，返回 IR Document。"""

        await self._load_blocks()
        blocks: list[Block] = []
        await self._walk_block(self._root_block_id, blocks, depth=0)
        title = await self.get_title()
        cover_path = await self._download_cover()
        return Document(title=title, blocks=blocks, cover=cover_path)

    async def _download_cover(self) -> str | None:
        """下载飞书文档封面图片，返回本地路径；无封面时返回 None。"""
        document = await self._get_document()
        if "cover" not in document:
            return None

        cover_token = document["cover"]["token"]

        try:
            logger.info(f"正在下载封面图: token={cover_token}")
            image_data = await self._download_image(cover_token)
            TEMP_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            tmp_path = TEMP_IMAGES_DIR / f"cover_{cover_token}.png"
            tmp_path.write_bytes(image_data)
            logger.info(f"  → 封面下载完成: {tmp_path}")
            return str(tmp_path)
        except Exception as e:
            logger.warning(f"封面下载失败: {e}")
            return None

    # ------------------------------------------------------------------
    # 块数据加载
    # ------------------------------------------------------------------

    async def _load_blocks(self) -> None:
        """分页加载所有块，构建 block_id → block_dict 映射。"""
        items: list[LarkBlock] = []
        page_token = ""
        while True:
            params = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = await self._client.get_json(
                f"/docx/v1/documents/{self._document_id}/blocks", params=params
            )
            items.extend(data["data"]["items"])
            if not data["data"].get("has_more"):
                break
            page_token = data["data"]["page_token"]

        for block in items:
            bid = block["block_id"]
            self._blocks[bid] = block
            if block.get("parent_id") == "":
                self._root_block_id = bid
        if not self._root_block_id and items:
            self._root_block_id = items[0]["block_id"]

        logger.info(f"  已加载 {len(self._blocks)} 个块")

    # ------------------------------------------------------------------
    # 树遍历
    # ------------------------------------------------------------------

    async def _walk_block(
        self, block_id: str, blocks: list[Block], depth: int = 0, indent_level: int = 0
    ) -> None:
        """深度优先遍历单个块，然后处理其子块（含列表分组）。"""
        block = self._blocks.get(block_id)
        if block is None:
            return

        block_type = block["block_type"]
        prefix = "  " * depth
        children = block.get("children") or []

        # quote_container：子块需要被包裹为 Blockquote
        if block_type == 34:
            quote_children: list[Block] = []
            await self._walk_children(children, quote_children, depth + 1, indent_level)
            if quote_children:
                blocks.append(Blockquote(children=quote_children))
            return

        # 普通块：转换当前块
        ir_block = await self._convert_single(block_type, block, prefix, indent_level)
        if ir_block is not None:
            blocks.append(ir_block)

        # 计算子块的缩进级别：
        # 仅文本/标题/列表块（block_type 2~13）下嵌套的子块才递增缩进
        # 容器块（grid、callout 等）的子块保持相同的缩进级别
        if 2 <= block_type <= 13:
            child_indent = indent_level + 1
        else:
            child_indent = indent_level

        # 递归处理子块（自动分组连续列表项）
        await self._walk_children(children, blocks, depth + 1, child_indent)

    async def _walk_children(
        self,
        child_ids: list[str],
        blocks: list[Block],
        depth: int,
        indent_level: int = 0,
    ) -> None:
        """处理子块列表，连续的同类型列表项自动分组为 OrderedList / UnorderedList。"""
        i = 0
        while i < len(child_ids):
            child_id = child_ids[i]
            child = self._blocks.get(child_id)
            if child is None:
                i += 1
                continue

            bt = child["block_type"]

            if bt in (12, 13):
                group_ids = [child_id]
                i += 1
                while i < len(child_ids):
                    nc = self._blocks.get(child_ids[i])
                    # 只合并同类型列表项（bullet 和 ordered 各自独立）
                    if nc is None or nc["block_type"] != bt:
                        break
                    group_ids.append(child_ids[i])
                    i += 1

                is_ordered = bt == 13
                items: list[ListItem] = []
                for gid in group_ids:
                    item_blocks: list[Block] = []
                    gblock = self._blocks[gid]

                    # 提取列表项文本内容（bullet/ordered 字段中的 elements）
                    if is_ordered:
                        content = gblock.get("ordered", {})
                    else:
                        content = gblock.get("bullet", {})
                    elements = content.get("elements", [])
                    inline_elements = self._elements_to_inline(elements)
                    if inline_elements:
                        item_blocks.append(Paragraph(children=inline_elements))

                    # 递归处理子块（嵌套列表等）
                    await self._walk_children(
                        gblock.get("children", []), item_blocks, depth + 1, indent_level
                    )
                    items.append(ListItem(blocks=item_blocks))

                if is_ordered:
                    blocks.append(OrderedList(items=items))
                else:
                    blocks.append(UnorderedList(items=items))
            else:
                await self._walk_block(child_id, blocks, depth + 1, indent_level)
                i += 1

    # ------------------------------------------------------------------
    # 单块转换（block_type → IR Block | None）
    # ------------------------------------------------------------------

    async def _convert_single(
        self, block_type: int, block: LarkBlock, prefix: str, indent_level: int = 0
    ) -> Block | None:
        """将单个 Lark 块转换为 IR Block。"""
        if block_type == 1:  # page
            return None
        if block_type == 2:  # text
            return self._convert_text(block, indent_level)
        if 3 <= block_type <= 11:  # heading1~9
            return self._convert_heading(block, block_type, indent_level)
        if block_type == 14:  # code
            return self._convert_code(block)
        if block_type == 22:  # divider
            return Divider()
        if block_type == 27:  # image
            return await self._convert_image(block, prefix)
        if block_type in (19, 24, 25, 30, 31, 32):  # containers — flatten
            return None
        if block_type in (12, 13):  # lists — handled by _walk_children
            return None
        if block_type == 34:  # quote — handled by _walk_block
            return None

        logger.warning(f"{prefix}未支持的块类型 (block_type={block_type})，已跳过")
        return None

    def _convert_text(
        self, block: LarkBlock, indent_level: int = 0
    ) -> Paragraph | None:
        """处理文本块 (block_type=2)。"""
        text = block.get("text")
        if not text:
            return None
        children = self._elements_to_inline(text.get("elements", []))
        if not children:
            return None
        align = self._extract_align(block)
        return Paragraph(children=children, align=align, indent_level=indent_level)

    def _convert_heading(
        self, block: LarkBlock, block_type: int, indent_level: int = 0
    ) -> Heading:
        """处理标题块 (block_type=3~11 → heading1~heading9)。
        H4~H9 在 IR 中保留为 Heading，由 Publisher 回退为粗体文本。
        """
        heading_level = block_type - 2  # 3→1, ..., 11→9
        heading_key = f"heading{heading_level}"
        heading = block.get(heading_key)
        if not heading:
            return Heading(level=heading_level, children=[])

        children = self._elements_to_inline(heading.get("elements", []))
        align = self._extract_align(block)
        return Heading(
            level=heading_level,
            children=children,
            align=align,
            indent_level=indent_level,
        )

    def _convert_code(self, block: LarkBlock) -> CodeBlock | None:
        """处理代码块 (block_type=14)。"""
        code = block.get("code")
        if not code:
            return None
        content_parts: list[str] = []
        lang = ""
        for elem in code.get("elements", []):
            text_run = elem.get("text_run")
            if text_run and text_run.get("content"):
                content_parts.append(text_run["content"])
        content = "".join(content_parts)

        code_style = code.get("style") or {}
        lang_id = code_style.get("language")
        if lang_id is not None:
            lang = CODE_LANG_MAP.get(lang_id, "")

        if not content:
            return None
        return CodeBlock(language=lang, content=content)

    async def _convert_image(self, block: LarkBlock, prefix: str) -> ImageBlock | None:
        """处理图片 (block_type=27)：下载到项目内临时目录。"""
        image = block.get("image")
        if not image:
            return None
        token = image.get("token")
        if not token:
            return None

        caption = (image.get("caption") or {}).get("content", "")

        try:
            logger.info(f"{prefix}正在下载图片: token={token}")
            image_data = await self._download_image(token)
            # 存到项目内临时目录
            TEMP_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            tmp_path = TEMP_IMAGES_DIR / f"{token}.png"
            tmp_path.write_bytes(image_data)
            logger.info(f"{prefix}  → 下载完成: {tmp_path}")
            return ImageBlock(source=str(tmp_path), alt_text=None, caption=caption)
        except Exception as e:
            logger.error(f"{prefix}  [错误] 图片下载失败: {e}")
            return None

    # ------------------------------------------------------------------
    # 飞书 API 调用
    # ------------------------------------------------------------------

    async def _download_image(self, token: str) -> bytes:
        """调用飞书图片下载 API。"""
        return await self._client.get_bytes(f"/drive/v1/medias/{token}/download")

    # ------------------------------------------------------------------
    # 内联元素转换
    # ------------------------------------------------------------------

    def _elements_to_inline(self, elements: list[TextElement]) -> list[InlineElement]:
        """将飞书元素列表转换为 IR InlineElement 列表（TextRun / Formula）。"""
        result: list[InlineElement] = []
        for elem in elements:
            text_run = elem.get("text_run")
            equation = elem.get("equation")
            if text_run and text_run.get("content"):
                result.append(self._text_run_to_run(text_run))
            elif equation and equation.get("content"):
                result.append(Formula(latex=equation["content"]))
        return result

    def _text_run_to_run(self, text_run: LarkTextRun) -> TextRun:
        """将单个飞书 text_run 转换为 IR TextRun。"""
        content = text_run["content"]
        style = text_run.get("text_element_style") or {}

        bold = style.get("bold", False) is True
        italic = style.get("italic", False) is True
        underline = style.get("underline", False) is True
        strikethrough = style.get("strikethrough", False) is True
        inline_code = style.get("inline_code", False) is True

        color = ""
        if inline_code:
            color = "#c7254e"
        else:
            text_color = style.get("text_color")
            if text_color is not None:
                color = TEXT_COLOR_MAP.get(text_color, "")

        link_url = None
        link = style.get("link")
        if link and link.get("url"):
            link_url = urllib.parse.unquote(link["url"])

        return TextRun(
            text=content,
            bold=bold,
            italic=italic,
            underline=underline,
            strikethrough=strikethrough,
            inline_code=inline_code,
            color=color,
            link_url=link_url,
        )

    @staticmethod
    def _extract_align(block: LarkBlock) -> Alignment:
        """从 Lark block 的 style 中提取对齐方式。
        Lark: 1=左对齐, 2=居中, 3=右对齐
        """
        key = ALIGN_KEY_MAP.get(block.get("block_type", 0))
        if key is None:
            return Alignment.LEFT
        sub = block.get(key)
        if isinstance(sub, dict):
            s = sub.get("style") or {}
            lark_align = s.get("align", 1)
            return LARK_TO_ALIGNMENT.get(lark_align, Alignment.LEFT)
        return Alignment.LEFT

    @staticmethod
    def _elements_to_plain_text(elements: list[TextElement]) -> str:
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

    async def close(self) -> None:
        await self._client.close()


def cleanup_temp_images() -> None:
    """清理飞书转换器产生的临时图片目录。"""
    if TEMP_IMAGES_DIR.exists():
        shutil.rmtree(TEMP_IMAGES_DIR)
        logger.info(f"已清理临时图片: {TEMP_IMAGES_DIR}")
