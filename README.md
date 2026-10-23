# 多平台文章发布工具

将本地 Markdown 文章或 **飞书云文档**一键发布到 **B站专栏 / 森空岛 / NGA**。

## 快速开始

```bash
# 1. 安装依赖
uv sync

# 2. 配置认证（编辑 .env 文件）
cp .env.example .env
# 然后从浏览器请求头复制完整 Cookie，填入 .env 的 BILIBILI_COOKIE

# 3. 运行
uv run python -m article_publisher bilibili markdown articles/article1
```

---

## 认证配置

程序需要 **B站认证**，飞书模式还需 **飞书应用认证**：

### B站 认证

| 变量 | 说明 | 获取方式 |
|------|------------|----------|
| `BILIBILI_COOKIE` | 浏览器请求头中的完整 Cookie 字符串 | F12 → Network → Request Headers → Cookie |

登录 B站并打开创作中心，按 F12 打开 **Network（网络）** 面板后刷新页面，选择发送到 `api.bilibili.com` 的已登录请求，在 **Request Headers（请求标头）** 中复制 `Cookie` 的完整值，填入 `.env`：

```dotenv
BILIBILI_COOKIE="粘贴浏览器请求头中的完整 Cookie 值"
```

仅复制值，不包含 `Cookie:` 前缀，保留所有 `name=value` 字段及分号分隔符。程序会发送完整 Cookie，并自动从中提取 `bili_jct` 作为 CSRF 令牌；缺少或留空 `SESSDATA`、`bili_jct` 时会报错。不要使用 `document.cookie` 获取，因为它无法读取 HttpOnly 的 `SESSDATA`。

Cookie 过期后需重新登录并更新 `BILIBILI_COOKIE`。

### 飞书认证（飞书云文档模式需要）

