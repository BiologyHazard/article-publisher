from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DownloadMediaResult:
    """下载媒体文件的结果。"""

    buffer: bytes
    content_type: str | None
    filename: str | None
