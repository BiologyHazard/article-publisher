"""
发布编排模块。

负责构造完整的 Opus 请求参数 (arg payload) 并调用 B站 API 保存草稿。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from bilibili_article.client import BiliClient
    from bilibili_article.converters.base import BaseConverter
    from bilibili_article.models import ArgPayload, InlineNode, Paragraph, Payload


@dataclass
class PublishConfig:
    """发布配置参数集合。

    将 publish_article 的 10+ 个可选参数封装为单一数据类，
    简化调用方签名，便于扩展。
    """

    category_id: int = 15
    article_id: int | None = None
    private_pub: int = 2
    reprint: int = 1
    original: int = 0
    comment_selected: int = 0
    up_closed_reply: int = 0
    timer_pub_time: int = 0
    list_id: int = 0
    image_urls: list[str] | None = None
    is_aigc: int = 0
    hashtag_ids: list[int] | None = None


def build_summary(paragraphs: list[Paragraph]) -> str:
    """从段落列表中提取纯文本摘要（取前 200 字）。"""
    texts: list[str] = []

    def extract(nodes: list[InlineNode]) -> None:
        for node in nodes:
            if node.get("node_type") == 1:
                texts.append(node.get("word", {}).get("words", ""))
            elif node.get("node_type") == 4:
                texts.append(node.get("link", {}).get("show_text", ""))
            elif node.get("node_type") == 5:
                texts.append(node.get("formula", {}).get("latex_content", ""))

    for p in paragraphs:
        para_type = p.get("para_type")
        if para_type in (1, 4, 5, 6, 9):
            extract(p.get("text", {}).get("nodes", []))
        elif para_type == 8:
            texts.append(p.get("code", {}).get("content", ""))

    full = "".join(texts)
    return full[:200].replace("\n", " ")


def publish_article(
    client: BiliClient,
    converter: BaseConverter,
    title: str,
    *,
    dry_run: bool = False,
    config: PublishConfig | None = None,
) -> dict[str, Any]:
    """
    将转换后的内容发布到 B站 草稿箱。

    参数:
        client:     已认证的 BiliClient 实例
        converter:  内容转换器实例
        title:      文章标题
        dry_run:    仅构建 payload 并输出到 stdout，不发送请求
        config:     发布配置参数集合（见 PublishConfig）

    返回:
        API 响应 JSON（dry_run 时返回空 dict）
    """
    if config is None:
        config = PublishConfig()

    logger.info("正在解析内容 ...")
    paragraphs = converter.convert()
    logger.info(f"解析完成，共 {len(paragraphs)} 个段落")

    summary = build_summary(paragraphs)
    logger.info(f"摘要: {summary}")

    arg: ArgPayload = {
        "type": 4,
        "template_id": 1,
        "category_id": config.category_id,
        "title": title,
        "private_pub": config.private_pub,
        "reprint": config.reprint,
        "original": config.original,
        "list_id": config.list_id,
        "comment_selected": config.comment_selected,
        "up_closed_reply": config.up_closed_reply,
        "timer_pub_time": config.timer_pub_time,
        "only_fans_level": 0,
        "only_fans_dnd": 0,
        "summary": summary,
        "opus": {
            "opus_source": 2,
            "title": title,
            "content": {
                "paragraphs": paragraphs,
            },
            "pub_info": {
                "editor_version": "eva3-3.0.0",
            },
            "attachments": {
                "is_aigc": config.is_aigc,
            },
        },
    }
    if config.article_id is not None:
        arg["article_id"] = config.article_id
    if config.image_urls:
        arg["image_urls"] = config.image_urls
    if config.hashtag_ids:
        arg["hashtag_ids"] = config.hashtag_ids

    payload: Payload = {"arg": arg}

    # 输出 payload 到 stdout
    logger.info("Payload: ")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if dry_run:
        return {}

    logger.info("正在保存到草稿箱 ...")
    result = client.save_draft(payload)
    aid = result["data"]["article_id"]
    logger.info(f"✅ 成功！草稿 ID: {aid}")
    logger.info(
        f"可在创作中心查看: https://member.bilibili.com/platform/upload/text/new-edit?aid={aid}"
    )
    return result