| 变量 | 说明 | 获取方式 |
|------|------|----------|
| `LARK_APP_ID` | 飞书应用 App ID | [飞书开放平台](https://open.feishu.cn/app) 创建应用后获取 |
| `LARK_APP_SECRET` | 飞书应用 App Secret | 同上 |

> ⚠️ `BILIBILI_COOKIE` 包含登录凭据，泄露等同账号被盗，`.env` 已加入 `.gitignore`

---

## 运行

平台作为一级子命令，输入源作为二级子命令：

### B站

```bash
```bash
# 发布到草稿箱
uv run -m article_publisher bilibili markdown articles/article1
uv run -m article_publisher bilibili lark <document_id>

# 编辑已发布文章
uv run -m article_publisher bilibili --edit <文章ID> markdown articles/article1
```

### 森空岛

```bash
# 生成草稿（输出浏览器控制台脚本到 localStorage）
uv run -m article_publisher skland markdown articles/article1
uv run -m article_publisher skland lark <document_id>

# 编辑已发布文章
uv run -m article_publisher skland --item-id <文章ID> markdown articles/article1
```

### NGA

```bash
# 发布新帖
uv run -m article_publisher nga markdown articles/article1 --fid 516
uv run -m article_publisher nga lark <document_id> --fid 516

# 编辑已有帖子
uv run -m article_publisher nga --tid <帖子ID> markdown articles/article1 --fid 516
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
- [x] **编辑已发布文章** — B站 (`--edit <文章ID>`)、森空岛 (`--item-id <文章ID>`)、NGA (`--tid <帖子ID>`)
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
uv run python main.py articles/article1                           # Markdown 模式
uv run python main.py --lark <doc_id>                              # 飞书云文档模式
uv run python main.py --lark <doc_id> --category 4                 # 指定分区
uv run python main.py --lark <doc_id> --private                    # 仅自己可见
uv run -m article_publisher --update 350908 md articles/article1   # 更新已有草稿
uv run -m article_publisher --edit 51387979 md articles/article1   # 编辑已发布 B站 文章
uv run -m article_publisher --item-id 5988027 md articles/article1 # 编辑已发布森空岛文章
```

### 编辑已发布文章

各平台均支持编辑已发布的内容：

| 平台 | 参数 | 说明 |
|------|------|------|
| B站 | `--edit <文章ID>` | 通过 `edit/opus` API 直接更新已发布文章 |
| 森空岛 | `--item-id <文章ID>` | 通过 `item/upd` API 更新（保留标签、合集等元数据） |
| NGA | `--tid <帖子ID>` | 先删旧附件再重新提交（原有功能） |

森空岛编辑模式支持粗体、斜体、下划线、删除线、预设文字颜色、段落与标题对齐、
一级到三级标题、引用块、有序/无序列表及多层混合嵌套、图片描述和分隔线。
四级及更深标题转换为加粗段落，嵌套引用展平但保留内容；代码块以带完整围栏的
文本段落保留，公式保留为 LaTeX 文本。链接目前仅保留文字和样式，不保留跳转。
代码块、公式、链接降级时会输出提示。示例中的表情、贴纸、@用户和视频尚未纳入
通用输入文档模型，因此不会从 Markdown / 飞书输入生成这些原生节点。

编辑会整体替换标题和正文，默认沿用原文章的游戏分区、子分区、标签和合集。
封面原图仍存在于新正文时保留原封面；原图被移除或重新上传后，按官方编辑器规则
改选新正文第一张图片，并清除旧裁剪引用。无图正文不提交封面图片 ID。
显式传入 `--cover` 时将该图片加入正文开头作为封面，由服务端生成裁剪结果。
`--game-id`、`--cate-id` 可覆盖分区。新草稿仍默认使用
明日方舟 / 攻略分区。正文图片缺失或上传失败时会停止更新，避免提交缺图文章。

```bash
# 预览完整更新 JSON，不读取旧文章、不上传图片、不提交更新
uv run -m article_publisher skland --item-id 5988027 --dry-run markdown articles/article1

# 更新已有文章，保留原分区
uv run -m article_publisher skland --item-id 5988027 markdown articles/article1
```

`--dry-run` 使用占位元数据和图片文本占位，因此不能用于验证旧文章元数据或图片上传。
针对捕获请求的离线回归测试：`uv run python -m unittest discover -s tests -v`。

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
from pathlib import Path
from article_publisher import BiliClient, MarkdownConverter, BiliPublisher, BiliPublishConfig
from article_publisher._auth import load_bilibili_auth

# 在异步函数中调用
async with BiliClient(cookie_str=load_bilibili_auth()["BILIBILI_COOKIE"]) as client:
    converter = MarkdownConverter(Path("articles/article1/main.md"))
    doc = await converter.convert()
    config = BiliPublishConfig(article_id=350791)
    publisher = BiliPublisher(client, config=config)
    result = await publisher.publish(doc)
```

### 编辑已发布文章（通过 Python API）

```python
# B站
config = BiliPublishConfig(edit_article_id=51387979)
publisher = BiliPublisher(client, config=config)
result = await publisher.publish(doc)

# 森空岛
config = SklandPublishConfig(item_id="5988027")
publisher = SklandPublisher(client, config=config)
result = await publisher.publish(doc)
```

---

## 项目文件结构

```
├── main.py                          # 入口脚本
├── src/
│   └── article_publisher/           # 核心包
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

## 文本颜色

森空岛和 NGA 发布时使用 Oklab 色彩空间中的距离，将来源字体颜色映射到平台最接近的
支持色。支持 `#RGB`、`#RRGGBB`（不区分大小写），以及目标调色板中的颜色名称；
未指定或无效的颜色使用平台默认色。不会修改来源文档中的颜色。

| 平台 | 颜色输出 |
|------|----------|
| 森空岛 | 6 种预设色；草稿与 `--item-id` 编辑模式均支持 |
| B 站 | 支持任意颜色，原样保留来源颜色，不匹配预设色、不自动生成 `dark_color` 或 `bili_theme` |
| NGA | 按颜色选择器的 24 种实际色值匹配，输出 `[color=颜色名称]`，不输出十六进制 BBCode |

森空岛和 NGA 的行内代码颜色同样经过映射；B 站保留行内代码的来源色。
NGA 使用颜色选择器截图的实际色值，部分颜色
（如 `blue`、`orange`、`green`、`silver`）与 CSS 同名色不同。
背景色／高亮色不在本次字体颜色支持范围内；B 站链接节点、NGA 链接及
森空岛草稿中退化为纯文本的链接仍使用原有处理方式，不保留来源链接颜色。

核心算法与调色板位于 `src/article_publisher/colors.py`。

## TODO

- [ ] NGA 自动回退全角标点
