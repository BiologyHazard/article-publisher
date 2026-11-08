from enum import Enum

from article_publisher.cache import CACHE_DIR
from article_publisher.document import Alignment

# 飞书文档图片缓存目录（发布后保留，由 `cache` 命令管理）
IMAGES_CACHE_DIR = CACHE_DIR / "lark_images"
LARK_API_BASE = "https://open.feishu.cn/open-apis"


class BlockType(Enum):
    """飞书文档块类型枚举。"""

    Page = 1
    Text = 2
    Heading1 = 3
    Heading2 = 4
    Heading3 = 5
    Heading4 = 6
    Heading5 = 7
    Heading6 = 8
    Heading7 = 9
    Heading8 = 10
    Heading9 = 11
    Bullet = 12
    Ordered = 13
    Code = 14
    Quote = 15
    Todo = 17
    Bitable = 18
    Callout = 19
    ChatCard = 20
    Diagram = 21
    Divider = 22
    File = 23
    Grid = 24
    GridColumn = 25
    Iframe = 26
    Image = 27
    Isv = 28
    Mindnote = 29
    Sheet = 30
    Table = 31
    TableCell = 32
    View = 33
    QuoteContainer = 34
    Task = 35
    Okr = 36
    OkrObjective = 37
    OkrKeyResult = 38
    OkrProgress = 39
    AddOns = 40
    JiraIssue = 41
    WikiCatalog = 42
    Board = 43
    Agenda = 44
    AgendaItem = 45
    AgendaItemTitle = 46
    AgendaItemContent = 47
    LinkPreview = 48
    SourceSynced = 49
    ReferenceSynced = 50
    SubPageList = 51
    AiTemplate = 52
    Undefined = 999

    @property
    def json_key(self) -> str:
        """获取该块类型在 JSON 中对应的字段名。"""

        return JSON_KEYS[self]


JSON_KEYS = {
    BlockType.Page: "page",
    BlockType.Text: "text",
    BlockType.Heading1: "heading1",
    BlockType.Heading2: "heading2",
    BlockType.Heading3: "heading3",
    BlockType.Heading4: "heading4",
    BlockType.Heading5: "heading5",
    BlockType.Heading6: "heading6",
    BlockType.Heading7: "heading7",
    BlockType.Heading8: "heading8",
    BlockType.Heading9: "heading9",
    BlockType.Bullet: "bullet",
    BlockType.Ordered: "ordered",
    BlockType.Code: "code",
    BlockType.Quote: "quote",
    BlockType.Todo: "todo",
    BlockType.Bitable: "bitable",
    BlockType.Callout: "callout",
    BlockType.ChatCard: "chat_card",
    BlockType.Diagram: "diagram",
    BlockType.Divider: "divider",
    BlockType.File: "file",
    BlockType.Grid: "grid",
    BlockType.GridColumn: "grid_column",
    BlockType.Iframe: "iframe",
    BlockType.Image: "image",
    BlockType.Isv: "isv",
    BlockType.Mindnote: "mindnote",
    BlockType.Sheet: "sheet",
    BlockType.Table: "table",
    BlockType.TableCell: "table_cell",
    BlockType.View: "view",
    BlockType.QuoteContainer: "quote_container",
    BlockType.Task: "task",
    BlockType.Okr: "okr",
    BlockType.OkrObjective: "okr_objective",
    BlockType.OkrKeyResult: "okr_key_result",
    BlockType.OkrProgress: "okr_progress",
    BlockType.AddOns: "add_ons",
    BlockType.JiraIssue: "jira_issue",
    BlockType.WikiCatalog: "wiki_catalog",
    BlockType.Board: "board",
    BlockType.Agenda: "agenda",
    BlockType.AgendaItem: "agenda_item",
    BlockType.AgendaItemTitle: "agenda_item_title",
    BlockType.AgendaItemContent: "agenda_item_content",
    BlockType.LinkPreview: "link_preview",
    BlockType.SourceSynced: "source_synced",
    BlockType.ReferenceSynced: "reference_synced",
    BlockType.SubPageList: "sub_page_list",
    BlockType.AiTemplate: "ai_template",
    BlockType.Undefined: "undefined",
}

