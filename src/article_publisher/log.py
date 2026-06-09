from __future__ import annotations

import inspect
import logging
import sys
from pathlib import Path

from loguru import logger

LOG_FORMAT_STANDARD = (
    "<green>{time:MM-DD HH:mm:ss}</> [<level>{level}</>] <level><normal>{message}</></>"
)

LOG_FORMAT_VERBOSE = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</> "
    "[<level>{level}</>] "
    "<cyan>{module}</>:<cyan>{function}</>:<cyan>{line}</> | "
    "<level><normal>{message}</></>"
)

LOG_FORMAT_VERY_VERBOSE = (
    '<dim>File <cyan>"{file.path}"</>, line <cyan>{line}</>, in <cyan>{function}</></>\n'
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</> "
    "[<level>{level}</>] "
    "<level><normal>{message}</></>"
)

CONSOLE_LOG_FORMAT = LOG_FORMAT_STANDARD
FILE_LOG_FORMAT = LOG_FORMAT_VERY_VERBOSE


if getattr(sys, "frozen", False) and (_MEIPASS := getattr(sys, "_MEIPASS", None)):
    ROOT_DIR = Path(
        _MEIPASS
    ).parent.resolve()  # frozen executable root, contains the executable file
else:
    ROOT_DIR = Path(__file__).parent.parent.parent.resolve()  # development project root


# https://loguru.readthedocs.io/en/stable/overview.html#entirely-compatible-with-standard-logging
class LoguruHandler(logging.Handler):
    """logging 与 loguru 之间的桥梁，将 logging 的日志转发到 loguru。"""

    def emit(self, record: logging.LogRecord):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        message = f"<magenta>{record.name.split('.')[0]}</> | {record.getMessage()}"
        logger.opt(colors=True, depth=depth, exception=record.exc_info).bind(
            module="uvicorn"
        ).log(level, message)


# 移除默认的 logger
logger.remove()

# 添加控制台 logger，输出到 stderr
if sys.stderr:  # 打包后可能没有 stderr
    logger.add(sys.stderr, level=0, format=CONSOLE_LOG_FORMAT, diagnose=True)

# 添加文件 logger
LOG_DIR = ROOT_DIR / "logs"
logger.add(
    LOG_DIR / "log_{time:YYYY-MM-DD}.log",
    level=0,
    format=FILE_LOG_FORMAT,
    diagnose=True,
)
