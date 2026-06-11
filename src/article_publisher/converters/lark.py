from __future__ import annotations

import shutil
import urllib.parse
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import aiohttp


from article_publisher.converters.base import Converter
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
from article_publisher.http_client import ClientSessionWithLog
from article_publisher.log import ROOT_DIR as _PROJECT_ROOT
from article_publisher.log import logger

# 临时图片目录（项目根目录内，用完清除）
_TEMP_IMAGES_DIR = _PROJECT_ROOT / "temp" / "lark_images"

# =============================================================================
# 常量
# =============================================================================

LARK_API_BASE = "https://open.feishu.cn/open-apis"

# 飞书文字颜色索引 → 十六进制颜色
_TEXT_COLOR_MAP: dict[int, str] = {
    1: "#c9272c",  # 红色
    2: "#fba518",  # 橙色
    3: "#f9d71c",  # 黄色
    4: "#3cb034",  # 绿色
    5: "#3598cd",  # 蓝色
    6: "#8e5bb5",  # 紫色
    7: "#7a7a7a",  # 灰色
    8: "#6bc3b2",  # 青色
    9: "#15848c",  # 深青
    10: "#1f8c9a",  # 靛蓝
    11: "#347ab3",  # 深蓝
    12: "#af6ba5",  # 粉紫
}
_BG_COLOR_MAP: dict[int, str] = {
    1: "#fdf2f2",  # 浅红
    2: "#fef6e8",  # 浅橙
    3: "#fef9da",  # 浅黄
    4: "#eaf7e6",  # 浅绿
    5: "#e7f1f7",  # 浅蓝
    6: "#f3edf7",  # 浅紫
    7: "#f0f0f0",  # 浅灰
    8: "#ffd9e4",  # 红色背景
    9: "#e5ffeb",  # 浅薄荷
}
# 代码语言 ID → 名称
_CODE_LANG_MAP: dict[int, str] = {
    0: "PlainText",
    1: "ABAP",
    2: "Ada",
    3: "Apache",
    4: "Apex",
    5: "Assembly",
    6: "Bash",
    7: "CSharp",
    8: "C++",
    9: "C",
    10: "COBOL",
    11: "CSS",
    12: "CoffeeScript",
    13: "D",
    14: "Dart",
    15: "Delphi",
    16: "Django",
    17: "Dockerfile",
    18: "Erlang",
    19: "Fortran",
    20: "FoxPro",
    21: "Go",
    22: "Groovy",
    23: "HLSL",
    24: "HTML",
    25: "Haskell",
    26: "INI",
    27: "JSON",
    28: "Java",
    29: "JavaScript",
    30: "Julia",
    31: "Kotlin",
    32: "LaTeX",
    33: "Lisp",
    34: "Logo",
    35: "Lua",
    36: "MATLAB",
    37: "Makefile",
    38: "Markdown",
    39: "Nginx",
    40: "Objective-C",
    41: "OpenEdge",
    42: "PHP",
    43: "Perl",
    44: "PowerShell",
    45: "Prolog",
    46: "Protocol Buffer",
    47: "Python",
    48: "R",
    49: "REST",
    50: "Ruby",
    51: "Rust",
    52: "SAS",
    53: "SQL",
    54: "Scala",
    55: "Scheme",
    56: "Shell",
    57: "Solidity",
    58: "Swift",
    59: "TypeScript",
    60: "VBA",
    61: "Visual Basic",
    62: "WebAssembly",
    63: "XML",
    64: "YAML",
    65: "CSharp",
}

# block_type → 对齐方式所在字段名的映射
_ALIGN_KEY_MAP: dict[int, str] = {
    2: "text",
    3: "heading1",
    4: "heading2",
    5: "heading3",
    6: "heading4",
    7: "heading5",
    8: "heading6",
    9: "heading7",
    10: "heading8",
    11: "heading9",
    12: "bullet",
    13: "ordered",
}

# Lark align 值 → Alignment 枚举
_LARK_TO_ALIGNMENT: dict[int, Alignment] = {
    1: Alignment.LEFT,
    2: Alignment.CENTER,
    3: Alignment.RIGHT,
}


# =============================================================================
# 飞书 REST 客户端
# =============================================================================


