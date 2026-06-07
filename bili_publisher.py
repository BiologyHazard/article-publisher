"""
B站 Opus (新版专栏) 自动化发布/保存草稿工具
===========================================

将本地 Markdown 文章（包含图片）自动上传到 B站 创作中心的草稿箱。

用法:
    1. 从浏览器获取 Cookie（SESSDATA, bili_jct, buvid3）
    2. 在 .env 文件中配置，或设置环境变量
    3. python bili_publisher.py articles/article1

文章目录结构:
    articles/
        article1/
            main.md       # Markdown 内容
            images/        # 图片文件夹
                xxx.png
                yyy.jpg

支持的 Markdown 语法:
    - # 一级标题      → B站 H1 标题
    - ## 二级标题     → B站 H2 标题
    - ### 三级标题    → B站 加粗正文（带特殊样式）
    - **粗体**       → 加粗
    - *斜体*         → 斜体
    - ~~删除线~~     → 删除线
    - `行内代码`     → 等宽字体样式
    - ---            → 分隔线
    - ![alt](path)   → 图片（自动上传到 B站 图床）
    - 普通文本段落    → B站正文
"""

import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path

import requests
from dotenv import find_dotenv, load_dotenv
from PIL import Image

# =============================================================================
# WBI 签名工具
# =============================================================================

MIXIN_KEY_TABLE = [
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
]


def get_mixin_key(raw: str) -> str:
    """对原始 key 字符串做重排，取前 32 位作为 mixin_key"""
    return "".join(raw[i] for i in MIXIN_KEY_TABLE)[:32]


def fetch_wbi_keys(session: requests.Session) -> tuple[str, str]:
    """从 /x/web-interface/nav 获取 WBI 的 img_key 和 sub_key"""
    resp = session.get("https://api.bilibili.com/x/web-interface/nav").json()
    wbi_img = resp["data"]["wbi_img"]
    img_key = wbi_img["img_url"].split("/")[-1].split(".")[0]
    sub_key = wbi_img["sub_url"].split("/")[-1].split(".")[0]
    return img_key, sub_key


def sign_wbi_params(params: dict, mixin_key: str) -> dict:
    """为参数字典添加 wts 和 w_rid 签名，返回新字典"""
    out = dict(params)
    out["wts"] = int(time.time())
    sorted_items = sorted(out.items())
    query = urllib.parse.urlencode({k: v for k, v in sorted_items if v is not None})
    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
    out["w_rid"] = w_rid
    return out


# =============================================================================
# B站 API 封装
# =============================================================================

BILI_API_BASE = "https://api.bilibili.com"


class BiliApiError(Exception):
    """B站 API 返回非 0 code 时抛出的异常"""

    def __init__(self, code: int, message: str, raw: object = None):
        self.code = code
        self.message = message
        self.raw = raw
        super().__init__(f"[{code}] {message}")


