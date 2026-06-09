"""NGA 平台模块。"""

from article_publisher.platforms.nga.client import NgaClient
from article_publisher.platforms.nga.publisher import NgaPublishConfig, NgaPublisher

__all__ = ["NgaClient", "NgaPublishConfig", "NgaPublisher"]
