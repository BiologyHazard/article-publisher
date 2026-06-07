"""
B站 API 客户端封装。

提供 B站 Opus 专栏相关的 HTTP API 调用，包括：
- WBI 签名
- 图片上传（双通道：upload_bfs + upcover 回退）
- 保存草稿
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import requests
from PIL import Image

from bilibili_article._wbi import (
    BILI_API_BASE,
    fetch_wbi_keys,
    get_mixin_key,
    sign_wbi_params,
)
from bilibili_article.log import logger

if TYPE_CHECKING:
    from bilibili_article.models import Payload, UploadedImage


class BiliApiError(Exception):
    """B站 API 返回非 0 code 时抛出的异常。"""

    def __init__(self, code: int, message: str, raw: Any = None):
        self.code = code
        self.message = message
        self.raw = raw
        super().__init__(f"[{code}] {message}")


class BiliClient:
    """封装与 B站后端交互的通用 HTTP 客户端。"""

    def __init__(self, sessdata: str, bili_jct: str, buvid3: str):
        self.csrf = bili_jct
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                "Referer": "https://member.bilibili.com/platform/upload/text/new-edit",
                "Origin": "https://member.bilibili.com",
            }
        )
        self.session.cookies.set("SESSDATA", sessdata, domain=".bilibili.com")
        self.session.cookies.set("bili_jct", bili_jct, domain=".bilibili.com")
        self.session.cookies.set("buvid3", buvid3, domain=".bilibili.com")
        self._mixin_key: str | None = None

    # ------------------------------------------------------------------
    # WBI 签名
    # ------------------------------------------------------------------

    def _ensure_mixin_key(self) -> str:
        """获取或生成 WBI mixin_key。"""
        if self._mixin_key is None:
            img_key, sub_key = fetch_wbi_keys(self.session)
            self._mixin_key = get_mixin_key(img_key + sub_key)
        return self._mixin_key

    def sign(self, params: dict[str, Any]) -> dict[str, Any]:
        """为参数字典附加 WBI 签名。"""
        mixin_key = self._ensure_mixin_key()
        return sign_wbi_params(params, mixin_key)

    # ------------------------------------------------------------------
    # 图片上传
    # ------------------------------------------------------------------

    def upload_image(self, file_path: Path) -> UploadedImage:
        """
        将本地图片上传到 B站图床，返回图片 URL、宽高及文件大小。
        """
        try:
            return self._upload_image_bfs(file_path)
        except BiliApiError as e:
            logger.info(f"upload_bfs 上传失败 ({e.message})，尝试 upcover 接口...")
            return self._upload_image_fallback(file_path)

    def _upload_image_bfs(self, file_path: Path) -> UploadedImage:
        """使用 Opus 编辑器专用接口上传图片（需要 WBI 签名）。"""
        url = f"{BILI_API_BASE}/x/dynamic/feed/draw/upload_bfs"
        params = self.sign(
            {
                "csrf": self.csrf,
                "biz": "new_dyn",
                "category": "daily",
            }
        )
        file_name = file_path.name
        file_size_kb = round(file_path.stat().st_size / 1024, 2)
        with open(file_path, "rb") as f:
            files = {"file_up": (file_name, f, self._detect_mime(file_path))}
            data = {
                "biz": "new_dyn",
                "category": "daily",
                "csrf": self.csrf,
            }
            response = self.session.post(url, params=params, files=files, data=data)
        result = response.json()
        if result.get("code") != 0:
            raise BiliApiError(
                result.get("code", -1),
                result.get("message", "upload_bfs失败"),
                result,
            )
        return self._format_image_result(
            file_path, result["data"]["image_url"], file_size_kb
        )

    def _upload_image_fallback(self, file_path: Path) -> UploadedImage:
        """使用旧版 upcover 接口上传图片。"""
        url = f"{BILI_API_BASE}/x/article/creative/article/upcover"
        file_name = file_path.name
        file_size_kb = round(file_path.stat().st_size / 1024, 2)
        with open(file_path, "rb") as f:
            files = {"binary": (file_name, f, self._detect_mime(file_path))}
            data = {"csrf": self.csrf, "cover": ""}
            response = self.session.post(url, files=files, data=data)
        result = response.json()
        if result.get("code") != 0:
            raise BiliApiError(
                result.get("code", -1),
                result.get("message", "图片上传失败"),
                result,
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

    def save_draft(self, payload: Payload) -> dict[str, Any]:
        """
        将专栏保存到草稿箱。
        payload 结构详见 models.py 中的 Payload 定义。
        返回响应 JSON。
        """
        url = f"{BILI_API_BASE}/x/dynamic/feed/article/draft/add"
        params = self.sign({"csrf": self.csrf})
        response = self.session.post(url, params=params, json=payload)  # type: ignore
        result = response.json()
        if result.get("code") != 0:
            raise BiliApiError(
                result.get("code", -1),
                result.get("message", "保存草稿失败"),
                result,
            )
        return result
