"""
森空岛 API 客户端。

提供森空岛相关的 HTTP API 调用，包括：
- 鹰角网络 OAuth2 认证流程
- OSS STS 凭证获取与图片上传
- 用户信息查询
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import requests
from PIL import Image

from article_publisher.log import logger

if TYPE_CHECKING:
    from pathlib import Path


# =============================================================================
# 异常
# =============================================================================


class SklandApiError(Exception):
    """森空岛 API 返回非 0 code 时抛出的异常。"""

    def __init__(self, code: int, message: str, raw: Any = None) -> None:
        self.code = code
        self.message = message
        self.raw = raw
        super().__init__(f"[{code}] {message}")


# =============================================================================
# 图片上传结果
# =============================================================================


@dataclass
class UploadedImage:
    """图片上传到森空岛 OSS 后的结果。"""

    url: str
    width: int
    height: int
    size: int
    image_id: str


# =============================================================================
# 签名工具
# =============================================================================


def _build_sign_headers(
    method: str, url: str, sign_token: str, d_id: str, *, body: str | None = None
) -> dict[str, str]:
    """
    计算森空岛 API 请求签名头。

    算法: sign = MD5(HMAC-SHA256(path + body/query + timestamp + JSON(headers), sign_token))

    headers 顺序固定为 platform → timestamp → dId → vName，不可改变。
    """
    parsed = urllib.parse.urlparse(url)
    body_or_query = parsed.query if method.upper() == "GET" else (body or "")

    timestamp = str(int(time.time()))

    # 顺序不可改变
    header_dict = {
        "platform": "3",
        "timestamp": timestamp,
        "dId": d_id,
        "vName": "1.21.0",
    }

    header_json = json.dumps(header_dict, separators=(",", ":"))
    raw = parsed.path + body_or_query + timestamp + header_json

    hex_s = hmac.new(
        sign_token.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    header_dict["sign"] = hashlib.md5(hex_s.encode("utf-8")).hexdigest()
    return header_dict


# =============================================================================
# API 端点
# =============================================================================

API_BASE = "https://zonai.skland.com"
AS_BASE = "https://as.hypergryph.com"
SKLAND_APP_CODE = "4ca99fa6b56cc2ba"

# =============================================================================
# 客户端
# =============================================================================


class SklandClient:
    """封装与森空岛后端交互的 HTTP 客户端。"""

    def __init__(self, hypergryph_token: str, skland_did: str) -> None:
        self._did = skland_did
        self._cred: str | None = None
        self._sign_token: str | None = None

        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0"
                ),
                "Origin": "https://www.skland.com",
                "Referer": "https://www.skland.com/",
            }
        )

        self._perform_auth(hypergryph_token)

    # ==================================================================
    # 认证流程
    # ==================================================================

    def _perform_auth(self, hypergryph_token: str) -> None:
        """完成森空岛认证：HYPERGRYPH_TOKEN → grant code → cred + sign_token。"""
        grant_code = self._get_grant_code(hypergryph_token)
        self._get_cred_and_token(grant_code)
        logger.info("森空岛认证成功")

    def _get_grant_code(self, token: str) -> str:
        """通过鹰角网络 OAuth2 获取 grant code。

        注意：鹰角网络 API 的响应格式与森空岛不同，
        没有顶层的 ``code`` / ``message`` 包裹，直接返回 ``data``。
        """
        resp = self._session.post(
            f"{AS_BASE}/user/oauth2/v2/grant",
            json={"appCode": SKLAND_APP_CODE, "token": token, "type": 0},
        )
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        try:
            return str(body["data"]["code"])
        except KeyError:
            return str(body["data"]["token"])

    def _get_cred_and_token(self, grant_code: str) -> None:
        """通过 grant code 获取 cred 和 sign_token。"""
        resp = self._session.post(
            f"{API_BASE}/web/v1/user/auth/generate_cred_by_code",
            headers={"dId": self._did},
            json={"code": grant_code, "kind": 1},
        )
        data = self._check_response(resp)
        self._cred = data["data"]["cred"]
        self._sign_token = data["data"]["token"]

    # ==================================================================
    # 响应处理
    # ==================================================================

    @staticmethod
    def _check_response(resp: requests.Response) -> dict[str, Any]:
        """检查 API 响应，成功返回 data 字典，失败抛出异常。"""
        try:
            body = resp.json()
        except ValueError as exc:
            raise SklandApiError(-1, f"无法解析响应: {resp.text[:200]}") from exc

        if body.get("code") != 0:
            raise SklandApiError(
                body.get("code", -1),
                body.get("message", body.get("msg", "未知错误")),
                raw=body,
            )
        return body

    # ==================================================================
    # 签名请求
    # ==================================================================

    def _request_with_sign(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """发送带签名的 API 请求，返回响应 data。"""
        assert self._sign_token is not None, "未完成认证"
        assert self._cred is not None, "未完成认证"

        # 构造完整 URL
        url = f"{API_BASE}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)

        # 签名用的 body 字符串（必须与 requests 发送的完全一致）
        body_str = json.dumps(json_body, separators=(",", ":")) if json_body else None

        # 计算签名头
        sign_headers = _build_sign_headers(
            method, url, self._sign_token, self._did, body=body_str
        )
        # cred 是独立请求头，不参与签名计算
        sign_headers["cred"] = self._cred

        # 发送请求
        kwargs: dict[str, Any] = {"headers": sign_headers}
        if json_body is not None:
            kwargs["data"] = body_str
            kwargs["headers"]["Content-Type"] = "application/json"

        resp = self._session.request(method, url, **kwargs)
        return self._check_response(resp)

    # ==================================================================
    # 用户信息
    # ==================================================================

    def get_user_id(self) -> str:
        """获取当前登录用户的数字 ID（取 ``data.user.id``）。"""
        resp = self._request_with_sign("GET", "/web/v1/user")
        return str(resp["data"]["user"]["id"])

    # ==================================================================
    # 图片上传
    # ==================================================================

    def upload_image(self, file_path: Path) -> UploadedImage:
        """
        将本地图片上传到森空岛 OSS 图床。

        流程：获取 OSS STS 凭证 → FormData 上传到阿里云 OSS → 返回 CDN URL。
        """
        file_ext = file_path.suffix.lstrip(".").lower() or "png"

        # Step 1: 获取 OSS STS 凭证
        logger.info(f"获取 OSS 上传凭证: {file_path.name}")
        sts_data = self._request_with_sign(
            "POST", "/web/v1/oss/sts", json_body={"kind": "image", "fileExt": file_ext}
        )

        sts_body: dict[str, str] = sts_data["data"]["body"]
        upload_url: str = sts_data["data"]["uploadURL"]
        address_url: str = sts_data["data"]["addressURL"]

        # Step 2: 上传到 OSS（multipart/form-data）
        logger.info(f"上传到 OSS: {file_path.name}")
        with open(file_path, "rb") as f:
            files = {
                "OSSAccessKeyId": (None, sts_body["OSSAccessKeyId"]),
                "callback": (None, sts_body["callback"]),
                "key": (None, sts_body["key"]),
                "policy": (None, sts_body["policy"]),
                "signature": (None, sts_body["signature"]),
                "successActionStatus": (None, sts_body["successActionStatus"]),
                "x:image_id": (None, sts_body["x:image_id"]),
                "file": (file_path.name, f, f"image/{file_ext}"),
            }
            oss_resp = self._session.post(upload_url, files=files)

        if oss_resp.status_code != 200:
            raise SklandApiError(
                -1, f"OSS 上传失败 (HTTP {oss_resp.status_code}): {oss_resp.text[:200]}"
            )

        # 从本地文件获取图片尺寸
        with Image.open(file_path) as img:
            width, height = img.size
        file_size = file_path.stat().st_size

        logger.info(f"  → 上传成功: {address_url}")
        return UploadedImage(
            url=address_url,
            width=width,
            height=height,
            size=file_size,
            image_id=sts_body["x:image_id"],
        )
