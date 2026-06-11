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
from typing import TYPE_CHECKING, Any, Literal, TypedDict, cast

import aiohttp
import json5

from article_publisher.http_client import ClientSessionWithLog
from article_publisher.log import logger

if TYPE_CHECKING:
    from pathlib import Path

NGA_BASE = "https://bbs.nga.cn"
ATTACH_UPLOAD_URL = "https://img8.nga.cn/attach.php"
ATTACH_VIEW_BASE = "https://img.nga.178.com/attachments"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0"
)


class NgaApiError(Exception):
    """NGA API 返回错误时抛出的异常。"""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


type Action = Literal["new", "modify"]


@dataclass
class UploadedImage:
    """图片上传到 NGA 后的结果。"""

    url: str
    """相对路径，如 mon_202606/08/-xxx.webp"""

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


class AttachResponseData(TypedDict):
    attachments: str
    attachments_check: str
    url: str
    isImg: str
    thumb: str
    isVideo: str


class Attachment(TypedDict):
    attachurl: str
    size: int
    type: str
    subid: int
    url_urf8_org_name: str
    dscp: str
    path: str
    name: str
    ext: str
    thumb: int


# =============================================================================
# NGA 客户端
# =============================================================================


class NgaClient(ClientSessionWithLog):
    """封装与 NGA 后端交互的异步 HTTP 客户端。"""

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

        # 解析 Cookie 字符串为字典
        cookies: dict[str, str] = {}
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if "=" in pair:
                key, value = pair.split("=", 1)
                cookies[key.strip()] = value.strip()

        super().__init__(
            headers={
                "User-Agent": _USER_AGENT,
                "Referer": f"{NGA_BASE}/",
                "Origin": NGA_BASE,
            },
            cookies=cookies,
        )

    def _log_tag(self) -> str:
        return "NGA"

    async def get_post_php(
        self,
        action: Action,
        fid: str,
        tid: str | None = None,
        pid: str | None = None,
        article: str | None = None,
    ) -> str:
        match action:
            case "new":
                params: dict[str, Any] = {"action": "new", "_newui": "", "fid": fid}
            case "modify":
                params: dict[str, Any] = {
                    "action": "modify",
                    "_newui": "",
                    "fid": fid,
                    "tid": tid,
                    "pid": pid,
                    "article": article,
                }
            case _:
                raise ValueError(f"action 必须是 'new' 或 'modify'，但得到: {action!r}")

        url = f"{NGA_BASE}/post.php"

        resp = await self.request("GET", url, params=params)
        text = await resp.text()

        try:
            self._auth_token = self._parse_auth(text)
        except NgaApiError:
            raise NgaApiError(
                f"获取 auth token 失败。请检查 Cookie 是否有效。\n{text[:512]}"
            ) from None

        return text

    # ==================================================================
    # Auth Token
    # ==================================================================

    def get_auth_token(self) -> str:
        """
        获取图片上传所需的 auth token。

        通过访问发帖页面，从页面内嵌的 ``__U.auth`` 中提取。
        结果会缓存。
        """
        if not self._auth_token:
            raise NgaApiError(
                "auth token 未获取，请先调用 get_post_php() 获取发帖页面以提取 auth token。"
            )
        return self._auth_token

        # if self._auth_token:
        #     return self._auth_token

        # url = f"{NGA_BASE}/post.php"
        # params = {"action": "new", "_newui": "", "fid": self.fid}
        # logger.info(f"获取 auth token (fid={self.fid}) ...")

        # self._log_request("GET", url, params=params)
        # resp = self._session.get(url, params=params)
        # self._log_response(resp)
        # resp.raise_for_status()

        # # NGA 返回 GBK 编码，检查编码
        # text = resp.text
        # logger.debug(f"响应长度: {len(text)} 字节")
        # logger.debug(f"响应 URL: {resp.url}")

        # # 如果被重定向到登录页，resp.url 会变化
        # if "login" in resp.url.lower() or "account" in resp.url.lower():
        #     raise NgaApiError(
        #         "Cookie 无效或已过期，页面被重定向到登录页。请重新登录 NGA 后更新 Cookie。"
        #     )

        # # 从 HTML 中提取 __U.auth — 支持多行 JSON 格式
        # # 尝试多种匹配模式
        # match = re.search(
        #     r'"auth"\s*:\s*"([a-f0-9]+)"', text.replace("\n", " ").replace("\r", "")
        # )
        # if not match:
        #     # 尝试 __U = { ... } 格式
        #     match = re.search(
        #         r'__U\s*[=:]\s*\{.*?"auth"\s*:\s*"([^"]+)"',
        #         text.replace("\n", " "),
        #         re.DOTALL,
        #     )
        # if not match:
        #     logger.debug(f"页面片段 (500 字符): {text[:500]}")
        #     raise NgaApiError("无法从发帖页面提取 auth token，请检查 Cookie 是否有效。")

        # self._auth_token = cast("str", match.group(1))
        # logger.info("  → auth token 获取成功")
        # return self._auth_token

    # ==================================================================
    # 图片上传
    # ==================================================================

    async def upload_image(self, file_path: Path) -> UploadedImage:
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
        form = aiohttp.FormData()
        form.add_field("attachment_file1_dscp", "")
        form.add_field("attachment_file1_img", "1")
        form.add_field("attachment_file1_auto_size", "8")
        form.add_field("attachment_file1_watermark", "")
        form.add_field("func", "upload")
        form.add_field("v2", "1")
        form.add_field("origin_domain", "bbs.nga.cn")
        form.add_field("__output", "1")
        form.add_field("auth", auth)
        form.add_field("fid", str(self.fid))
        form.add_field(
            "attachment_file1_url_utf8_name", urllib.parse.quote(file_name, safe="")
        )
        form.add_field(
            "attachment_file1",
            file_path.read_bytes(),
            filename=file_name,
            content_type="application/octet-stream",
        )

        resp = await self.request("POST", ATTACH_UPLOAD_URL, data=form)

        if resp.status != 200:
            text = await resp.text()
            raise NgaApiError(f"图片上传失败 (HTTP {resp.status}): {text[:200]}")

        text = await resp.text()
        # 解析响应
        result = self._parse_upload_response(text)

        logger.info(f"  → 上传成功: {result['url']}")
        return UploadedImage(
            url=result["url"],
            size=file_size,
            attachment_str=result["attachments"],
            attachment_check=result["attachments_check"],
        )

    # ==================================================================
    # 提交帖子
    # ==================================================================

    async def submit_post(
        self,
        subject: str,
        content: str,
        attachment_strings: list[str],
        attachment_checks: list[str],
        *,
        tid: str | None = None,
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
            "hidden": "2",
            "attachments": attach_value,
            "attachments_check": attach_check_value,
            "self_reply": "",
            "newvote_max": "1",
            "nojump": "1",
            "lite": "htmljs",
            "step": "2",
        }

        if tid:
            data["tid"] = tid

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

        resp = await self.request("POST", url, data=body, headers=headers)
        text = await resp.text()

        # 解析响应
        result = self._parse_window_script_muti_get_var_store(text)

        # NGA 的 "成功" 响应也是在 error 字段中！"发贴完毕" 表示成功
        error_text = result.get("error", {}).get("0", "") or ""
        if error_text and "完毕" in error_text:
            # 成功！error[2] 可能是新的帖子 ID（仅新帖有效，编辑时不返回）
            new_tid = result.get("error", {}).get("2", "") or tid
            logger.info(f"  → 帖子提交成功！tid={new_tid}")
            logger.info(f"  → https://bbs.nga.cn/read.php?tid={new_tid}")
            return result

        if error_text:
            raise NgaApiError(f"发帖失败: {error_text}")

        logger.info("  → 帖子提交成功！")
        return result

    # ==================================================================
    # 附件管理（编辑帖子用）
    # ==================================================================

    async def get_recent_attachments(self, tid: str) -> list[Attachment]:
        """
        获取帖子当前的所有附件列表。

        用于编辑帖子时获取旧附件信息，以便后续删除。
        实际响应结构为 ``data["0"]["0"], data["0"]["1"], ...``，
        每个附件包含 ``attachurl``（相对路径）、``url_utf8_org_name``（原始文件名）等字段。

        Args:
            tid: 主题 ID

        Returns:
            附件信息列表（可能为空列表）
        """
        url = f"{NGA_BASE}/nuke.php"
        params: dict[str, str] = {
            "__lib": "attachment",
            "__act": "get_recent_attach",
            "__output": "3",
        }
        post_data: dict[str, str] = {"tid": tid}

        logger.info(f"获取帖子附件列表 (tid={tid}) ...")
        resp = await self.request("POST", url, params=params, data=post_data)
        text = await resp.text()

        result = self._parse_window_script_muti_get_var_store(text)
        if "error" in result:
            logger.warning(f"  [错误] {result['error']}")
            return []

        # 实际响应格式: {"data": {"0": {"0": {...}, "1": {...}, ...}}}
        attachments: list[Attachment] = list(
            result.get("data", {}).get("0", {}).values()
        )

        logger.info(f"  → 找到 {len(attachments)} 个附件")
        return attachments

    async def delete_attachment(self, tid: str, aid: str, pid: str = "0") -> bool:
        """
        删除帖子中的单个附件。

        Args:
            tid: 主题 ID
            aid: 附件标识符（值为附件数据中的 ``name`` 字段，即 NGA 存储的文件名）
            pid: 楼层 ID，主楼为 0

        Returns:
            是否删除成功
        """
        url = f"{NGA_BASE}/nuke.php"
        data = {
            "__lib": "del_attach",
            "__act": "del_attach",
            "pid": pid,
            "tid": tid,
            "aid": aid,
            "raw": "3",
        }

        logger.info(f"删除附件: {aid}")
        resp = await self.request("POST", url, data=data)

        if resp.status == 200:
            logger.debug(f"  → 删除成功: {aid}")
            return True
        else:
            logger.warning(f"  → 删除失败 (HTTP {resp.status}): {aid}")
            return False

    # ==================================================================
    # 响应解析
    # ==================================================================

    @staticmethod
    def _parse_auth(text: str) -> str:
        """
        从发帖页面 HTML 中提取 auth token。

        text 需包含 `"auth":"abcdef123456"`
        """
        match = re.search(r'["\']auth["\']:\s*["\']([^"\']+)["\']', text)
        if not match:
            raise NgaApiError(f"无法解析 auth token: {text[:256]}")
        return match.group(1)

    @staticmethod
    def _parse_window_script_muti_get_var_store(text: str) -> dict[str, Any]:
        """
        从包含 window.script_muti_get_var_store={...} 的响应中提取 JSON 对象。

        Args:
            text: 响应文本，其中只能包含一个 JSON 对象

        Returns:
            解析后的字典
        """

        # 假设 text 中只包含一个对象，直接使用贪婪匹配
        match = re.search(
            r"window\s*\.\s*script_muti_get_var_store\s*=\s*(\{.*\})", text, re.DOTALL
        )
        if not match:
            raise NgaApiError(
                f"无法解析 window.script_muti_get_var_store: {text[:256]}"
            )
        json_str = match.group(1)

        try:
            obj = cast("dict[str, Any]", json5.loads(json_str))
        except (ValueError, UnicodeDecodeError):
            raise NgaApiError(
                f"无法解析 window.script_muti_get_var_store: {text[:256]}"
            ) from None

        return obj

    @staticmethod
    def _parse_upload_response(text: str) -> AttachResponseData:
        """
        解析 NGA 图片上传响应。

        响应格式：
        window.script_muti_get_var_store={data:{attachments:'...',attachments_check:'...',url:'...',isImg:'1',...}}
        """

        obj = NgaClient._parse_window_script_muti_get_var_store(text)

        if "data" not in obj:
            raise NgaApiError(f"上传响应缺少 data 字段: {text[:256]}")

        data = obj["data"]

        return AttachResponseData(**data)
