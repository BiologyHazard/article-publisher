# B站 Opus 专栏 API 完整参考文档

> 本文档记录了通过抓包分析（HAR + 浏览器 DevTools）获得的 B站 新版 Opus 专栏相关所有 API 接口。
> 抓包时间：2026-06-02 | 编辑器版本：EVA3-3.0.0

---

## 目录

1. [认证体系](#1-认证体系)
2. [WBI 签名机制](#2-wbi-签名机制)
3. [API 总览](#3-api-总览)
4. [Opus 内容格式](#4-opus-内容格式)
5. [接口详解](#5-接口详解)
6. [附录：常用分区 ID](#6-附录常用分区-id)
7. [附录：错误码速查](#7-附录错误码速查)

---

## 1. 认证体系

### 1.1 Cookie 认证

B站 Web API 使用 Cookie 进行身份认证。本工具通过 `BILIBILI_COOKIE` 环境变量读取并发送浏览器请求头中的**完整 Cookie**。以下是其中的关键字段，实际配置时需保留浏览器发送的所有字段：

| Cookie 字段 | 说明 | HttpOnly | 获取方式 |
|-------------|------|----------|----------|
| `SESSDATA` | 登录会话令牌 | **是** | 浏览器 DevTools → Application → Cookies |
| `bili_jct` | CSRF 防护令牌（表单提交用） | 否 | 同上 |
| `buvid3` | 浏览器唯一标识符 | 否 | 同上 |

> ⚠️ `SESSDATA` 是 HttpOnly 的，无法通过 `document.cookie` 读取。
> 请登录创作中心，打开 DevTools → Network 并刷新页面，选择发送到 `api.bilibili.com` 的已登录请求，在 Request Headers 中复制 Cookie 的完整值（不含 `Cookie:` 前缀）。

在 `.env` 中配置 `BILIBILI_COOKIE="粘贴浏览器请求头中的完整 Cookie 值"`。

### 1.2 请求头

```http
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...
Referer: https://member.bilibili.com/platform/upload/text/new-edit
Origin: https://member.bilibili.com
Cookie: <BILIBILI_COOKIE 中保存的完整 Cookie 值>
```

### 1.3 CSRF 令牌

所有写操作（POST/PUT/DELETE）需要在请求参数中附带 `csrf` 参数，
值即为 Cookie 中的 `bili_jct` 字段。客户端会自动从 `BILIBILI_COOKIE` 中提取该值；缺少或留空 `SESSDATA`、`bili_jct` 时会在发送请求前报错。

---

## 2. WBI 签名机制

B站 大部分 API 需要 **WBI 签名**（`w_rid` + `wts`），
这是一种基于 MD5 的请求签名方案，用于防止请求被篡改。

### 2.1 获取签名密钥

**请求：**
```
GET https://api.bilibili.com/x/web-interface/nav
```

**响应中的关键字段：**
```json
{
  "data": {
    "wbi_img": {
      "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png",
      "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png"
    }
  }
}
```

### 2.2 生成 mixin_key

从 `img_url` 和 `sub_url` 中提取文件名（不含扩展名）拼接：
```
raw_key = "7cd084941338484aae1ad9425b84077c" + "4932caff0ff746eab6f01bf08b70ac45"
```

然后通过固定位移表重排，取前 32 位：
```python
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
    return "".join(raw[i] for i in MIXIN_KEY_TABLE)[:32]
```

### 2.3 生成签名

```python
def sign_wbi_params(params: dict, mixin_key: str) -> dict:
    out = dict(params)
    out["wts"] = int(time.time())  # 当前时间戳
    sorted_items = sorted(out.items())  # 按 key 排序
    query = urllib.parse.urlencode({k: v for k, v in sorted_items if v is not None})
    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
    out["w_rid"] = w_rid
    return out
```

**示例：**
- 输入参数：`{"csrf": "xxx", "pn": 1}`
- 排序后：`csrf=xxx&pn=1`
- 拼接 mixin_key：`csrf=xxx&pn=1<mixin_key>`
- MD5 得到 `w_rid`

---

## 3. API 总览

### 3.1 使用中的接口（最终方案）

| 接口 | 方法 | 用途 | 是否需要 WBI |
|------|------|------|-------------|
| `/x/web-interface/nav` | GET | 获取 WBI 签名密钥 + 用户信息 | ❌ |
| `/x/dynamic/feed/draw/upload_bfs` | POST | **Opus 图片上传**（首选） | **✅** |
| `/x/dynamic/feed/article/draft/add` | POST | **保存/更新专栏草稿** | **✅** |
| `/x/dynamic/feed/edit/opus` | POST | **编辑已发布专栏文章** | **✅** |
| `/x/article/creative/article/view` | GET | 获取已发布文章详情 | ✅ |
| `/x/article/edit_times` | GET | 查询文章可编辑次数 | ✅ |
| `/x/article/creative/article/upcover` | POST | 图片上传（备用方案） | ❌ |

### 3.2 已验证但未使用的接口

| 接口 | 方法 | 用途 | 备注 |
|------|------|------|------|
| `/x/dynamic/feed/draw/transfer_image` | POST | 从外部 URL 搬运图片到 B站图床 | 可用于网络图片转存 |
| `/x/dynamic/feed/create/opus_init_check` | GET | 获取 Opus 发布权限和配置 | 可获取最大标题长度(50)、最大正文(10万)、最大图片数(100)等 |
| `/x/article/creative/draft/list` | GET | 获取草稿列表 | 可列出所有草稿 |
| `/x/kv-frontend/namespace/data` | GET | 获取 KV 存储配置 | 编辑器内部使用 |
| `/x/web-frontend/risk/config` | GET | 获取风控配置 | 获取验证码 SDK 地址 |

### 3.3 其他发现的接口

| 接口 | 方法 | 用途 | 来源 |
|------|------|------|------|
| `/x/v2/dynamic/sunflower/parse` | POST | 解析文本中的链接/卡片 | 编辑器 JS 源码 |
| `//member.bilibili.com/x/web/white` | GET | 白名单检查 | 编辑器启动时调用 |
| `//member.bilibili.com/platform/upload-manager/opus` | - | Opus 上传管理器页面 | 编辑器 JS 中引用的路径 |

---

## 4. Opus 内容格式

这是整个 API 的核心——**Opus 内容模型**。
文章正文由 `paragraphs`（段落数组）构成。

> 📄 **完整指南见 [`PAYLOAD_GUIDE.md`](PAYLOAD_GUIDE.md)**
> 对照 [`bilibili_保存到草稿箱_example_payload.json`](bilibili_保存到草稿箱_example_payload.json) 逐层详解所有段落类型和节点格式。

### 4.1 整体结构

```json
{
  "arg": {
    "type": 4, "template_id": 1, "category_id": 15,
    "title": "文章标题", "article_id": 350788,
    "image_urls": ["https://..."],
    "summary": "摘要...",
    "opus": {
      "opus_source": 2, "title": "文章标题",
      "content": { "paragraphs": [...] },
      "pub_info": { "editor_version": "eva3-3.0.0" },
      "attachments": { "is_aigc": 0 }
    }
  }
}
```

### 4.2 段落类型一览

| `para_type` | 类型 | 说明 |
|:---:|------|------|
| `1` | 文本段落 | 普通正文（含内联节点） |
| `2` | 图片段落 | `pic.pics[]` 数组 |
| `3` | 分隔线 | `line.line_type=1` |
| `4` | 引用段落 | 块引用，同组共享 `combine_hash` |
| `5` | 有序列表 | `list_format.theme`: arabic_num / lower_letter / roman_num |
| `6` | 无序列表 | `list_format.theme`: dot / square / circle |
| `8` | 代码块 | `code.lang` + `code.content` |
| `9` | 标题段落 | `heading_type: 1/2/3` |

### 4.3 节点类型一览

| `node_type` | 类型 | 说明 |
|:---:|------|------|
| `1` | 文本节点 | `word` 包含文字和样式 |
| `2` | 表情 | `emote.raw_text`，如 `[doge_金箍]` |
| `4` | 超链接 | `link` 包含 URL 和展示文字 |
| `5` | 公式 | `formula.latex_content` |

### 4.4 字体级别

| `font_level` | 用途 | `font_size` |
|--------------|------|:-----------:|
| `"xxLarge"` | 一级标题 | `24` |
| `"xLarge"` | 二级标题 | `22` |
| `"large"` | 三级标题 | `20` |
| `"regular"` | 普通正文 | `17` |
| `"small"` | 极小字号 | `13` |

### 4.5 文本样式

```json
{"bold": true}          // 加粗
{"italic": true}        // 斜体
{"underline": true}     // 下划线
{"strikethrough": true} // 删除线
```

### 4.6 图片段落 (`para_type: 2`)

```json
{
  "para_type": 2,
  "pic": {
    "pics": [{
      "url": "https://i0.hdslb.com/bfs/new_dyn/xxxxx.png",
      "width": 2479, "height": 1463,
      "size": 1147.22, "ai_gen_pic": 0,
      "comment": "图片描述（可选）"
    }],
    "style": 0
  }
}
```

### 4.7 编辑器渲染后的 HTML

当 Opus 内容被编辑器渲染后（仅供理解编辑器行为）：

| Opus 段落 | 渲染的 HTML |
|-----------|-------------|
| 文本段落 | `<p><span>...</span></p>` |
| H1 标题 | `<p><span><strong>标题</strong></span></p>` |
| 图片段落 | `<div class="eva3-enhanced-image-wrapper"><figure><img src="..."></figure></div>` |
| 分隔线 | `<hr>` |
| 加粗 | `<strong>` |
| 斜体 | `<em>` |
| 删除线 | `<s>` |
| 行内代码 | `<span style="color: rgb(199, 37, 78);">` |

---

## 5. 接口详解

### 5.1 获取用户信息和 WBI 密钥

```
GET https://api.bilibili.com/x/web-interface/nav
```

**认证：** 需要 Cookie（用于获取登录用户信息），
但即使未登录也能获取 `wbi_img`（WBI 密钥）。

**响应：**
```json
{
  "code": 0,
  "data": {
    "isLogin": true,
    "uname": "用户名",
    "mid": 1349647254,
    "level_info": {
      "current_level": 3,
      "current_exp": 1605,
      "next_exp": 4500
    },
    "wbi_img": {
      "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png",
      "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png"
    }
  }
}
```

**提取 WBI 密钥的 Python 代码：**
```python
wbi_img = response["data"]["wbi_img"]
img_key = wbi_img["img_url"].split("/")[-1].split(".")[0]
sub_key = wbi_img["sub_url"].split("/")[-1].split(".")[0]
```

---

### 5.2 Opus 图片上传（首选）

```
POST https://api.bilibili.com/x/dynamic/feed/draw/upload_bfs
```

**认证：** 需要 Cookie + WBI 签名 + CSRF

**查询参数：**
| 参数 | 值 |
|------|-----|
| `csrf` | Cookie 中的 `bili_jct` |
| `w_rid` | WBI 签名 |
| `wts` | WBI 时间戳 |
| `biz` | `"new_dyn"` |
| `category` | `"daily"` |

**请求体：** `multipart/form-data`
| 字段 | 说明 |
|------|------|
| `file_up` | 图片文件（支持 jpg/png/gif/webp/bmp） |
| `biz` | `"new_dyn"` |
| `category` | `"daily"` |
| `csrf` | Cookie 中的 `bili_jct` |

**响应：**
```json
{
  "code": 0,
  "data": {
    "image_url": "http://i0.hdslb.com/bfs/new_dyn/xxxxx.png",
    "image_width": 2479,
    "image_height": 1463,
    "img_size": 1147.22,
    "ai_gen_pic": 0
  }
}
```

> ⚠️ `image_url` 返回的是 `http://` 开头的 URL。
> B站 编辑器会自动升级为 HTTPS（Chrome 的 Mixed Content 自动升级），
> 但通过 API 保存时**必须替换为 `https://`**，否则 API 会报错 `[37130] 内容包含非法图片链接`。

**Python 调用示例：**
```python
url = "https://api.bilibili.com/x/dynamic/feed/draw/upload_bfs"
params = sign_wbi({"csrf": csrf, "biz": "new_dyn", "category": "daily"})
files = {"file_up": ("image.png", open("image.png", "rb"), "image/png")}
data = {"biz": "new_dyn", "category": "daily", "csrf": csrf}
response = session.post(url, params=params, files=files, data=data)
result = response.json()
image_url = result["data"]["image_url"].replace("http://", "https://")
```

---

### 5.3 旧版封面/图片上传（备用）

```
POST https://api.bilibili.com/x/article/creative/article/upcover
```

**认证：** 需要 Cookie + CSRF（不需要 WBI 签名）

**请求体：** `multipart/form-data`
| 字段 | 说明 |
|------|------|
| `binary` | 图片文件 |
| `cover` | 留空字符串 `""` |
| `csrf` | Cookie 中的 `bili_jct` |

**响应：**
```json
{
  "code": 0,
  "data": {
    "url": "http://i0.hdslb.com/bfs/.../xxxxx.png"
  }
}
```

> 这个接口原本用于上传**专栏封面**，但也能上传正文图片。
> 返回的 URL 同样是 `http://`，需要替换为 `https://`。
> 此接口没有图片尺寸信息，需自行从文件获取。

---

### 5.4 外部图片搬运

```
POST https://api.bilibili.com/x/dynamic/feed/draw/transfer_image
```

**用途：** 将外部 URL 的图片复制到 B站 图床（编辑器 JS 中的 `transferHandler`）

**认证：** 需要 Cookie

**请求体：**
```json
{
  "origin_path": "https://example.com/image.png",
  "upload_params": {
    "biz": "new_dyn"
  }
}
```

**响应：**
```json
{
  "code": 0,
  "data": {
    "image_url": "http://i0.hdslb.com/bfs/new_dyn/xxxxx.png",
    "image_width": 800,
    "image_height": 600,
    "img_size": 123.45,
    "ai_gen_pic": 0
  }
}
```

> 此接口在编辑器中用于处理粘贴外部图片链接的场景。

---

### 5.5 保存/更新专栏草稿（核心）

```
POST https://api.bilibili.com/x/dynamic/feed/article/draft/add
```

**认证：** 需要 Cookie + WBI 签名 + CSRF

**查询参数：**
| 参数 | 说明 |
|------|------|
| `csrf` | Cookie 中的 `bili_jct` |
| `w_rid` | WBI 签名 |
| `wts` | WBI 时间戳 |

**请求体结构：**
```json
{
  "arg": {
    "type": 4,
    "template_id": 1,
    "category_id": 15,
    "article_id": 350758,
    "title": "文章标题",
    "private_pub": 2,
    "reprint": 1,
    "original": 0,
    "list_id": 0,
    "comment_selected": 0,
    "up_closed_reply": 0,
    "timer_pub_time": 0,
    "only_fans_level": 0,
    "only_fans_dnd": 0,
    "summary": "摘要文本（前250字）",
    "opus": {
      "opus_source": 2,
      "title": "文章标题",
      "content": {
        "paragraphs": [...]
      }
    }
  }
}
```

**`arg` 字段详解：**

| 字段 | 类型 | 说明 | 首次创建 | 更新草稿 |
|------|------|------|:--------:|:--------:|
| `type` | number | 固定为 `4`（文章类型） | ✅ | ✅ |
| `template_id` | number | 固定为 `1` | ✅ | ✅ |
| `category_id` | number | 分区 ID（默认 `15`=生活） | ✅ | ✅ |
| `article_id` | number | 草稿 ID | ❌ | ✅ |
| `title` | string | 文章标题（≤50字） | ✅ | ✅ |
| `private_pub` | number | 可见性：`2`=公开, `1`=仅自己可见 | ✅ | ✅ |
| `reprint` | number | 转载：`1`=禁止转载, `0`=允许转载 | ✅ | ✅ |
| `original` | number | 原创声明：`0`=不声明, `1`=声明原创 | ✅ | ✅ |
| `list_id` | number | 文集 ID（`0`=不加入文集） | ✅ | ✅ |
| `comment_selected` | number | 精选评论：`0`=关闭, `1`=开启 | ✅ | ✅ |
| `up_closed_reply` | number | 关闭评论：`0`=允许, `1`=关闭 | ✅ | ✅ |
| `timer_pub_time` | number | 定时发布时间戳（`0`=立即发布） | ✅ | ✅ |
| `only_fans_level` | number | 仅粉丝可见等级（`0`=不限） | ✅ | ✅ |
| `only_fans_dnd` | number | 粉丝可见免打扰 | ✅ | ✅ |
| `summary` | string | 摘要（纯文本，前 250 字） | ✅ | ✅ |
| `opus` | object | Opus 内容体（见下文） | ✅ | ✅ |

**`opus` 字段详解：**

```json
{
  "opus_source": 2,
  "title": "文章标题",
  "content": {
    "paragraphs": [...]
  }
}
```

| 字段 | 说明 |
|------|------|
| `opus_source` | 固定为 `2`（Web 编辑器） |
| `title` | 与 `arg.title` 相同 |
| `content.paragraphs` | 段落数组（见第4章） |

**响应：**
```json
{
  "code": 0,
  "message": "OK",
  "data": {
    "article_id": 350758
  }
}
```

**关键行为：**
- **首次调用**（不传 `article_id`）：创建新草稿，返回新 `article_id`
- **后续调用**（传入 `article_id`）：更新已有草稿
- **自动保存冲突**：如果草稿在浏览器中被编辑过（有更新的版本），
  直接更新会报错 `[47015] 当前版本较低 请升级最新版App后再编辑该专栏`，
  此时需创建新草稿。

---

### 5.6 Opus 发布权限检查

```
GET https://api.bilibili.com/x/dynamic/feed/create/opus_init_check
```

**查询参数：**
| 参数 | 说明 |
|------|------|
| `web_location` | `"333.40205"` 或 `"333.1305"` |
| `editor_version` | `"eva3-3.0.0"`（可选） |
| `w_rid` | WBI 签名（可选） |
| `wts` | WBI 时间戳（可选） |

**响应：**
```json
{
  "code": 0,
  "data": {
    "permission": {
      "items": [
        {"type": 18, "permission": 1, "title": "AI辅助创作声明", ...},
        {"type": 6, "permission": 1, "title": "关闭评论", ...},
        {"type": 5, "permission": 1, "title": "精选评论", ...}
      ]
    },
    "config": {
      "min_title_len": 1,
      "max_title_len": 50,
      "max_article_len": 100000,
      "max_image_count": 100,
      "max_card_count": 100,
      "max_hashtag_len": 30
    }
  }
}
```

> 可获取发布配置上限：标题最大 50 字、正文最大 10 万字、图片最多 100 张。

---

### 5.7 草稿列表

```
GET https://api.bilibili.com/x/article/creative/draft/list
```

**查询参数：**
| 参数 | 说明 |
|------|------|
| `pn` | 页码（从 1 开始） |
| `ps` | 每页数量（最大 50） |
| `keyword` | 搜索关键字 |
| `web_location` | `"333.40205"` |

**响应：**
```json
{
  "code": 0,
  "data": {
    "artlist": [
      {
        "id": 350758,
        "title": "专栏标题",
        "summary": "正文摘要",
        "ptime": "2026-06-02 21:57:28",
        ...
      }
    ]
  }
}
```

---

## 6. 附录：常用分区 ID

| ID | 分区 |
|:--:|------|
| `2` | 动画 |
| `3` | 音乐 |
| `4` | 游戏 |
| `5` | 娱乐 |
| `15` | 生活（默认） |
| `17` | 单机游戏 |
| `22` | 影视 |
| `26` | 时尚 |
| `36` | 知识 |
| `72` | 美食 |

---

## 7. 附录：错误码速查

| 错误码 | 含义 | 处理建议 |
|:-----:|------|----------|
| `0` | 成功 | - |
| `-101` | 账号未登录 | Cookie 无效/过期，重新获取 |
| `-111` | CSRF 校验失败 | `bili_jct` 不匹配或缺失 |
| `-304` | 未修改 | 数据相同，无需更新 |
| `37130` | 内容包含非法图片链接 | 图片 URL 需使用 HTTPS |
| `47015` | 当前版本较低 | 草稿已在新版本中被编辑，需重新创建 |
| `47011` | 参数错误 | 检查请求参数字段 |

---

## 8. 总结：完整请求流程

```
┌─────────────────────────────────────────────────────┐
│ 1. 从浏览器获取 Cookie                              │
│    完整 Cookie → BILIBILI_COOKIE                    │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│ 2. 获取 WBI 密钥                                     │
│    GET /x/web-interface/nav                          │
│    提取 img_key + sub_key → mixin_key                │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│ 3. 上传图片（每张图调用一次）                         │
│    POST /x/dynamic/feed/draw/upload_bfs              │
│    + WBI 签名 + FormData(file_up, biz, category)     │
│    → 获取 HTTPS 图片 URL                              │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│ 4. 解析 Markdown → Opus paragraphs                   │
│    - # H1 → text node, font_level=h1, bold           │
│    - ## H2 → text node, font_level=h2, bold          │
│    - ### H3 → text node, bold                        │
│    - ** ** → bold style                              │
│    - * * → italic style                              │
│    - ~~ ~~ → strikethrough style                     │
│    - `code` → red color text                         │
│    - ![alt](path) → para_type=2, pic.pics[].url     │
│    - --- → para_type=3, line.line_type=1             │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│ 5. 保存草稿                                          │
│    POST /x/dynamic/feed/article/draft/add            │
│    + WBI 签名 + JSON body(arg)                       │
│    → 获取 article_id                                  │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│ 6. 编辑已发布文章                                     │
│    POST /x/dynamic/feed/edit/opus                   │
│    + WBI 签名                                        │
│    Body: { raw_content, opus_req, dyn_id_str }       │
│    → dyn_id_str, dyn_type, dyn_rid                   │
│                                                      │
│    opus_req 字段:                                    │
│    - upload_id: "{mid}_{timestamp}_{random}"         │
│    - opus: 与草稿相同的 Opus 内容体                   │
│    - scene: 12                                       │
│    - meta: {"app_meta": {"from": "edit.creative.h5", │
│              "mobi_app": "web"}}                     │
│    - option: {"aigc":2, "close_comment":0,           │
│               "up_choose_comment":0}                 │
│    - topic: { id, name } (可选)                      │
│    opus.article: { category_id, list_id,             │
│                    originality, reproduced, cover }   │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│ 7. 在浏览器中查看                                     │
│    https://member.bilibili.com/platform/upload/      │
│    text/new-edit?aid={article_id}                    │
└─────────────────────────────────────────────────────┘
```

---

> 本文档基于对 B站 创作中心 Web 版（EVA3 编辑器）的实际抓包分析编写，
> 接口和行为可能随 B站 前端更新而变化。
> 最后更新：2026-07-12
