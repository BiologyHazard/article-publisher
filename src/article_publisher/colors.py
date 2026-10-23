"""平台字体调色板与最近色匹配（sRGB → Oklab 欧氏距离）。

只在发布边界转换颜色，保留文档模型中的来源颜色。空值或非法颜色不
强制指定颜色，以便平台使用默认文字色；距离相同时按调色板顺序选择。
"""

import re
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class TextColor:
    """浅色模式匹配色及平台输出值。"""

    color: str
    value: str
    dark_color: str = ""
    bili_theme: str = ""


SKLAND_TEXT_COLORS = tuple(
    TextColor(color, color)
    for color in ("#222222", "#90C208", "#46AAFA", "#FA6E5A", "#FAB446", "#826EFF")
)

BILIBILI_TEXT_COLORS = tuple(
    TextColor(color, color, dark_color, theme)
    for color, dark_color, theme in (
        ("#2f3238", "#D0D3D7", "Ga9"),
        ("#61666d", "#A2A7AE", "Ga7"),
        ("#9499a0", "#757A81", "Ga5"),
        ("#c9ccd0", "#46494D", "Ga3"),
        ("#89e1e1", "#085B5C", "Cy3"),
        ("#95e4af", "#175C34", "Gr3"),
        ("#ffdb93", "#7C4C08", "Ye3"),
        ("#ffb68c", "#7D2F0E", "Or3"),
        ("#fcafaa", "#742728", "Re3"),
        ("#d8b6ff", "#4E317D", "Pu3"),
        ("#88a4ff", "#3B53A8", "Bl4"),
        ("#4fd3d1", "#028080", "Cy4"),
        ("#2ac864", "#1FA251", "Gr5"),
        ("#ffcc00", "#CCA000", "Ly5"),
        ("#ff661a", "#E1540D", "Or5"),
        ("#f85a54", "#D1403E", "Re5"),
        ("#ac6dff", "#8C50E0", "Pu5"),
        ("#6188ff", "#4B6BD4", "Bl5"),
        ("#018488", "#5AC2C0", "Cy7"),
        ("#089043", "#6DC28D", "Gr7"),
        ("#aa7d00", "#DEC158", "Ly7"),
        ("#bb3800", "#EB8F61", "Or7"),
        ("#c9272c", "#E18281", "Re7"),
        ("#723ecc", "#B48DEB", "Pu7"),
        ("#3752c8", "#899EE3", "Bl7"),
    )
)

# 按用户提供的 NGA 颜色选择器截图逐行取色；不能用 CSS 同名颜色替代。
NGA_TEXT_COLORS = tuple(
    TextColor(color, name)
    for name, color in (
        ("skyblue", "#87CEEB"),
        ("royalblue", "#4169E1"),
        ("blue", "#0066BB"),
        ("darkblue", "#00008B"),
        ("orange", "#A06700"),
        ("orangered", "#FF4500"),
        ("crimson", "#DC143C"),
        ("red", "#DD0000"),
        ("firebrick", "#B22222"),
        ("darkred", "#8B0000"),
        ("green", "#3D9F0E"),
        ("limegreen", "#32CD32"),
        ("seagreen", "#2E8B57"),
        ("teal", "#008080"),
        ("deeppink", "#FF1493"),
        ("tomato", "#FF6347"),
        ("coral", "#FF7F50"),
        ("purple", "#800080"),
        ("indigo", "#4B0082"),
        ("burlywood", "#DEB887"),
        ("sandybrown", "#F4A460"),
        ("sienna", "#A0522D"),
        ("chocolate", "#D2691E"),
        ("silver", "#888888"),
    )
)


@lru_cache(maxsize=1024)
def _hex_to_oklab(color: str) -> tuple[float, float, float]:
    """将标准 #rrggbb sRGB 转换为 Oklab（D65 白点）。"""
    rgb = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    l_root = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_root = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_root = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (
        0.2104542553 * l_root + 0.7936177850 * m_root - 0.0040720468 * s_root,
        1.9779984951 * l_root - 2.4285922050 * m_root + 0.4505937099 * s_root,
        0.0259040371 * l_root + 0.7827717662 * m_root - 0.8086757660 * s_root,
    )


@lru_cache(maxsize=1024)
def nearest_text_color(source: str, palette: tuple[TextColor, ...]) -> TextColor | None:
    """匹配 #RGB / #RRGGBB 或调色板输出名；非法输入返回 None。

    匹配使用浅色模式的 color，深色值与主题标识仅随选中的颜色输出。
    """
    source = source.strip().lower()
    if not source or not palette:
        return None
    for entry in palette:
        if source in (entry.color.lower(), entry.value.lower()):
            return entry
    if not re.fullmatch(r"#(?:[0-9a-f]{3}|[0-9a-f]{6})", source):
        return None
    if len(source) == 4:
        source = "#" + "".join(c * 2 for c in source[1:])
    lab = _hex_to_oklab(source)
    return min(
        palette,
        key=lambda entry: sum(
            (a - b) ** 2 for a, b in zip(lab, _hex_to_oklab(entry.color), strict=True)
        ),
    )