class _LarkHttpClient(ClientSessionWithLog):
    """飞书 API 的异步 HTTP 客户端（自动管理 tenant_access_token）。"""

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._tenant_token: str | None = None
        super().__init__(headers={"User-Agent": "article-publisher/0.1.0 (aiohttp)"})

    def _log_tag(self) -> str:
        return "LARK"

    async def _ensure_token(self) -> str:
        if self._tenant_token:
            return self._tenant_token
        resp = await self.request(
            "POST",
            f"{LARK_API_BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        data = await resp.json()
        self._tenant_token = data["tenant_access_token"]
        assert self._tenant_token is not None
        # _ensure_token 后需设置 Authorization 头部供后续请求使用
        # 直接修改 session 的默认头部
        self._default_headers["Authorization"] = f"Bearer {self._tenant_token}"
        return self._tenant_token

    async def _request_with_auth(
        self, method: str, path: str, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """发送已携带 tenant_access_token 的 HTTP 请求。"""
        await self._ensure_token()
        return await self.request(method, f"{LARK_API_BASE}{path}", **kwargs)

    async def get_json(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """发送 GET 请求并返回 JSON 响应。"""
        resp = await self._request_with_auth("GET", path, **kwargs)
        data = await resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"飞书 API 错误: [{data.get('code')}] {data.get('msg')}")
        return data

    async def get_bytes(self, path: str, **kwargs: Any) -> bytes:
        """发送 GET 请求并返回原始字节（用于下载文件）。"""
        resp = await self._request_with_auth("GET", path, **kwargs)
        if resp.status != 200:
            raise RuntimeError(f"飞书文件下载失败: HTTP {resp.status}")
        return await resp.read()


# =============================================================================
# 转换器
# =============================================================================


class LarkDocxConverter(Converter):
    """将飞书云文档转换为 IR Document。"""

    def __init__(self, app_id: str, app_secret: str, document_id: str):
        self.document_id = document_id
        self._lark = _LarkHttpClient(app_id, app_secret)

        # block_id → block dict
        self._blocks: dict[str, dict[str, Any]] = {}
        self._root_block_id: str = ""

    # ------------------------------------------------------------------
    # 文档元信息
    # ------------------------------------------------------------------

    async def _fetch_document_info(self) -> dict[str, Any]:
        """获取文档基本信息（结果缓存避免重复请求）。"""
        if not hasattr(self, "_cached_doc_info"):
            data = await self._lark.get_json(f"/docx/v1/documents/{self.document_id}")
            doc = data["data"]["document"]
            cover_token: str | None = None
            cover = doc.get("cover")
            if cover and cover.get("token"):
                cover_token = cover["token"]
            self._cached_doc_info = {
                "document_id": doc["document_id"],
                "title": doc["title"],
                "revision_id": doc["revision_id"],
                "cover_token": cover_token,
            }
        return self._cached_doc_info

    async def get_title(self) -> str:
        """从飞书文档基本信息中提取标题。"""
        info = await self._fetch_document_info()
        return info.get("title", "未命名文章")

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
        info = await self._fetch_document_info()
        cover_token = info.get("cover_token")
        if not cover_token:
            return None

        try:
            logger.info(f"正在下载封面图: token={cover_token}")
            image_data = await self._download_image(cover_token)
            _TEMP_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            tmp_path = _TEMP_IMAGES_DIR / f"cover_{cover_token}.png"
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
        items: list[dict[str, Any]] = []
        page_token = ""
        while True:
            params = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = await self._lark.get_json(
                f"/docx/v1/documents/{self.document_id}/blocks", params=params
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
        self, block_type: int, block: dict[str, Any], prefix: str, indent_level: int = 0
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
        self, block: dict[str, Any], indent_level: int = 0
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
        self, block: dict[str, Any], block_type: int, indent_level: int = 0
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

    def _convert_code(self, block: dict[str, Any]) -> CodeBlock | None:
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
            lang = _CODE_LANG_MAP.get(lang_id, "")

        if not content:
            return None
        return CodeBlock(language=lang, content=content)

    async def _convert_image(
        self, block: dict[str, Any], prefix: str
    ) -> ImageBlock | None:
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
            _TEMP_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            tmp_path = _TEMP_IMAGES_DIR / f"{token}.png"
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
        return await self._lark.get_bytes(f"/drive/v1/medias/{token}/download")

    # ------------------------------------------------------------------
    # 内联元素转换
    # ------------------------------------------------------------------

    def _elements_to_inline(self, elements: list[Any]) -> list[InlineElement]:
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

    def _text_run_to_run(self, text_run: dict[str, Any]) -> TextRun:
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
        elif style.get("text_color") is not None:
            color = _TEXT_COLOR_MAP.get(style["text_color"], "")

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
    def _extract_align(block: dict[str, Any]) -> Alignment:
        """从 Lark block 的 style 中提取对齐方式。
        Lark: 1=左对齐, 2=居中, 3=右对齐
        """
        key = _ALIGN_KEY_MAP.get(block.get("block_type", 0))
        if key is None:
            return Alignment.LEFT
        sub = block.get(key)
        if isinstance(sub, dict):
            s = sub.get("style") or {}
            lark_align = s.get("align", 1)
            return _LARK_TO_ALIGNMENT.get(lark_align, Alignment.LEFT)
        return Alignment.LEFT

    @staticmethod
    def _elements_to_plain_text(elements: list[Any]) -> str:
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
        await self._lark.close()


# =============================================================================
# 临时文件清理
# =============================================================================


def cleanup_temp_images() -> None:
    """清理飞书转换器产生的临时图片目录。"""
    if _TEMP_IMAGES_DIR.exists():
        shutil.rmtree(_TEMP_IMAGES_DIR)
        logger.info(f"已清理临时图片: {_TEMP_IMAGES_DIR}")