class BiliClient:
    """封装与 B站 后端交互的通用 HTTP 客户端"""

    def __init__(self, sessdata: str, bili_jct: str, buvid3: str):
        self.csrf = bili_jct
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                "Referer": "https://member.bilibili.com/platform/upload/text/new-edit",
                "Origin": "https://member.bilibili.com",
            }
        )
        self.session.cookies.set("SESSDATA", sessdata, domain=".bilibili.com")
        self.session.cookies.set("bili_jct", bili_jct, domain=".bilibili.com")
        self.session.cookies.set("buvid3", buvid3, domain=".bilibili.com")
        self._mixin_key: str | None = None

    # ------------------------------------------------------------------
    # WBI 签名
    # ------------------------------------------------------------------

    def _ensure_mixin_key(self) -> str:
        """如果还没有 mixin_key，则从 nav 接口获取，返回 mixin_key"""
        if self._mixin_key is None:
            img_key, sub_key = fetch_wbi_keys(self.session)
            self._mixin_key = get_mixin_key(img_key + sub_key)
        return self._mixin_key

    def sign(self, params: dict) -> dict:
        """为参数字典附加 WBI 签名"""
        mixin_key = self._ensure_mixin_key()
        return sign_wbi_params(params, mixin_key)

    # ------------------------------------------------------------------
    # 图片上传
    # ------------------------------------------------------------------

    def upload_image(self, file_path: Path) -> dict:
        """
        将本地图片上传到 B站 图床（优先使用 Opus 编辑器专用接口），返回:
            {"url": str, "width": int, "height": int}
        """
        try:
            return self._upload_image_bfs(file_path)
        except BiliApiError as e:
            print(f"    upload_bfs 上传失败 ({e.message})，尝试 upcover 接口...")
            return self._upload_image_fallback(file_path)

    def _upload_image_bfs(self, file_path: Path) -> dict:
        """使用 Opus 编辑器专用接口上传图片（需要 WBI 签名）"""
        url = f"{BILI_API_BASE}/x/dynamic/feed/draw/upload_bfs"
        params = self.sign({"csrf": self.csrf, "biz": "new_dyn", "category": "daily"})
        file_name = file_path.name
        file_size_kb = round(file_path.stat().st_size / 1024, 2)
        with open(file_path, "rb") as f:
            files = {"file_up": (file_name, f, self._detect_mime(file_path))}
            data = {"biz": "new_dyn", "category": "daily", "csrf": self.csrf}
            resp = self.session.post(url, params=params, files=files, data=data)
        result = resp.json()
        if result.get("code") != 0:
            raise BiliApiError(
                result.get("code", -1),
                result.get("message", "upload_bfs失败"),
                result,
            )
        with Image.open(file_path) as img:
            w, h = img.size
        raw_url = result["data"]["image_url"]
        # B站图床返回 http://，但API要求 https://
        if raw_url.startswith("http://"):
            raw_url = "https://" + raw_url[7:]
        return {
            "url": raw_url,
            "width": w,
            "height": h,
            "size": file_size_kb,
        }

    def _upload_image_fallback(self, file_path: Path) -> dict:
        """回退方案：使用旧版 upcover 接口上传图片"""
        url = f"{BILI_API_BASE}/x/article/creative/article/upcover"
        file_name = file_path.name
        file_size_kb = round(file_path.stat().st_size / 1024, 2)
        with open(file_path, "rb") as f:
            files = {"binary": (file_name, f, self._detect_mime(file_path))}
            data = {"csrf": self.csrf, "cover": ""}
            resp = self.session.post(url, files=files, data=data)
        result = resp.json()
        if result.get("code") != 0:
            raise BiliApiError(
                result.get("code", -1),
                result.get("message", "图片上传失败"),
                result,
            )
        with Image.open(file_path) as img:
            w, h = img.size
        raw_url = result["data"]["url"]
        # upcover 返回 http://，改为 https://
        if raw_url.startswith("http://"):
            raw_url = "https://" + raw_url[7:]
        return {"url": raw_url, "width": w, "height": h, "size": file_size_kb}

    @staticmethod
    def _detect_mime(path: Path) -> str:
        ext = path.suffix.lower()
        return {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }.get(ext, "application/octet-stream")

    # ------------------------------------------------------------------
    # 专栏草稿箱
    # ------------------------------------------------------------------

    def save_draft(self, arg_payload: dict) -> dict:
        """
        将专栏保存到草稿箱。
        arg_payload 即请求体中 arg 字段的内容。
        首次调用不传入 article_id 会新建草稿；
        后续传入 article_id 会更新已有草稿。
        返回响应 JSON。
        """
        url = f"{BILI_API_BASE}/x/dynamic/feed/article/draft/add"
        params = self.sign({"csrf": self.csrf})
        body = {"arg": arg_payload}
        resp = self.session.post(url, params=params, json=body)
        result = resp.json()
        if result.get("code") != 0:
            raise BiliApiError(
                result.get("code", -1),
                result.get("message", "保存草稿失败"),
                result,
            )
        return result


# =============================================================================
# Markdown → Opus 转换器
# =============================================================================

# B站 Opus 文本样式常量
FONT_SIZE_REGULAR = 17
FONT_SIZE_H1 = 20
FONT_SIZE_H2 = 18


