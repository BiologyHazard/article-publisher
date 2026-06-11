from article_publisher.document import Alignment
from article_publisher.log import ROOT_DIR as _PROJECT_ROOT

# 临时图片目录（项目根目录内，用完清除）
TEMP_IMAGES_DIR = _PROJECT_ROOT / "temp" / "lark_images"
LARK_API_BASE = "https://open.feishu.cn/open-apis"

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