HEADING_LEVELS = {
    BlockType.Heading1: 1,
    BlockType.Heading2: 2,
    BlockType.Heading3: 3,
    BlockType.Heading4: 4,
    BlockType.Heading5: 5,
    BlockType.Heading6: 6,
    BlockType.Heading7: 7,
    BlockType.Heading8: 8,
    BlockType.Heading9: 9,
}

# 飞书文字颜色索引 → 十六进制颜色
TEXT_COLOR_MAP: dict[int, str] = {
    1: "#c9272c",  # 红色
    2: "#fba518",  # 橙色
    3: "#f9d71c",  # 黄色
    4: "#3cb034",  # 绿色
    5: "#3598cd",  # 蓝色
    6: "#8e5bb5",  # 紫色
    7: "#7a7a7a",  # 灰色
    8: "#6bc3b2",  # 青色
    9: "#15848c",  # 深青
    10: "#1f8c9a",  # 靛蓝
    11: "#347ab3",  # 深蓝
    12: "#af6ba5",  # 粉紫
}
BG_COLOR_MAP: dict[int, str] = {
    1: "#fdf2f2",  # 浅红
    2: "#fef6e8",  # 浅橙
    3: "#fef9da",  # 浅黄
    4: "#eaf7e6",  # 浅绿
    5: "#e7f1f7",  # 浅蓝
    6: "#f3edf7",  # 浅紫
    7: "#f0f0f0",  # 浅灰
    8: "#ffd9e4",  # 红色背景
    9: "#e5ffeb",  # 浅薄荷
}
# 代码语言 ID → 名称
CODE_LANG_MAP: dict[int, str] = {
    0: "PlainText",
    1: "ABAP",
    2: "Ada",
    3: "Apache",
    4: "Apex",
    5: "Assembly",
    6: "Bash",
    7: "CSharp",
    8: "C++",
    9: "C",
    10: "COBOL",
    11: "CSS",
    12: "CoffeeScript",
    13: "D",
    14: "Dart",
    15: "Delphi",
    16: "Django",
    17: "Dockerfile",
    18: "Erlang",
    19: "Fortran",
    20: "FoxPro",
    21: "Go",
    22: "Groovy",
    23: "HLSL",
    24: "HTML",
    25: "Haskell",
    26: "INI",
    27: "JSON",
    28: "Java",
    29: "JavaScript",
    30: "Julia",
    31: "Kotlin",
    32: "LaTeX",
    33: "Lisp",
    34: "Logo",
    35: "Lua",
    36: "MATLAB",
    37: "Makefile",
    38: "Markdown",
    39: "Nginx",
    40: "Objective-C",
    41: "OpenEdge",
    42: "PHP",
    43: "Perl",
    44: "PowerShell",
    45: "Prolog",
    46: "Protocol Buffer",
    47: "Python",
    48: "R",
    49: "REST",
    50: "Ruby",
    51: "Rust",
    52: "SAS",
    53: "SQL",
    54: "Scala",
    55: "Scheme",
    56: "Shell",
    57: "Solidity",
    58: "Swift",
    59: "TypeScript",
    60: "VBA",
    61: "Visual Basic",
    62: "WebAssembly",
    63: "XML",
    64: "YAML",
    65: "CSharp",
}
# block_type → 对齐方式所在字段名的映射
ALIGN_KEY_MAP: dict[int, str] = {
    2: "text",
    3: "heading1",
    4: "heading2",
    5: "heading3",
    6: "heading4",
    7: "heading5",
    8: "heading6",
    9: "heading7",
    10: "heading8",
    11: "heading9",
    12: "bullet",
    13: "ordered",
}
# Lark align 值 → Alignment 枚举
LARK_TO_ALIGNMENT: dict[int, Alignment] = {
    1: Alignment.LEFT,
    2: Alignment.CENTER,
    3: Alignment.RIGHT,
}