def make_text_node(
    words: str,
    *,
    font_size: int = FONT_SIZE_REGULAR,
    font_level: str = "regular",
    bold: bool = False,
    italic: bool = False,
    underline: bool = False,
    strikethrough: bool = False,
    color: str = "",
    dark_color: str = "",
) -> dict:
    """构造一个 Opus 文本节点"""
    style: dict[str, bool] = {}
    if bold:
        style["bold"] = True
    if italic:
        style["italic"] = True
    if underline:
        style["underline"] = True
    if strikethrough:
        style["strikethrough"] = True

    node: dict = {
        "node_type": 1,
        "word": {
            "words": words,
            "font_size": font_size,
            "color": color,
            "dark_color": dark_color,
            "style": style,
            "font_level": font_level,
        },
    }
    # 只有非空样式才保留
    if not style:
        node["word"]["style"] = {}
    return node


def make_heading_node(words: str, level: int) -> dict:
    """构造标题节点（Opus 格式：para_type=9, heading_type=1/2/3）"""
    heading_config = {
        1: {"font_size": 24, "font_level": "xxLarge", "heading_type": 1},
        2: {"font_size": 22, "font_level": "xLarge", "heading_type": 2},
        3: {"font_size": 20, "font_level": "large", "heading_type": 3},
    }
    cfg = heading_config.get(level, heading_config[3])
    return {
        "node_type": 1,
        "word": {
            "words": words,
            "font_size": cfg["font_size"],
            "color": "",
            "dark_color": "",
            "style": {},
            "font_level": cfg["font_level"],
        },
    }


def make_heading_paragraph(words: str, level: int) -> dict:
    """构造标题段落"""
    heading_config = {
        1: {"heading_type": 1},
        2: {"heading_type": 2},
        3: {"heading_type": 3},
    }
    cfg = heading_config.get(level, heading_config[3])
    return {
        "para_type": 9,
        "format": {
            "indent": {"first_line_indent": 0, "indent": 0},
            "heading_type": cfg["heading_type"],
        },
        "text": {"nodes": [make_heading_node(words, level)]},
    }


def make_image_paragraph(
    img_url: str, width: int, height: int, size: float = 0
) -> dict:
    """构造图片段落（Opus 格式）"""
    return {
        "para_type": 2,
        "pic": {
            "pics": [
                {
                    "url": img_url,
                    "width": width,
                    "height": height,
                    "size": size,
                    "ai_gen_pic": 0,
                }
            ],
            "style": 0,
        },
    }


def make_divider_paragraph() -> dict:
    """构造分隔线段落（Opus 格式：para_type=3, line_type=1）"""
    return {"para_type": 3, "line": {"line_type": 1}}


def make_text_paragraph(nodes: list[dict]) -> dict:
    """构造文本段落"""
    return {
        "para_type": 1,
        "format": {
            "indent": {
                "first_line_indent": 0,
                "indent": 0,
            }
        },
        "text": {"nodes": nodes},
    }


# ------------------------------------------------------------------
# 内联 Markdown 解析
# ------------------------------------------------------------------

INLINE_PATTERN = re.compile(
    r"~~(.*?)~~"  # ~~删除线~~
    r"|`(.*?)`"  # `行内代码`
    r"|\*\*(.*?)\*\*"  # **粗体**
    r"|\*(.*?)\*"  # *斜体*
    r"|(.)"  # 普通字符（fallback）
)


def parse_inline(text: str) -> list[dict]:
    """
    将一行纯文本解析为 Opus 文本节点列表，支持：
    **粗体**  *斜体*  ~~删除线~~  `行内代码`
    """
    nodes: list[dict] = []
    for match in INLINE_PATTERN.finditer(text):
        if match.group(1) is not None:  # ~~删除线~~
            nodes.append(make_text_node(match.group(1), strikethrough=True))
        elif match.group(2) is not None:  # `行内代码`
            nodes.append(
                make_text_node(
                    match.group(2),
                    font_level="regular",
                    color="#c7254e",
                )
            )
        elif match.group(3) is not None:  # **粗体**
            nodes.append(make_text_node(match.group(3), bold=True))
        elif match.group(4) is not None:  # *斜体*
            nodes.append(make_text_node(match.group(4), italic=True))
        elif match.group(5) is not None:  # 普通字符
            ch = match.group(5)
            if (
                nodes
                and not nodes[-1]["word"]["style"]
                and nodes[-1]["word"]["font_level"] == "regular"
                and not nodes[-1]["word"]["color"]
            ):
                # 合并到上一个普通节点
                nodes[-1]["word"]["words"] += ch
            else:
                nodes.append(make_text_node(ch))
    return nodes


