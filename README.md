# B站 Opus 专栏自动发布工具

将本地 Markdown 文章或 **飞书云文档**一键发布到 **B站创作中心草稿箱**。

## 快速开始

```bash
# 1. 安装依赖
uv sync

# 2. 配置认证（编辑 .env 文件）
cp .env.example .env
# 然后从浏览器 Cookie 中复制 SESSDATA、bili_jct、buvid3 填入 .env

# 3. 运行
uv run python -m bilibili_article md articles/article1
```

---

## 认证配置

程序需要 **B站认证**，飞书模式还需 **飞书应用认证**：

### B站 认证

| 变量 | 对应 Cookie | 获取方式 |
|------|------------|----------|
| `SESSDATA` | 登录会话令牌 | F12 → Application → Cookies → bilibili.com |
| `bili_jct` | CSRF 令牌 | 同上 |
| `buvid3` | 设备标识 | 同上 |

### 飞书认证（飞书云文档模式需要）

| 变量 | 说明 | 获取方式 |
|------|------|----------|
| `LARK_APP_ID` | 飞书应用 App ID | [飞书开放平台](https://open.feishu.cn/app) 创建应用后获取 |
| `LARK_APP_SECRET` | 飞书应用 App Secret | 同上 |

> ⚠️ `SESSDATA` 和 `bili_jct` 泄露等同账号被盗，`.env` 已加入 `.gitignore`

---

## 运行

### Markdown 模式

```bash
uv run python main.py articles/article1
uv run python main.py articles/我的新文章
```

### 飞书云文档模式

```bash
uv run python main.py --lark <document_id>
# 示例:
uv run python main.py --lark UXiMw9NeNiH3ypkyaXmc5VR7nvc
```

### 输出示例

```
📄 专栏: D:\...\articles\article1
----------------------------------------
正在解析 Markdown ...
  正在上传图片: ...\images\image.png
    → 上传成功: https://i0.hdslb.com/bfs/new_dyn/xxx.png
  解析完成，共 18 个段落
  摘要: 这是一个使用程序化发布工具创建的 B站 专栏...
  payload 已导出: ...\articles\article1\payload.json
正在保存到草稿箱 ...
  ✔ 成功！草稿 ID: 350791

✅ 完成！草稿 ID: 350791
   可在创作中心查看:
   https://member.bilibili.com/platform/upload/text/new-edit?aid=350791
```

---

## ✅ 已实现的功能

### 输入源

- [x] **本地 Markdown** — 解析 `articles/*/main.md`，支持图片自动上传
- [x] **飞书云文档** — 通过文档 ID 拉取飞书文档，自动转换并上传图片

### Markdown 语法支持

| Markdown | B站 Opus 效果 |
|----------|--------------|
| `# 标题` | H1 标题（24px, `xxLarge`） |
| `## 标题` | H2 标题（22px, `xLarge`） |
| `### 标题` | H3 标题（20px, `large`） |
| `**粗体**` | 加粗样式 |
| `*斜体*` | 斜体样式 |
| `~~删除线~~` | 删除线样式 |
| `` `行内代码` `` | 红色等宽文本 |
| `![描述](images/x.png)` | 图片（自动上传到B站图床） |
| `---` / `***` / `___` | 分隔线 |
| 普通文本段落 | B站正文（17px） |
| 空行分隔 | 段落分隔 |

### 程序功能

- [x] **WBI 签名** — 自动从 nav 接口获取密钥并签名
- [x] **图片上传**（双通道）— 首选 `upload_bfs`，失败自动回退 `upcover`
- [x] **多图片支持** — 一篇文章任意数量图片
- [x] **保存草稿** — 新建/更新草稿
- [x] **标题格式** — 使用 `para_type: 9` + `heading_type` 的正确格式
- [x] **`pub_info`** / **`attachments`** — 编辑器版本标识和 AI 声明
- [x] **payload 导出** — 每次保存时导出 `payload.json` 用于调试
- [x] **环境变量配置** — `.env` 文件 / 系统环境变量
- [x] **双通道图片上传** — `upload_bfs`(首选) + `upcover`(备用)

### 飞书云文档转换支持

| 飞书块类型 | B站 Opus 效果 | 说明 |
|-----------|--------------|------|
| `text` | 普通正文 | 支持粗体/斜体/下划线/删除线/行内代码/超链接/公式 |
| `heading1~3` | H1~H3 标题 | 完美对应 B站 标题格式 |
| `heading4~9` | 加粗正文 | B站 仅支持 H1~H3 |
| `bullet` | 无序列表 | 支持到 3 级嵌套 |
| `ordered` | 有序列表 | 支持到 3 级嵌套 |
| `code` | 代码块 | 语言自动识别 |
| `quote_container` | 引用块 | 同组引用共享 `combine_hash` |
| `divider` | 分隔线 | — |
| `image` | 图片段落 | 自动从飞书下载并上传到 B站 图床 |
| `callout` | 普通正文 | 保留子块内容 |
| `grid` / `table` | 展平子块 | 复杂布局展平为普通内容 |

---

## ❌ 暂未实现的 Markdown 语法

这些是 B站 Opus 格式支持、但当前解析器暂未转换的语法（欢迎 PR）：

| Markdown | B站 Opus 格式 | 优先级 |
|----------|--------------|:------:|
| `- list` / `1. list` | `para_type:5/6` + `list_format` | 🟡 中 |
| `> blockquote` | `para_type:4` + `combine_hash` | 🟡 中 |
| `` ```code``` `` | `para_type:8` + `code.lang/content` | 🟡 中 |
| `[link](url)` | `node_type:4` + `link` 对象 | 🟢 低 |
| `$公式$` | `node_type:5` + `formula.latex_content` | 🟢 低 |
| 表情 `[doge]` | `node_type:2` + `emote.raw_text` | 🟢 低 |
| 文字背景色 | `bg_style` 字段 | 🟢 低 |
| 对齐方式 | `format.align: 0/1/2` | 🟢 低 |
| 缩进 | `format.indent.indent: 1/2` | 🟢 低 |
| 图片描述 | `pics[].comment` | 🟢 低 |

---

## 高级用法

### 命令行选项

```bash
uv run python main.py articles/article1              # Markdown 模式
uv run python main.py --lark <doc_id>                 # 飞书云文档模式
uv run python main.py --lark <doc_id> --category 4    # 指定分区
uv run python main.py --lark <doc_id> --private       # 仅自己可见
uv run python -m bilibili_article --update 350908 md articles/article1  # 更新已有草稿
```

### 指定分区

```bash
uv run python main.py articles/article1 --category 4  # 4=游戏
```

常用分区：`15`=生活(默认) `4`=游戏 `2`=动画 `3`=音乐 `5`=娱乐 `17`=单机游戏 `36`=知识

### 设为仅自己可见

```bash
uv run python main.py articles/article1 --private
```

### 更新已有草稿（通过 Python API）

```python
from bilibili_article import BiliClient, MarkdownConverter, PublishConfig, publish_article

client = BiliClient(sessdata, bili_jct, buvid3)
converter = MarkdownConverter(client, "articles/article1/main.md")
config = PublishConfig(article_id=350791)
result = publish_article(client, converter, title="标题", config=config)
```

---

## 项目文件结构

```
├── main.py                          # 入口脚本
├── src/
│   └── bilibili_article/            # 核心包
│       ├── __init__.py              # 包导出
│       ├── _auth.py                 # 认证配置加载
│       ├── _wbi.py                  # WBI 签名工具
│       ├── client.py                # B站 API 客户端（BiliClient）
│       ├── opus.py                  # Opus 格式数据构建器
│       ├── publisher.py             # 发布编排（publish_article）
│       ├── cli.py                   # 命令行入口
│       └── converters/
│           ├── __init__.py
│           ├── base.py              # 转换器基类
│           ├── markdown.py          # Markdown → Opus 转换器
│           └── lark.py              # 飞书云文档 → Opus 转换器
├── .env                             # 认证配置（已 gitignore）
├── .env.example                     # 环境变量模板
├── pyproject.toml                   # Python 项目配置
├── README.md                        # 本文件
├── articles/
│   └── article1/
│       ├── main.md
│       ├── payload.json             # 运行时自动导出（调试用）
│       └── images/
│           ├── image.png
│           └── og-image.png
└── docs/ 相关文档
    ├── API_REFERENCE.md
    ├── PAYLOAD_GUIDE.md
    ├── bilibili_保存到草稿箱_example_payload.json
    ├── lark_获取文档基本信息_example_response.json
    └── lark_获取文档所有块_example_response.json
```

---

## 技术原理

### Markdown 模式

| 步骤 | API | 说明 |
|:----:|-----|------|
| 1 | `GET /x/web-interface/nav` | 获取 WBI 密钥 + 用户信息 |
| 2 | `POST /x/dynamic/feed/draw/upload_bfs` | 上传图片到 B站 CDN |
| 3 | `POST /x/dynamic/feed/article/draft/add` | 保存草稿（WBI 签名） |

### 飞书云文档模式

| 步骤 | API | 说明 |
|:----:|-----|------|
| 1 | `GET /open-apis/docx/v1/documents/:id` | 获取飞书文档信息（标题） |
| 2 | `GET /open-apis/docx/v1/documents/:id/blocks` | 获取文档所有块（分页） |
| 3 | `GET /open-apis/drive/v1/medias/:token/download` | 下载图片 |
| 4 | `POST /x/dynamic/feed/draw/upload_bfs` | 上传图片到 B站 CDN |
| 5 | `POST /x/dynamic/feed/article/draft/add` | 保存草稿（WBI 签名） |

详细 API 文档见 [`API_REFERENCE.md`](docs/API_REFERENCE.md)，Payload 格式详解见 [`PAYLOAD_GUIDE.md`](docs/PAYLOAD_GUIDE.md)。

---

## 免责声明

- 本工具仅供 **学习交流** 使用
- 请遵守 [Bilibili 用户协议](https://www.bilibili.com/protocal/licence.html)
- 请勿用于发布违规内容
- 使用者需自行承担相关责任
