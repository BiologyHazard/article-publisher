from __future__ import annotations

from typing import NotRequired, TypedDict

from .common import LarkApiResponse


class Cover(TypedDict):
    token: str
    offset_ratio_x: float
    offset_ratio_y: float


class DisplaySetting(TypedDict):
    show_authors: NotRequired[bool]
    show_create_time: NotRequired[bool]
    show_pv: NotRequired[bool]
    show_uv: NotRequired[bool]
    show_like_count: NotRequired[bool]
    show_comment_count: NotRequired[bool]
    show_related_matters: NotRequired[bool]


class Document(TypedDict):
    document_id: str
    revision_id: int
    title: str
    cover: NotRequired[Cover]
    display_setting: NotRequired[DisplaySetting]


class GetDocumentData(TypedDict):
    document: Document


type GetDocumentResponse = LarkApiResponse[GetDocumentData]
