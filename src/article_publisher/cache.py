"""
缓存目录管理。

发布过程中下载的图片等文件保存在项目根目录的 cache/ 下。
发布结束后不再自动清理，由 `article_publisher cache` 子命令统一查看和清理。
"""

import shutil
lazy from pathlib import Path

from article_publisher.log import ROOT_DIR

CACHE_DIR = ROOT_DIR / "cache"
"""缓存根目录。"""

_SIZE_UNITS = ("KB", "MB", "GB", "TB")
"""字节以上的容量单位，按 1024 进制递增。"""


def cache_size(directory: Path = CACHE_DIR) -> tuple[int, int]:
    """返回缓存目录下的 (文件数量, 总字节数)。"""
    if not directory.exists():
        return 0, 0
    files = [path for path in directory.rglob("*") if path.is_file()]
    return len(files), sum(path.stat().st_size for path in files)


def format_size(num_bytes: int) -> str:
    """将字节数格式化为易读字符串，例如 1.5 MB。"""
    size = float(num_bytes)
    unit = "B"
    for next_unit in _SIZE_UNITS:
        if size < 1024:
            break
        size /= 1024
        unit = next_unit
    precision = 0 if unit == "B" else 1
    return f"{size:.{precision}f} {unit}"


def clear_cache(directory: Path = CACHE_DIR) -> bool:
    """删除缓存目录，返回是否确实删除了内容。"""
    if not directory.exists():
        return False
    shutil.rmtree(directory)
    return True
