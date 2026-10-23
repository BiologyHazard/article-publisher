from typing import NotRequired, TypedDict

from .common import LarkApiResponse

# 文本元素 / 样式 (TextElement & TextStyle)


class Link(TypedDict):
    url: str


class TextElementStyle(TypedDict):
    bold: NotRequired[bool]
    italic: NotRequired[bool]
    strikethrough: NotRequired[bool]
    underline: NotRequired[bool]
    inline_code: NotRequired[bool]
    text_color: NotRequired[int]
    background_color: NotRequired[int]
    link: NotRequired[Link]
    comment_ids: NotRequired[list[str]]


class TextRun(TypedDict):
    content: str
    text_element_style: NotRequired[TextElementStyle]


class MentionUser(TypedDict):
    user_id: str
    text_element_style: NotRequired[TextElementStyle]


class MentionDoc(TypedDict):
    token: str
    obj_type: int
    url: str
    text_element_style: NotRequired[TextElementStyle]


class Reminder(TypedDict):
    create_user_id: str
    is_notify: NotRequired[bool]
    is_whole_day: NotRequired[bool]
    expire_time: int
    notify_time: int
    text_element_style: NotRequired[TextElementStyle]


class InlineFile(TypedDict):
    file_token: str
    source_block_id: str
    text_element_style: NotRequired[TextElementStyle]


class InlineBlock(TypedDict):
    block_id: str
    text_element_style: NotRequired[TextElementStyle]


class Equation(TypedDict):
    content: str
    text_element_style: NotRequired[TextElementStyle]


class UndefinedElement(TypedDict):
    pass


class TextElement(TypedDict):
    text_run: NotRequired[TextRun]
    mention_user: NotRequired[MentionUser]
    mention_doc: NotRequired[MentionDoc]
    reminder: NotRequired[Reminder]
    file: NotRequired[InlineFile]
    inline_block: NotRequired[InlineBlock]
    equation: NotRequired[Equation]
    undefined_element: NotRequired[UndefinedElement]


class TextStyle(TypedDict):
    align: NotRequired[int]
    done: NotRequired[bool]
    folded: NotRequired[bool]
    language: NotRequired[int]
    wrap: NotRequired[bool]
    background_color: NotRequired[str]
    indentation_level: NotRequired[str]
    sequence: NotRequired[str]


class Text(TypedDict):
    style: NotRequired[TextStyle]
    elements: list[TextElement]


# 各类块的内容实体 (BlockData)


class Callout(TypedDict):
    background_color: NotRequired[int]
    border_color: NotRequired[int]
    text_color: NotRequired[int]
    emoji_id: NotRequired[str]


class Divider(TypedDict):
    pass


class ImageCaption(TypedDict):
    content: NotRequired[str]


class Image(TypedDict):
    token: NotRequired[str]
    width: NotRequired[int]
    height: NotRequired[int]
    align: NotRequired[int]
    caption: NotRequired[ImageCaption]
    scale: NotRequired[float]


class Code(TypedDict):
    elements: list[TextElement]
    style: NotRequired[TextStyle]


class Grid(TypedDict):
    column_size: int


class GridColumn(TypedDict):
    width_ratio: NotRequired[int]


class QuoteContainer(TypedDict):
    pass


class TableMergeInfo(TypedDict):
    row_span: NotRequired[int]
    col_span: NotRequired[int]


class TableProperty(TypedDict):
    row_size: int
    column_size: int
    column_width: NotRequired[list[int]]
    header_row: NotRequired[bool]
    header_column: NotRequired[bool]
    merge_info: NotRequired[list[TableMergeInfo]]


class Table(TypedDict):
    cells: list[str]
    property: TableProperty


class TableCell(TypedDict):
    pass


class Sheet(TypedDict):
    token: NotRequired[str]
    row_size: NotRequired[int]
    column_size: NotRequired[int]


class Bitable(TypedDict):
    token: str
    view_type: int


class File(TypedDict):
    token: NotRequired[str]
    name: NotRequired[str]
    view_type: NotRequired[int]


class View(TypedDict):
    view_type: NotRequired[int]


class ChatCard(TypedDict):
    chat_id: str
    align: NotRequired[int]


class Board(TypedDict):
    token: NotRequired[str]
    align: NotRequired[int]
    width: NotRequired[int]
    height: NotRequired[int]


class Diagram(TypedDict):
    diagram_type: NotRequired[int]


class IframeComponent(TypedDict):
    type: int
    url: str


class Iframe(TypedDict):
    component: IframeComponent


class Mindnote(TypedDict):
    token: str


class Task(TypedDict):
    task_id: str


class OKRObjective(TypedDict):
    objective_id: str
    kr_ids: NotRequired[list[str]]


class VisibleSetting(TypedDict):
    progress_fill_area_visible: NotRequired[bool]
    progress_status_visible: NotRequired[bool]
    score_visible: NotRequired[bool]


class OKR(TypedDict):
    okr_id: str
    objectives: NotRequired[list[OKRObjective]]
    # 获取时的额外字段
    period_display_status: NotRequired[str]
    period_name_zh: NotRequired[str]
    period_name_en: NotRequired[str]
    user_id: NotRequired[str]
    visible_setting: NotRequired[VisibleSetting]