# ------------------------------------------------------------------
# 块级 Markdown 解析
# ------------------------------------------------------------------


class MarkdownParser:
    """将 Markdown 字符串转换为 Opus paragraphs 列表"""

    def __init__(self, client: BiliClient, base_dir: Path):
        self.client = client
        self.base_dir = base_dir

    def parse(self, md: str) -> list[dict]:
        lines = md.split("\n")
        paragraphs: list[dict] = []
        buffer: list[dict] = []  # 当前段落累积的节点

        def flush():
            nonlocal buffer
            if buffer:
                paragraphs.append(make_text_paragraph(buffer))
                buffer = []

        for line in lines:
            stripped = line.strip()

            # 空行 → 结束当前段落
            if not stripped:
                flush()
                continue

            # 标题
            h_match = re.match(r"^(#{1,3})\s+(.*)", stripped)
            if h_match:
                flush()
                level = len(h_match.group(1))
                paragraphs.append(make_heading_paragraph(h_match.group(2), level))
                continue

            # 图片 ![alt](path)
            img_match = re.match(r"!\[.*?\]\((.*?)\)", stripped)
            if img_match:
                flush()
                self._process_image(img_match, paragraphs)
                continue

            # 分隔线
            if stripped in ("---", "***", "___"):
                flush()
                paragraphs.append(make_divider_paragraph())
                continue

            # 普通行 — 解析内联格式
            buffer.extend(parse_inline(stripped))

        flush()
        return paragraphs

    def _process_image(self, match: re.Match, paragraphs: list[dict]) -> None:
        """处理图片：上传并追加图片段落"""
        raw_path = match.group(1)
        # 支持相对路径（相对于 base_dir）和绝对路径
        img_path = (
            Path(raw_path)
            if Path(raw_path).is_absolute()
            else (self.base_dir / raw_path).resolve()
        )

        if not img_path.is_file():
            print(f"  [警告] 图片文件不存在，跳过: {img_path}")
            return

        print(f"  正在上传图片: {img_path}")
        try:
            info = self.client.upload_image(img_path)
            paragraphs.append(
                make_image_paragraph(
                    info["url"], info["width"], info["height"], info.get("size", 0)
                )
            )
            print(f"    → 上传成功: {info['url']}")
        except BiliApiError as e:
            print(f"    [错误] 图片上传失败: {e}")
        except Exception as e:
            print(f"    [错误] 图片处理异常: {e}")


# =============================================================================
# 主流程
# =============================================================================


def build_summary(paragraphs: list[dict]) -> str:
    """从段落列表中提取纯文本摘要（取前 200 字）"""
    texts: list[str] = []
    for p in paragraphs:
        if p.get("para_type") == 1:
            for node in p.get("text", {}).get("nodes", []):
                if node.get("node_type") == 1:
                    texts.append(node.get("word", {}).get("words", ""))
    full = "".join(texts)
    return full[:200].replace("\n", " ")


