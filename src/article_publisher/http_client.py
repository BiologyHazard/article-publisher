"""
异步 HTTP 客户端基类。

封装 aiohttp ClientSession，提供统一的 ``request`` 方法，
自动记录请求和响应的 debug 日志（参考 NGA 客户端的日志模式）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

import aiohttp
from aiohttp.hdrs import CONTENT_DISPOSITION
from multidict import CIMultiDict

from article_publisher.log import logger

if TYPE_CHECKING:
    from collections.abc import Mapping


def gen_oss_compatible_formdata(form_data: aiohttp.FormData) -> aiohttp.MultipartWriter:
    """
    生成兼容 OSS 的 FormData，重排 multipart 部分的 headers。

    OSS 要求 multipart/form-data 中每个 part 的 Content-Disposition 必须在第一位，
    aiohttp 默认生成的 multipart 顺序未定义，可能导致 OSS 无法正确解析。
    该函数通过访问 MultipartWriter 内部结构重排 headers 来兼容 OSS。

    参考文档：https://api.aliyun.com/troubleshoot?q=0006-00000109
    """
    writer = form_data._gen_form_data()
    for payload, _encoding, _te_encoding in writer._parts:
        new_header = CIMultiDict()
        content_disposition = payload._headers.popall(CONTENT_DISPOSITION, None)
        # 先插入 Content-Disposition → 排在最前
        if content_disposition is not None:
            new_header.extend((CONTENT_DISPOSITION, v) for v in content_disposition)
        # 再插入其他 headers（如 Content-Type） → 排在后面
        new_header.extend(payload._headers.items())
        payload._headers = new_header
    return writer


class BaseHttpClient:
    """异步 HTTP 客户端基类。

    用法示例::

        class MyClient(BaseHttpClient):
            def __init__(self, token: str) -> None:
                super().__init__(headers={"Authorization": f"Bearer {token}"})

            async def get_data(self) -> dict[str, Any]:
                resp = await self.request("GET", "https://api.example.com/data")
                return await resp.json()
    """

    def __init__(
        self,
        headers: Mapping[str, str] | None = None,
        cookies: Mapping[str, str] | None = None,
    ) -> None:
        self._session = aiohttp.ClientSession(headers=headers, cookies=cookies)

    async def close(self) -> None:
        """关闭底层 aiohttp 会话。"""
        await self._session.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def request(
        self, method: str, url: str, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """发送 HTTP 请求，自动记录请求与响应的 debug 日志。

        返回的 :class:`aiohttp.ClientResponse` 对象可继续调用
        ``.json()`` / ``.text()`` 等方法读取响应体（body 已被预读缓存）。

        调用方建议用法::

            resp = await client.request("POST", url, json=payload)
            result = await resp.json()
        """
        await self._log_request(method, url, **kwargs)
        response = await self._session.request(method, url, **kwargs)

        # 预读响应体以记录日志；aiohttp 会缓存 body，
        # 后续 .json() / .text() 可复用缓存
        await self._log_response(response)

        return response

    def _log_tag(self) -> str:
        """返回日志前缀标签，子类可覆盖以区分平台。"""
        return "HTTP"

    async def _log_request(self, method: str, url: str, **kwargs: Any) -> None:
        """debug 日志：打印请求的完整信息。"""
        tag = self._log_tag()
        logger.debug(f"[{tag} REQ] {method} {url}")

        if kwargs.get("params"):
            logger.debug(f"[{tag} REQ] params: {kwargs['params']}")

        if "json" in kwargs:
            logger.debug(f"[{tag} REQ] json: {kwargs['json']}")

        if kwargs.get("data"):
            data = kwargs["data"]
            if isinstance(data, aiohttp.MultipartWriter):
                logger.debug(
                    f"[{tag} REQ] body: {(await data.as_bytes()).decode('utf-8', errors='replace')}"
                )
            elif isinstance(data, bytes):
                try:
                    logger.debug(f"[{tag} REQ] body (bytes): {data[:2000]}")
                except Exception:
                    logger.debug(f"[{tag} REQ] body (bytes): <{len(data)} bytes>")
            else:
                logger.debug(f"[{tag} REQ] body: {data}")

        if kwargs.get("headers"):
            # 只打印关键头部，不打印完整的 Cookie / Authorization
            safe_headers = {
                k: v
                for k, v in kwargs["headers"].items()
                if k.lower() not in ("cookie", "authorization")
            }
            logger.debug(f"[{tag} REQ] headers: {safe_headers}")

    async def _log_response(self, response: aiohttp.ClientResponse) -> None:
        """debug 日志：打印响应的完整信息。"""
        tag = self._log_tag()
        logger.debug(f"[{tag} RSP] HTTP {response.status} {response.url}")
        logger.debug(f"[{tag} RSP] headers: {dict(response.headers)}")

        try:
            text = await response.text()
        except UnicodeDecodeError:
            logger.debug(f"[{tag} RSP] body: <binary: {response.content_length} bytes>")
            return

        if len(text) > 16384:
            logger.debug(
                f"[{tag} RSP] body ({len(text)} chars, truncated): {text[:16384]}..."
            )
        else:
            logger.debug(f"[{tag} RSP] body: {text}")