class ProgressRate(TypedDict):
    mode: NotRequired[str]
    current: NotRequired[float]
    percent: NotRequired[float]
    progress_status: NotRequired[str]
    status_type: NotRequired[str]
    start: NotRequired[float]
    target: NotRequired[float]


class OkrObjective(TypedDict):
    objective_id: NotRequired[str]
    confidential: NotRequired[bool]
    position: NotRequired[int]
    score: NotRequired[int]
    visible: NotRequired[bool]
    weight: NotRequired[float]
    progress_rate: NotRequired[ProgressRate]
    content: NotRequired[Text]


class OkrKeyResult(TypedDict):
    kr_id: NotRequired[str]
    confidential: NotRequired[bool]
    position: NotRequired[int]
    score: NotRequired[int]
    visible: NotRequired[bool]
    weight: NotRequired[float]
    progress_rate: NotRequired[ProgressRate]
    content: NotRequired[Text]


class Progress(TypedDict):
    pass


class AddOns(TypedDict):
    component_id: NotRequired[str]
    component_type_id: NotRequired[str]
    record: NotRequired[str]


class ISV(TypedDict):
    component_id: NotRequired[str]
    component_type_id: NotRequired[str]


class JiraIssue(TypedDict):
    id: NotRequired[str]
    key: NotRequired[str]


class LinkPreview(TypedDict):
    url: str
    url_type: str


class ReferenceSynced(TypedDict):
    source_block_id: NotRequired[str]
    source_document_id: NotRequired[str]


class SourceSynced(TypedDict):
    elements: NotRequired[list[TextElement]]
    align: NotRequired[int]


class SubPageList(TypedDict):
    wiki_token: NotRequired[str]


class WikiCatalog(TypedDict):
    wiki_token: NotRequired[str]


class Agenda(TypedDict):
    pass


class AgendaItem(TypedDict):
    pass


class AgendaTitleElement(TypedDict):
    text_run: NotRequired[TextRun]
    mention_user: NotRequired[MentionUser]
    mention_doc: NotRequired[MentionDoc]
    reminder: NotRequired[Reminder]
    file: NotRequired[InlineFile]
    inline_block: NotRequired[InlineBlock]
    equation: NotRequired[Equation]
    undefined_element: NotRequired[UndefinedElement]


class AgendaItemTitle(TypedDict):
    align: NotRequired[int]
    elements: list[AgendaTitleElement]


class AgendaItemContent(TypedDict):
    pass


class AITemplate(TypedDict):
    pass


class Undefined(TypedDict):
    pass


# 块 (Block)


class Block(TypedDict):
    """单个块的完整数据结构。

    基于 block_type 的值，对应的内容实体字段会出现且仅出现一个。
    """

    block_id: str
    block_type: int
    parent_id: NotRequired[str]
    children: NotRequired[list[str]]
    comment_ids: NotRequired[list[str]]

    # 以下字段根据 block_type 出现一个
    page: NotRequired[Text]
    text: NotRequired[Text]
    heading1: NotRequired[Text]
    heading2: NotRequired[Text]
    heading3: NotRequired[Text]
    heading4: NotRequired[Text]
    heading5: NotRequired[Text]
    heading6: NotRequired[Text]
    heading7: NotRequired[Text]
    heading8: NotRequired[Text]
    heading9: NotRequired[Text]
    bullet: NotRequired[Text]
    ordered: NotRequired[Text]
    code: NotRequired[Code]
    quote: NotRequired[Text]
    todo: NotRequired[Text]
    bitable: NotRequired[Bitable]
    callout: NotRequired[Callout]
    chat_card: NotRequired[ChatCard]
    diagram: NotRequired[Diagram]
    divider: NotRequired[Divider]
    file: NotRequired[File]
    grid: NotRequired[Grid]
    grid_column: NotRequired[GridColumn]
    iframe: NotRequired[Iframe]
    image: NotRequired[Image]
    isv: NotRequired[ISV]
    mindnote: NotRequired[Mindnote]
    sheet: NotRequired[Sheet]
    table: NotRequired[Table]
    table_cell: NotRequired[TableCell]
    view: NotRequired[View]
    quote_container: NotRequired[QuoteContainer]
    task: NotRequired[Task]
    okr: NotRequired[OKR]
    okr_objective: NotRequired[OkrObjective]
    okr_key_result: NotRequired[OkrKeyResult]
    okr_progress: NotRequired[Progress]
    add_ons: NotRequired[AddOns]
    jira_issue: NotRequired[JiraIssue]
    wiki_catalog: NotRequired[WikiCatalog]
    board: NotRequired[Board]
    agenda: NotRequired[Agenda]
    agenda_item: NotRequired[AgendaItem]
    agenda_item_title: NotRequired[AgendaItemTitle]
    agenda_item_content: NotRequired[AgendaItemContent]
    link_preview: NotRequired[LinkPreview]
    source_synced: NotRequired[SourceSynced]
    reference_synced: NotRequired[ReferenceSynced]
    sub_page_list: NotRequired[SubPageList]
    ai_template: NotRequired[AITemplate]
    undefined: NotRequired[Undefined]


class ListDocumentBlockData(TypedDict):
    items: list[Block]
    page_token: NotRequired[str]
    has_more: bool


type ListDocumentBlockResponse = LarkApiResponse[ListDocumentBlockData]
