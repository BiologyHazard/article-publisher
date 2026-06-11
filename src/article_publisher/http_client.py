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
    from aiohttp.typedefs import StrOrURL


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
        new_headers = CIMultiDict()
        content_disposition = payload._headers.popall(CONTENT_DISPOSITION, None)
        # 先插入 Content-Disposition → 排在最前
        if content_disposition is not None:
            new_headers.extend((CONTENT_DISPOSITION, v) for v in content_disposition)
        # 再插入其他 headers（如 Content-Type） → 排在后面
        new_headers.extend(payload._headers.items())
        payload._headers = new_headers
    return writer


class ClientSessionWithLog(aiohttp.ClientSession):
    """
    自动记录请求与响应 debug 日志的 :class:`aiohttp.ClientSession` 子类。

    覆盖 :meth:`aiohttp.ClientSession._request`，在发送请求前和收到响应后
    分别调用 ``_log_request`` 和 ``_log_response`` 输出 debug 日志，
    帮助开发者在不改动业务代码的情况下追踪 HTTP 交互细节。

    日志输出格式（通过 ``_log_tag`` 控制前缀标签）::

        [HTTP REQ] POST https://example.com/api
        [HTTP REQ] json: {"key": "value"}
        [HTTP RSP] HTTP 200 https://example.com/api
        [HTTP RSP] headers: {...}
        [HTTP RSP] body: {"result": "ok"}

    各平台客户端可继承此类并覆写 :meth:`_log_tag` 来区分日志来源，例如::

        class BiliBiliClient(ClientSessionWithLog):
            def _log_tag(self) -> str:
                return "Bilibili"
    """

    if TYPE_CHECKING:
        # aiohttp.ClientSession 定义了 __aenter__ 和 __aexit__，但标注的返回类型为 ClientSession，
        # 这里重新标注为 Self，以便在子类中使用 async with 时正确推断类型。
        async def __aenter__(self) -> Self:
            return self

    async def _request(
        self, method: str, str_or_url: StrOrURL, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """发送 HTTP 请求，自动记录请求与响应的 debug 日志。"""

        await self._log_request(method, str_or_url, **kwargs)
        response = await super()._request(method, str_or_url, **kwargs)
        await self._log_response(response)

        return response

    def _log_tag(self) -> str:
        """返回日志前缀标签，子类可覆盖以区分平台。"""

        return "HTTP"

    async def _log_request(self, method: str, url: StrOrURL, **kwargs: Any) -> None:
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
