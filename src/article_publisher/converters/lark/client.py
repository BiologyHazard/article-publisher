from typing import Any

import aiohttp

from article_publisher.converters.lark.consts import LARK_API_BASE
from article_publisher.http_client import ClientSessionWithLog


class LarkHttpClient(ClientSessionWithLog):
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