def publish_article(
    client: BiliClient,
    article_dir: Path,
    *,
    category_id: int = 15,
    article_id: int | None = None,
    private_pub: int = 2,
    reprint: int = 1,
    original: int = 0,
    comment_selected: int = 0,
    up_closed_reply: int = 0,
) -> dict:
    """
    将 article_dir 下的专栏发布到草稿箱。

    参数:
        client:          已认证的 BiliClient 实例
        article_dir:     文章文件夹路径（包含 main.md 和 images/）
        category_id:     分区 ID (15=生活, 4=游戏, 等等)
        article_id:      已有草稿 ID（None 表示新建）
        private_pub:     可见性 (2=公开, 1=仅自己可见)
        reprint:         转载设置 (1=禁止转载)
        original:        原创声明 (0=不声明, 1=声明原创)
        comment_selected:精选评论 (0=关闭, 1=开启)
        up_closed_reply: 关闭评论 (0=允许评论, 1=关闭评论)

    返回:
        API 响应 JSON，包含 article_id
    """
    md_path = article_dir / "main.md"
    if not md_path.is_file():
        raise FileNotFoundError(f"找不到 main.md: {md_path}")

    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    # ---- 提取标题 ----
    title_match = re.search(r"^#\s+(.*)", md_content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "未命名文章"

    # ---- 解析 Markdown → Opus paragraphs ----
    print("正在解析 Markdown ...")
    parser = MarkdownParser(client, article_dir)
    paragraphs = parser.parse(md_content)
    print(f"  解析完成，共 {len(paragraphs)} 个段落")

    # ---- 生成摘要 ----
    summary = build_summary(paragraphs)
    print(f"  摘要: {summary[:60]}...")

    # ---- 构造请求参数 ----
    # 注意：image_urls 是文章封面（自定义封面），不是正文图片列表，
    #       如果不需要自定义封面则不传此字段
    arg: dict = {
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

    # ---- 导出 payload 到文件（调试用） ----
    payload_path = article_dir / "payload.json"
    with open(payload_path, "w", encoding="utf-8") as f:
        json.dump({"arg": arg}, f, ensure_ascii=False, indent=2)
    print(f"  payload 已导出: {payload_path}")

    # ---- 调用 API ----
    print("正在保存到草稿箱 ...")
    result = client.save_draft(arg)
    aid = result["data"]["article_id"]
    print(f"  ✔ 成功！草稿 ID: {aid}")
    return result


# =============================================================================
# 配置加载（环境变量 / .env 文件）
# =============================================================================

REQUIRED_ENV = ("SESSDATA", "bili_jct", "buvid3")


def load_auth() -> dict:
    """从 .env 文件或系统环境变量加载认证配置"""
    load_dotenv(find_dotenv(usecwd=True))
    cfg = {}
    for key in REQUIRED_ENV:
        val = os.environ.get(key, "").strip()
        if val:
            cfg[key] = val
    return cfg


# =============================================================================
# 命令行入口
# =============================================================================


def main():
    # 尝试加载配置
    cfg = load_auth()
    missing = [k for k in REQUIRED_ENV if k not in cfg]

    if missing:
        print("错误：缺少必要的环境变量")
        print()
        print("请在项目根目录创建 .env 文件，内容如下：")
        print()
        print("    SESSDATA=你的SESSDATA值")
        print("    bili_jct=你的bili_jct值")
        print("    buvid3=你的buvid3值")
        print()
        print("获取方式：浏览器登录 B站 后")
        print("  F12 → Application → Cookies → bilibili.com")
        print("  复制 SESSDATA、bili_jct、buvid3 三个字段的值")
        print()
        print("也可通过系统环境变量设置上述三项。")
        sys.exit(1)

    sessdata = cfg["SESSDATA"]
    bili_jct = cfg["bili_jct"]
    buvid3 = cfg["buvid3"]

    # 解析目标文件夹
    args = sys.argv[1:]
    if not args:
        print("用法: python bili_publisher.py <文章目录>")
        print("示例: python bili_publisher.py articles/article1")
        sys.exit(1)

    article_dir = Path(args[0]).resolve()
    if not article_dir.is_dir():
        print(f"错误：目录不存在: {article_dir}")
        sys.exit(1)

    # 初始化客户端
    client = BiliClient(sessdata, bili_jct, buvid3)

    print(f"\n📄 专栏: {article_dir}")
    print("-" * 40)

    try:
        result = publish_article(client, article_dir)
        print(f"\n✅ 完成！草稿 ID: {result['data']['article_id']}")
        print(
            f"   可在创作中心查看: "
            f"https://member.bilibili.com/platform/upload/text/new-edit"
            f"?aid={result['data']['article_id']}"
        )
    except BiliApiError as e:
        print(f"\n❌ API 错误 [{e.code}]: {e.message}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 运行时错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
