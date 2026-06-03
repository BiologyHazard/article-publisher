"""
发布编排模块。

负责构造完整的 Opus 请求参数 (arg payload) 并调用 B站 API 保存草稿。
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bilibili_article.client import BiliClient
    from bilibili_article.converters.base import BaseConverter
    from bilibili_article.models import ArgPayload, InlineNode, Paragraph


def build_summary(paragraphs: list[Paragraph]) -> str:  # type: ignore[misc]
    """从段落列表中提取纯文本摘要（取前 200 字）。"""
    texts: list[str] = []

    def extract(nodes: list[InlineNode]) -> None:  # type: ignore[misc]
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
    category_id: int = 15,
    article_id: int | None = None,
    private_pub: int = 2,
    reprint: int = 1,
    original: int = 0,
    comment_selected: int = 0,
    up_closed_reply: int = 0,
    payload_path: str | None = None,
) -> dict:
    """
    将转换后的内容发布到 B站 草稿箱。

    参数:
        client:          已认证的 BiliClient 实例
        converter:       内容转换器实例
        title:           文章标题
        category_id:     分区 ID (15=生活, 4=游戏...)
        article_id:      已有草稿 ID（None 表示新建）
        private_pub:     可见性 (2=公开, 1=仅自己可见)
        reprint:         转载设置 (1=禁止转载)
        original:        原创声明 (0=不声明, 1=声明原创)
        comment_selected:精选评论 (0=关闭, 1=开启)
        up_closed_reply: 关闭评论 (0=允许评论, 1=关闭评论)
        payload_path:    payload 导出路径（None 表示不导出）

    返回:
        API 响应 JSON
    """
    print("  正在解析内容 ...")
    paragraphs = converter.convert()
    print(f"  解析完成，共 {len(paragraphs)} 个段落")

    summary = build_summary(paragraphs)
    print(f"  摘要: {summary[:60]}...")

    arg: ArgPayload = {  # type: ignore[valid-type,misc]
        "type": 4,
        "template_id": 1,
        "category_id": category_id,
        "title": title,
        "private_pub": private_pub,
        "reprint": reprint,
        "original": original,
        "list_id": 0,
        "comment_selected": comment_selected,
        "up_closed_reply": up_closed_reply,
        "timer_pub_time": 0,
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
                "is_aigc": 0,
            },
        },
    }
    if article_id is not None:
        arg["article_id"] = article_id

    # 导出 payload（调试用）
    if payload_path:
        os.makedirs(os.path.dirname(payload_path) or ".", exist_ok=True)
        with open(payload_path, "w", encoding="utf-8") as f:
            json.dump({"arg": arg}, f, ensure_ascii=False, indent=2)
        print(f"  payload 已导出: {payload_path}")

    print("  正在保存到草稿箱 ...")
    result = client.save_draft(arg)
    aid = result["data"]["article_id"]
    print(f"  ✔ 成功！草稿 ID: {aid}")
    return result
