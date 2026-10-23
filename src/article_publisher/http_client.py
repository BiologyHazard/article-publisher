"""
异步 HTTP 客户端基类。

封装 aiohttp ClientSession，提供统一的 ``request`` 方法，
自动记录请求和响应的 debug 日志（参考 NGA 客户端的日志模式）。
"""

from typing import Any, Self

import aiohttp
lazy from aiohttp.typedefs import StrOrURL

from article_publisher.log import logger


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

    async def __aenter__(self) -> Self:
        await super().__aenter__()
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
                # 避免将整个 multipart body 序列化到内存中仅用于日志记录。
                # 改用结构化的摘要信息（字段名、文件名），减少额外开销。
                try:
                    parts_info: list[dict[str, Any]] = []
                    parts = getattr(data, "_parts", None) or []
                    for idx, part in enumerate(parts, start=1):
                        headers = getattr(part, "headers", {}) or {}
                        disposition = headers.get(aiohttp.hdrs.CONTENT_DISPOSITION, "")
                        field_name: str | None = None
                        filename: str | None = None
                        if disposition:
                            for item in disposition.split(";"):
                                item = item.strip()
                                if item.startswith("name="):
                                    field_name = item.split("=", 1)[1].strip('"')
                                elif item.startswith("filename="):
                                    filename = item.split("=", 1)[1].strip('"')
                        parts_info.append(
                            {
                                "index": idx,
                                "name": field_name,
                                "filename": filename,
                                "content_type": headers.get(aiohttp.hdrs.CONTENT_TYPE),
                            }
                        )
                    logger.debug(
                        f"[{tag} REQ] multipart body: "
                        f"{len(parts_info)} part(s): {parts_info}"
                    )
                except Exception:
                    logger.debug(
                        f"[{tag} REQ] multipart body: "
                        f"<{len(getattr(data, '_parts', []))} parts>"
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
