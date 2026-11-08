from typing import Any

lazy import aiohttp

from article_publisher.http_client import ClientSessionWithLog
lazy from article_publisher.converters.lark.models.block import (
    Block,
    ListDocumentBlockResponse,
)

from .consts import LARK_API_BASE
from .models.download_media import DownloadMediaResult
lazy from .models import (
    GetDocumentData,
    GetDocumentResponse,
    InternalTenantAccessTokenRequest,
    InternalTenantAccessTokenResponse,
)


class LarkClient(ClientSessionWithLog):
    """飞书 API 的异步 HTTP 客户端（自动管理 tenant_access_token）。"""

    def __init__(self, app_id: str, app_secret: str):
        self._app_id = app_id
        self._app_secret = app_secret
        self._tenant_token: str | None = None
        super().__init__()

    def _log_tag(self) -> str:
        return "LARK"

    async def _ensure_token(self) -> str:
        if self._tenant_token:
            return self._tenant_token

        request: InternalTenantAccessTokenRequest = {
            "app_id": self._app_id,
            "app_secret": self._app_secret,
        }
        resp = await self.request(
            "POST",
            f"{LARK_API_BASE}/auth/v3/tenant_access_token/internal",
            json=request,
        )
        data: InternalTenantAccessTokenResponse = await resp.json()
        if data["code"] != 0:
            raise RuntimeError(f"飞书认证失败: [{data['code']}] {data['msg']}")

        self._tenant_token = data["tenant_access_token"]
        # _ensure_token 后需设置 Authorization 头部供后续请求使用
        # 使用公开 API headers 修改默认头部
        self.headers["Authorization"] = f"Bearer {self._tenant_token}"
        return self._tenant_token

    async def _request_with_auth(
        self, method: str, path: str, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """发送已携带 tenant_access_token 的 HTTP 请求。"""
        await self._ensure_token()
        return await self.request(method, f"{LARK_API_BASE}{path}", **kwargs)

    async def get_json(self, path: str, **kwargs: Any) -> Any:
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

    async def get_document(self, document_id: str) -> GetDocumentData:
        """获取文档基本信息"""

        obj: GetDocumentResponse = await self.get_json(
            f"/docx/v1/documents/{document_id}"
        )
        return obj["data"]

    async def download_media(self, token: str) -> DownloadMediaResult:
        """调用飞书下载媒体 API。"""

        response = await self._request_with_auth(
            "GET", f"/drive/v1/medias/{token}/download"
        )
        if response.status != 200:
            raise RuntimeError(f"飞书媒体下载失败: HTTP {response.status}")

        content_type = response.content_type
        content_disposition = response.content_disposition
        filename = None
        if content_disposition:
            filename = content_disposition.filename
        buffer = await response.read()
        return DownloadMediaResult(
            buffer=buffer, content_type=content_type, filename=filename
        )

    async def list_document_block(self, document_id: str) -> list[Block]:
        """分页加载所有块"""

        items: list[Block] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": 500, "document_revision_id": -1}
            if page_token is not None:
                params["page_token"] = page_token
            obj: ListDocumentBlockResponse = await self.get_json(
                f"/docx/v1/documents/{document_id}/blocks", params=params
            )
            items.extend(obj["data"]["items"])
            if not obj["data"]["has_more"]:
                break
            page_token = obj["data"].get("page_token")

        return items
