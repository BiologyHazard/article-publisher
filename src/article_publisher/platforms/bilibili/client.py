"""
B站 API 客户端封装。

提供 B站 Opus 专栏相关的 HTTP API 调用，包括：
- WBI 签名
- 图片上传（双通道：upload_bfs + upcover 回退）
- 保存草稿
"""

from typing import Any
lazy from pathlib import Path

import aiohttp
from PIL import Image

from article_publisher.http_client import ClientSessionWithLog
from article_publisher.log import logger
from article_publisher.platforms.bilibili._wbi import (
    BILI_API_BASE,
    fetch_wbi_keys,
    get_mixin_key,
    sign_wbi_params,
)
lazy from article_publisher.platforms.bilibili.models import Payload, UploadedImage


class BiliApiError(Exception):
    """B站 API 返回非 0 code 时抛出的异常。"""

    def __init__(self, code: int, message: str, raw: Any = None):
        self.code = code
        self.message = message
        self.raw = raw
        super().__init__(f"[{code}] {message}")


class BiliClient(ClientSessionWithLog):
    """封装与 B站后端交互的通用 HTTP 客户端。"""

    def __init__(self, cookie_str: str):
        """使用浏览器请求头中的完整 Cookie，并提取 bili_jct 用于 CSRF 校验。"""
        cookie_str = cookie_str.strip()
        cookies: dict[str, str] = {}
        for pair in cookie_str.split(";"):
            key, separator, value = pair.strip().partition("=")
            if separator:
                cookies[key.strip()] = value.strip()
        missing = [key for key in ("SESSDATA", "bili_jct") if not cookies.get(key)]
        if missing:
            raise ValueError(
                f"BILIBILI_COOKIE 缺少必要字段：{', '.join(missing)}；"
                "请从浏览器请求头复制完整的 Cookie 值。"
            )
        self.csrf = cookies["bili_jct"]
        super().__init__(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
                "Referer": "https://member.bilibili.com/",
                "Origin": "https://member.bilibili.com",
                "Cookie": cookie_str,
            }
        )
        self._mixin_key: str | None = None

    def _log_tag(self) -> str:
        return "BILI"

    # ------------------------------------------------------------------
    # WBI 签名
    # ------------------------------------------------------------------

    async def _ensure_mixin_key(self) -> str:
        """获取或生成 WBI mixin_key。"""
        if self._mixin_key is None:
            img_key, sub_key = await fetch_wbi_keys(self)
            self._mixin_key = get_mixin_key(img_key + sub_key)
        return self._mixin_key

    async def sign(self, params: dict[str, Any]) -> dict[str, Any]:
        """为参数字典附加 WBI 签名。"""
        mixin_key = await self._ensure_mixin_key()
        return sign_wbi_params(params, mixin_key)

    # ------------------------------------------------------------------
    # 图片上传
    # ------------------------------------------------------------------

    async def upload_image(self, file_path: Path) -> UploadedImage:
        """
        将本地图片上传到 B站图床，返回图片 URL、宽高及文件大小。
        """
        try:
            return await self._upload_image_bfs(file_path)
        except BiliApiError as e:
            logger.info(f"upload_bfs 上传失败 ({e.message})，尝试 upcover 接口...")
            return await self._upload_image_fallback(file_path)

    async def _upload_image_bfs(self, file_path: Path) -> UploadedImage:
        """使用 Opus 编辑器专用接口上传图片（需要 WBI 签名）。"""
        url = f"{BILI_API_BASE}/x/dynamic/feed/draw/upload_bfs"
        params = await self.sign(
            {"csrf": self.csrf, "biz": "new_dyn", "category": "daily"}
        )
        file_name = file_path.name
        file_size_kb = round(file_path.stat().st_size / 1024, 2)

        mime_type = Image.open(file_path).get_format_mimetype()
        data = aiohttp.FormData()
        data.add_field(
            "file_up",
            file_path.read_bytes(),
            filename=file_name,
            content_type=mime_type,
        )
        data.add_field("biz", "new_dyn")
        data.add_field("category", "daily")
        data.add_field("csrf", self.csrf)

        resp = await self.request("POST", url, params=params, data=data)
        result = await resp.json()

        if result.get("code") != 0:
            raise BiliApiError(
                result.get("code", -1), result.get("message", "upload_bfs失败"), result
            )
        return self._format_image_result(
            file_path, result["data"]["image_url"], file_size_kb
        )

    async def _upload_image_fallback(self, file_path: Path) -> UploadedImage:
        """使用旧版 upcover 接口上传图片。"""
        url = f"{BILI_API_BASE}/x/article/creative/article/upcover"
        file_name = file_path.name
        file_size_kb = round(file_path.stat().st_size / 1024, 2)

        mime = self._detect_mime(file_path)
        data = aiohttp.FormData()
        data.add_field(
            "binary", file_path.read_bytes(), filename=file_name, content_type=mime
        )
        data.add_field("csrf", self.csrf)
        data.add_field("cover", "")

        resp = await self.request("POST", url, data=data)
        result = await resp.json()

        if result.get("code") != 0:
            raise BiliApiError(
                result.get("code", -1), result.get("message", "图片上传失败"), result
            )
        return self._format_image_result(file_path, result["data"]["url"], file_size_kb)

    @staticmethod
    def _format_image_result(
        file_path: Path, raw_url: str, file_size_kb: float
    ) -> UploadedImage:
        """统一处理图片上传结果：获取尺寸、标准化 URL、构建返回字典。"""
        with Image.open(file_path) as img:
            w, h = img.size
        if raw_url.startswith("http://"):
            raw_url = "https://" + raw_url[7:]
        return {"url": raw_url, "width": w, "height": h, "size": file_size_kb}

    @staticmethod
    def _detect_mime(path: Path) -> str:
        ext = path.suffix.lower()
        return {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }.get(ext, "application/octet-stream")

    # ------------------------------------------------------------------
    # 专栏草稿箱
    # ------------------------------------------------------------------

    async def save_draft(self, payload: Payload) -> dict[str, Any]:
        """
        将专栏保存到草稿箱。
        payload 结构详见 models.py 中的 Payload 定义。
        返回响应 JSON。
        """
        url = f"{BILI_API_BASE}/x/dynamic/feed/article/draft/add"
        params = await self.sign({"csrf": self.csrf})
        resp = await self.request("POST", url, params=params, json=payload)
        result = await resp.json()
        if result.get("code") != 0:
            raise BiliApiError(
                result.get("code", -1), result.get("message", "保存草稿失败"), result
            )
        return result

    # ------------------------------------------------------------------
    # 编辑已发布文章
    # ------------------------------------------------------------------

    async def edit_opus(
        self,
        dyn_id_str: str,
        upload_id: str,
        opus: dict[str, Any],
        *,
        scene: int = 12,
        option: dict[str, Any] | None = None,
        meta: dict[str, Any] | None = None,
        topic: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        编辑已发布的 Opus 专栏文章。

        参数:
            dyn_id_str: 文章的动态 ID（从 article/view 接口获取的 dyn_id_str）
            upload_id: 上传会话 ID，格式 ``{mid}_{timestamp}_{random}``
            opus: Opus 内容体（与 save_draft 的 opus 字段结构一致）
            scene: 场景值，默认 12（编辑）
            option: 附加选项（aigc、评论等）
            meta: 元信息（app_meta 等）
            topic: 话题信息
        """
        url = f"{BILI_API_BASE}/x/dynamic/feed/edit/opus"
        params = await self.sign({"csrf": self.csrf})

        opus_req: dict[str, Any] = {
            "upload_id": upload_id,
            "opus": opus,
            "scene": scene,
            "meta": meta
            or {"app_meta": {"from": "edit.creative.h5", "mobi_app": "web"}},
            "option": option or {"aigc": 2, "close_comment": 0, "up_choose_comment": 0},
        }
        if topic:
            opus_req["topic"] = topic

        body = {"raw_content": "", "opus_req": opus_req, "dyn_id_str": dyn_id_str}

        resp = await self.request("POST", url, params=params, json=body)
        result = await resp.json()
        if result.get("code") != 0:
            raise BiliApiError(
                result.get("code", -1), result.get("message", "编辑文章失败"), result
            )
        return result
