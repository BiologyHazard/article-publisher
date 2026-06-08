"""
NGA API 客户端。

提供 NGA 相关的 HTTP API 调用，包括：
- Cookie 认证
- 获取 auth token（上传图片所需）
- 图片上传到 NGA 图床
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from PIL import Image

from bilibili_article.log import logger

# =============================================================================
# 常量
# =============================================================================

NGA_BASE = "https://bbs.nga.cn"
ATTACH_UPLOAD_URL = "https://img8.nga.cn/attach.php"
ATTACH_VIEW_BASE = "https://img.nga.178.com/attachments"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0"
)


# =============================================================================
# 异常
# =============================================================================


class NgaApiError(Exception):
    """NGA API 返回错误时抛出的异常。"""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


# =============================================================================
# 图片上传结果
# =============================================================================


@dataclass
class UploadedImage:
    """图片上传到 NGA 后的结果。"""

    url: str
    """相对路径，如 mon_202606/08/-xxx.webp"""

    width: int
    height: int
    size: int
    attachment_str: str
    """attachments 字段值（发帖时需要附带）"""

    attachment_check: str
    """attachments_check 字段值（发帖时需要附带）"""

    @property
    def bbcode(self) -> str:
        """生成 NGA 正文中使用的 [img] BBCode。"""
        return f"[img]./{self.url}[/img]"

    @property
    def full_url(self) -> str:
        """图片完整 URL。"""
        return f"{ATTACH_VIEW_BASE}/{self.url}"


# =============================================================================
# NGA 客户端
# =============================================================================


class NgaClient:
    """封装与 NGA 后端交互的 HTTP 客户端。"""

    def __init__(self, cookie_str: str, fid: int) -> None:
        """
        Args:
            cookie_str: 完整的 Cookie 字符串（从浏览器复制）
            fid: 目标版块 ID
        """
        self.fid = fid
        self.uid: str | None = None
        """当前登录用户的 UID（从 __U 中提取，可用于获取帖子列表 URL）"""
        self._auth_token: str | None = None

        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": _USER_AGENT, "Referer": f"{NGA_BASE}/", "Origin": NGA_BASE}
        )

        # 解析并设置 Cookie
        # cookies 来自 bbs.nga.cn，设置 domain 以覆盖所有 nga.cn 子域
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if "=" in pair:
                key, value = pair.split("=", 1)
                self._session.cookies.set(key.strip(), value.strip(), domain=".nga.cn")

    # ==================================================================
    # Auth Token
    # ==================================================================

    def get_auth_token(self) -> str:
        """
        获取图片上传所需的 auth token。

        通过访问发帖页面，从页面内嵌的 ``__U.auth`` 中提取。
        结果会缓存。
        """
        if self._auth_token:
            return self._auth_token

        url = f"{NGA_BASE}/post.php"
        params = {"action": "new", "_newui": "", "fid": self.fid}
        logger.info(f"获取 auth token (fid={self.fid}) ...")

        resp = self._session.get(url, params=params)
        resp.raise_for_status()

        # NGA 返回 GBK 编码，检查编码
        text = resp.text
        logger.debug(f"响应长度: {len(text)} 字节")
        logger.debug(f"响应 URL: {resp.url}")

        # 如果被重定向到登录页，resp.url 会变化
        if "login" in resp.url.lower() or "account" in resp.url.lower():
            raise NgaApiError(
                "Cookie 无效或已过期，页面被重定向到登录页。请重新登录 NGA 后更新 Cookie。"
            )

        # 从 HTML 中提取 __U.auth — 支持多行 JSON 格式
        # 尝试多种匹配模式
        match = re.search(
            r'"auth"\s*:\s*"([a-f0-9]+)"', text.replace("\n", " ").replace("\r", "")
        )
        if not match:
            # 尝试 __U = { ... } 格式
            match = re.search(
                r'__U\s*[=:]\s*\{.*?"auth"\s*:\s*"([^"]+)"',
                text.replace("\n", " "),
                re.DOTALL,
            )
        if not match:
            logger.debug(f"页面片段 (500 字符): {text[:500]}")
            raise NgaApiError("无法从发帖页面提取 auth token，请检查 Cookie 是否有效。")

        self._auth_token = match.group(1)
        logger.info(f"  → auth token 获取成功")
        return self._auth_token

    # ==================================================================
    # 图片上传
    # ==================================================================

    def upload_image(self, file_path: Path) -> UploadedImage:
        """
        将本地图片上传到 NGA 图床。

        流程：获取 auth token → multipart/form-data 上传 → 解析响应。
        """
        if not file_path.is_file():
            raise NgaApiError(f"文件不存在: {file_path}")

        auth = self.get_auth_token()
        file_name = file_path.name
        file_size = file_path.stat().st_size

        logger.info(f"上传图片: {file_path.name} ({file_size} bytes)")

        # 构建 multipart form-data
        with open(file_path, "rb") as f:
            files: dict[str, Any] = {
                "attachment_file1_dscp": (None, ""),
                "attachment_file1_img": (None, "1"),
                "attachment_file1_auto_size": (None, "8"),
                "attachment_file1_watermark": (None, ""),
                "func": (None, "upload"),
                "v2": (None, "1"),
                "origin_domain": (None, "bbs.nga.cn"),
                "__output": (None, "1"),
                "auth": (None, auth),
                "fid": (None, str(self.fid)),
                "attachment_file1_url_utf8_name": (
                    None,
                    requests.utils.quote(file_name, safe=""),
                ),
                "attachment_file1": (file_name, f, "application/octet-stream"),
            }

            resp = self._session.post(ATTACH_UPLOAD_URL, files=files)

        if resp.status_code != 200:
            raise NgaApiError(
                f"图片上传失败 (HTTP {resp.status_code}): {resp.text[:200]}"
            )

        # 解析响应
        result = self._parse_upload_response(resp.text)

        # 获取图片尺寸
        with Image.open(file_path) as img:
            width, height = img.size

        logger.info(f"  → 上传成功: {result['url']}")
        return UploadedImage(
            url=result["url"],
            width=width,
            height=height,
            size=file_size,
            attachment_str=result["attachments"],
            attachment_check=result["attachments_check"],
        )

    # ==================================================================
    # 提交帖子
    # ==================================================================

    def submit_post(
        self,
        subject: str,
        content: str,
        attachment_strings: list[str],
        attachment_checks: list[str],
        *,
        tid: int | None = None,
    ) -> dict[str, Any]:
        """
        提交帖子到 post.php。

        使用与上传图片相同的 session，确保 checksum 匹配。
        """
        attach_value = "\t".join(attachment_strings) + "\t"
        attach_check_value = "\t".join(attachment_checks) + "\t"

        url = f"{NGA_BASE}/post.php"
        logger.info(f"提交帖子: {subject[:50]}...")

        # 构建表单数据
        # 非 ASCII 内容（标题、正文）需要 GBK URL 编码
        data: dict[str, str] = {
            "action": "modify" if tid else "new",
            "fid": str(self.fid),
            "post_subject": subject,
            "post_content": content,
            "attachments": attach_value,
            "attachments_check": attach_check_value,
            "hidden": "2",
            "self_reply": "",
            "newvote_max": "1",
            "nojump": "1",
            "lite": "htmljs",
            "step": "2",
        }

        if tid:
            data["tid"] = str(tid)

        # 手动构建 GBK URL-encoded body
        body_parts: list[bytes] = []
        for key, value in data.items():
            k_enc = urllib.parse.quote(key.encode("gbk"), safe="")
            if key in ("post_subject", "post_content"):
                # 中文字段用 GBK 编码后 URL 编码
                v_enc = urllib.parse.quote(
                    value.encode("gbk", errors="replace"), safe=""
                )
            else:
                # ASCII 字段直接 URL 编码
                v_enc = urllib.parse.quote(value, safe="")
            body_parts.append(f"{k_enc}={v_enc}".encode("gbk"))

        body = b"&".join(body_parts)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        resp = self._session.post(url, data=body, headers=headers)
        text = resp.text

        # 解析响应
        result = self._parse_post_response(text)

        # NGA 的 "成功" 响应也是在 error 字段中！"发贴完毕" 表示成功
        error_text = result.get("error", {}).get("0", "") or ""
        if error_text and "完毕" in error_text:
            # 成功！error[2] 可能是帖子 ID
            tid = result.get("error", {}).get("2", "")
            logger.info(f"  → 帖子提交成功！tid={tid}")
            logger.info(f"  → https://bbs.nga.cn/read.php?tid={tid}")
            return result

        if error_text:
            raise NgaApiError(f"发帖失败: {error_text}")

        logger.info("  → 帖子提交成功！")
        return result

    @staticmethod
    def _parse_post_response(text: str) -> dict[str, Any]:
        """解析 post.php 响应。"""
        import json

        match = re.search(
            r"window\.script_muti_get_var_store\s*=\s*(\{.+?\})", text, re.DOTALL
        )
        if not match:
            # 尝试直接 JSON 解析
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                # 检查是否有错误提示
                if "你没有登录" in text:
                    return {"error": {"0": "Cookie 已过期，请重新登录"}}
                return {"error": {"0": f"无法解析响应: {text[:200]}"}}

        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return {"error": {"0": f"JSON 解析失败: {match.group(1)[:200]}"}}

    @staticmethod
    def _parse_upload_response(text: str) -> dict[str, str]:
        """
        解析 NGA 图片上传响应。

        响应格式：
        window.script_muti_get_var_store={data:{attachments:'...',attachments_check:'...',url:'...',isImg:'1',...}}
        """
        # 直接用更健壮的方式提取各字段
        result: dict[str, str] = {}

        # 提取 data: { ... } 中的内容（非贪婪匹配外层大括号）
        data_match = re.search(r"data\s*:\s*\{(.*)\}\s*\}", text, re.DOTALL)
        if not data_match:
            raise NgaApiError(f"无法解析 data 字段: {text[:300]}")

        data_str = data_match.group(1)

        # 逐个提取关键字段
        for key in ("url", "attachments", "attachments_check", "isImg", "isVideo"):
            m = re.search(
                r'["\']?' + key + r'["\']?\s*:\s*["\']([^"\']+)["\']', data_str
            )
            if m:
                result[key] = m.group(1)

        if "url" not in result:
            raise NgaApiError(f"响应中缺少 url 字段: {text[:300]}")

        return result
