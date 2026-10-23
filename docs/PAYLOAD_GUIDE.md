# Opus 专栏 Payload 详解

> 本文档对照 [`bilibili_保存到草稿箱_example_payload.json`](bilibili_保存到草稿箱_example_payload.json) 逐层解析 B站 Opus 专栏的请求体结构。
> 该 payload 来自在 B站 编辑器中手动编辑文章后点"保存草稿"时抓取的真实请求。

---

## 目录

1. [顶层字段](#1-顶层字段)
2. [Opus 内容体](#2-opus-内容体)
3. [文本段落与节点](#3-文本段落与节点)
4. [标题段落](#4-标题段落)
5. [图片段落](#5-图片段落)
6. [分隔线](#6-分隔线)
7. [列表](#7-列表)
8. [引用块](#8-引用块)
9. [代码块](#9-代码块)
10. [表情、链接、公式](#10-表情链接公式)
11. [常见段落速查表](#11-常见段落速查表)

---

## 1. 顶层字段

```json
{
  "arg": {
    "type": 4,
    "template_id": 1,
    "category_id": 15,
    "article_id": 350788,
    "title": "专栏标题",
    "private_pub": 2,
    "reprint": 0,
    "original": 1,
    "list_id": 1061428,
    "comment_selected": 0,
    "up_closed_reply": 0,
    "timer_pub_time": 0,
    "only_fans_level": 0,
    "only_fans_dnd": 0,
    "image_urls": ["http://..."],
    "summary": "摘要文本...",
    "opus": { ... }
  }
}
```

| 字段 | 值 | 说明 |
|------|:--:|------|
| `type` | `4` | 文章类型（固定值） |
| `template_id` | `1` | 模板 ID（固定值） |
| `category_id` | `15` | 分区 ID，`15`=生活 |
| `article_id` | `350788` | 草稿 ID（新建时不传，更新时传） |
| `title` | `"专栏标题"` | 文章标题（≤50字） |
| `private_pub` | `2` | 可见性：`2`=公开，`1`=仅自己可见 |
| `reprint` | `0` | `0`=允许转载，`1`=禁止转载 |
| `original` | `1` | `0`=不声明原创，`1`=声明原创 |
| `list_id` | `1061428` | 文集 ID，`0`=不加入文集 |
| `comment_selected` | `0` | `0`=关闭精选评论，`1`=开启 |
| `up_closed_reply` | `0` | `0`=允许评论，`1`=关闭评论 |
| `timer_pub_time` | `0` | 定时发布时间戳，`0`=立即发布 |
| `only_fans_level` | `0` | 仅粉丝可见等级 |
| `only_fans_dnd` | `0` | 粉丝可见免打扰 |
| `image_urls` | `[...]` | **自定义封面**（可选）。仅一张图，不是正文所有图片。不传则自动从正文开头取文字做封面 |
| `summary` | `"..."` | 纯文本摘要（前 250 字） |

---

## 2. Opus 内容体

```json
{
  "opus_source": 2,
  "title": "专栏标题",
  "content": {
    "paragraphs": [ ... ]    // ← 正文的核心
  },
  "pub_info": {
    "editor_version": "eva3-3.0.0"   // 编辑器版本标识
  },
  "attachments": {
    "is_aigc": 0                      // 0=不是AI生成，1=AI生成
  }
}
```

| 字段 | 说明 |
|------|------|
| `opus_source` | 来源标识：`2`=Web 编辑器 |
| `title` | 与顶层 `title` 相同 |
| `content.paragraphs` | 正文段落数组（核心内容） |
| `pub_info.editor_version` | 编辑器版本（B站 用于兼容性判断） |
| `attachments.is_aigc` | AI 生成声明：`0`=否，`1`=是 |

---

## 3. 文本段落与节点

### 3.1 文本段落

```json
{
  "para_type": 1,
  "format": {
    "indent": { "first_line_indent": 0, "indent": 0 },
    "align": 0       // 可选：0=左对齐，1=居中，2=右对齐
  },
  "text": {
    "nodes": [ ... ]  // 内联节点数组
  }
}
```

#### `format` 字段

| 子字段 | 说明 |
|--------|------|
| `indent.first_line_indent` | 首行缩进（通常为 `0`） |
| `indent.indent` | 段落缩进：`0`=无，`1`=一级，`2`=二级 |
| `align` | 对齐：`0`=左对齐，`1`=居中，`2`=右对齐（省略时默认左对齐） |

### 3.2 文本节点 (`node_type: 1`)

```json
{
  "node_type": 1,
  "word": {
    "words": "文本内容",
    "font_size": 17,
    "color": "",
    "dark_color": "",
    "style": {},
    "font_level": "regular"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `words` | string | 文字内容 |
| `font_size` | number | 字号：`24`(H1)、`22`(H2)、`20`(H3)、`17`(正文)、`13`(极小) |
| `font_level` | string | 级别：`"xxLarge"`、`"xLarge"`、`"large"`、`"regular"`、`"small"` |
| `style` | object | 样式：`{"bold":true}`、`{"italic":true}`、`{"underline":true}`、`{"strikethrough":true}` |
| `color` | string | 文字颜色（十六进制，如 `"#c9272c"`） |
| `dark_color` | string | 暗色模式文字颜色（如 `"#E18281"`） |
| `bili_theme` | string | B站 主题色标识（如 `"Re7"`=红色） |
| `bg_style` | object | 背景色样式（见下文） |

发布器按 Oklab 距离，从 25 种浅色模式文字预设色中选择最近色，并将该预设的
`color`、`dark_color`、`bili_theme` 一并写入。不会独立匹配深色值。
完整配对见 `src/article_publisher/colors.py` 中的 `BILIBILI_TEXT_COLORS`。
未设置或无效的来源颜色输出空 `color` / `dark_color`，不指定 `bili_theme`。

#### 背景色 (`bg_style`)

```json
"bg_style": {
  "style": 1,
  "color": {
    "color": "#ffd9e4",
    "dark_color": "#472030",
    "bili_theme": "Pi2"
  }
}
```

### 3.3 空文本段落

```json
{
  "para_type": 1,
  "format": { "indent": { "first_line_indent": 0, "indent": 0 } },
  "text": { "nodes": [] }
}
```

用于在文章末尾产生空白行。

---

## 4. 标题段落

标题使用独立的 `para_type: 9`，区别于普通文本段落。

```json
{
  "para_type": 9,
  "format": {
    "indent": { "first_line_indent": 0, "indent": 0 },
    "heading_type": 1
  },
  "text": {
    "nodes": [
      {
        "node_type": 1,
        "word": {
          "words": "一级标题",
          "font_size": 24,
          "color": "",
          "dark_color": "",
          "style": {},
          "font_level": "xxLarge"
        }
      }
    ]
  }
}
```

| 级别 | `heading_type` | `font_level` | `font_size` |
|:---:|:--------------:|:------------:|:-----------:|
| H1 | `1` | `"xxLarge"` | `24` |
| H2 | `2` | `"xLarge"` | `22` |
| H3 | `3` | `"large"` | `20` |

---

## 5. 图片段落

```json
{
  "para_type": 2,
  "pic": {
    "pics": [
      {
        "url": "http://i0.hdslb.com/bfs/new_dyn/xxxxx.png",
        "width": 128,
        "height": 128,
        "size": 5.66,
        "comment": "这是图片的描述",
        "ai_gen_pic": 0
      }
    ],
    "style": 0
  }
}
```

#### `pic.pics[]` 内部字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `url` | string | 图片 CDN 地址（注意是 `http://`，编辑器自动升级 HTTPS） |
| `width` | number | 图片宽度（像素） |
| `height` | number | 图片高度（像素） |
| `size` | number | 文件大小（KB） |
| `comment` | string | 图片描述/注释（可选） |
| `ai_gen_pic` | number | `0`=非AI生成，`1`=AI生成 |

> ⚠️ `pics` 是数组，目前编辑器每次插入只含一张图片。
> `style: 0` 是固定值。

---

## 6. 分隔线

```json
{
  "para_type": 3,
  "line": {
    "line_type": 1
  }
}
```

`line_type: 1` 表示水平分割线（`<hr>`）。

---

## 7. 列表

### 7.1 有序列表 (`para_type: 5`)

```json
{
  "para_type": 5,
  "format": {
    "align": 0,
    "list_format": {
      "level": 1,
      "order": 1,
      "theme": "arabic_num"
    },
    "combine_hash": "list_1780421967155_49ms6y5"
  },
  "text": {
    "nodes": [
      { "node_type": 1, "word": { "words": "有序列表之一", ... } }
    ]
  }
}
```

### 7.2 无序列表 (`para_type: 6`)

```json
{
  "para_type": 6,
  "format": {
    "align": 0,
    "list_format": {
      "level": 1,
      "order": 1,
      "theme": "dot"
    },
    "combine_hash": "list_1780421967157_ds0bvnf"
  },
  "text": {
    "nodes": [
      { "node_type": 1, "word": { "words": "无序列表之一", ... } }
    ]
  }
}
```

#### 列表字段说明

| 字段 | 说明 |
|------|------|
| `list_format.level` | 缩进层级：`1`=一级，`2`=二级，`3`=三级 |
| `list_format.order` | 序号（从 1 开始递增） |
| `list_format.theme` | 序号样式（见下表） |
| `combine_hash` | 同组列表项的共享标识（格式：`list_{时间戳}_{随机串}`） |

#### 列表主题

| 列表类型 | 一级 | 二级 | 三级 |
|:--------:|:---:|:---:|:----:|
| 有序 | `arabic_num` (1. 2. 3.) | `lower_letter` (a. b. c.) | `roman_num` (i. ii. iii.) |
| 无序 | `dot` (●) | `square` (■) | `circle` (○) |

---

## 8. 引用块

```json
{
  "para_type": 4,
  "format": {
    "indent": { "first_line_indent": 0, "indent": 0 },
    "combine_hash": "blockquote_1780421967159_0.40501190813454013"
  },
  "text": {
    "nodes": [
      { "node_type": 1, "word": { "words": "这是一个引用", ... } }
    ]
  }
}
```

同一引用块内的多个段落共享同一个 `combine_hash`。

---

## 9. 代码块

```json
{
  "para_type": 8,
  "code": {
    "lang": "python",
    "content": "这是代码块的第一行\n第二行\n第三行\n\n第五行"
  }
}
```

| 字段 | 说明 |
|------|------|
| `code.lang` | 编程语言标识（如 `"python"`、`"javascript"`、`"html"` 等） |
| `code.content` | 代码内容（含换行符 `\n`） |

---

## 10. 表情、链接、公式

这些作为**内联节点**出现在文本段落的 `text.nodes` 数组中。

### 10.1 表情 (`node_type: 2`)

```json
{
  "node_type": 2,
  "emote": {
    "raw_text": "[doge_金箍]"
  }
}
```

`raw_text` 就是 B站 聊天框中 `[名称]` 格式的原始文本，编辑器会自动渲染为对应的表情图片。

### 10.2 超链接 (`node_type: 4`)

```json
{
  "node_type": 4,
  "link": {
    "show_text": "链接展示文字",
    "link": "https://member.bilibili.com/platform/upload/text/new-edit?aid=350788",
    "icon": "",
    "icon_suffix": "",
    "link_type": 16,
    "biz_id": "",
    "pics": [],
    "style": {
      "bold": false,
      "italic": false,
      "strikethrough": false,
      "underline": false,
      "font_size": 0,
      "font_level": "regular"
    }
  }
}
```

### 10.3 Latex 公式 (`node_type: 5`)

```json
{
  "node_type": 5,
  "formula": {
    "latex_content": "E = mc^2"
  }
}
```

---

## 11. 常见段落速查表

| 想要的效果 | `para_type` | 关键字段 |
|-----------|:-----------:|----------|
| 普通正文 | `1` | `text.nodes` |
| 一级标题 | `9` | `heading_type: 1` |
| 二级标题 | `9` | `heading_type: 2` |
| 三级标题 | `9` | `heading_type: 3` |
| 图片 | `2` | `pic.pics[].url` |
| 分隔线 | `3` | `line.line_type: 1` |
| 引用块 | `4` | `format.combine_hash` |
| 有序列表 | `5` | `list_format.theme: arabic_num` |
| 无序列表 | `6` | `list_format.theme: dot` |
| 代码块 | `8` | `code.lang` + `code.content` |
| **粗体** | `1` | `style: {"bold": true}` |
| *斜体* | `1` | `style: {"italic": true}` |
| <u>下划线</u> | `1` | `style: {"underline": true}` |
| ~~删除线~~ | `1` | `style: {"strikethrough": true}` |
| 表情 | `1` | `node_type: 2, emote.raw_text` |
| 超链接 | `1` | `node_type: 4, link` |
| 公式 | `1` | `node_type: 5, formula` |
| 左对齐 | `1` | `format.align: 0`（默认） |
| 居中 | `1` | `format.align: 1` |
| 右对齐 | `1` | `format.align: 2` |
| 一级缩进 | `1` | `format.indent.indent: 1` |
| 二级缩进 | `1` | `format.indent.indent: 2` |

---

> 最后更新：2026-06-03 | 编辑器版本：eva3-3.0.0
>
> 对应示例文件：[`bilibili_保存到草稿箱_example_payload.json`](bilibili_保存到草稿箱_example_payload.json)
