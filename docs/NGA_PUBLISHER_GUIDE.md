# NGA 发布器实现指南

> 本文档详细记录了 NGA（Ngabbs.com / bbs.nga.cn）论坛的发布机制、API 接口、
> 图片上传流程和发帖实现，用于指导 `article-publisher` 项目中 NGA 发布器的开发与维护。

---

## 目录

1. [概述](#1-概述)
2. [架构概览](#2-架构概览)
3. [认证机制](#3-认证机制)
4. [图片上传](#4-图片上传)
5. [帖子提交](#5-帖子提交)
6. [编辑已有帖子](#6-编辑已有帖子)
7. [IR → NGA BBCode 转换](#7-ir--nga-bbcode-转换)
8. [完整执行流程](#8-完整执行流程)
9. [常见问题](#9-常见问题)

---

## 1. 概述

### 1.1 什么是 NGA

NGA（艾泽拉斯国家地理论坛）是国内最大的游戏社区之一。其帖子使用类 BBCode 的标记语言
进行排版。本项目实现了将 Markdown / 飞书云文档自动转换为 NGA BBCode 并发布到论坛的功能。

### 1.2 关键技术点

| 技术点         | 说明                                                                  |
| -------------- | --------------------------------------------------------------------- |
| **编码**       | NGA 使用 **GBK/GB18030** 编码（`__CHARSET = 'GBK'`）                  |
| **发帖接口**   | `POST https://bbs.nga.cn/post.php`，application/x-www-form-urlencoded |
| **图片上传**   | `POST https://img8.nga.cn/attach.php?`，multipart/form-data           |
| **API 网关**   | `https://bbs.nga.cn/nuke.php?`（用于其他操作）                        |
| **图片 CDN**   | `https://img.nga.178.com/attachments/`                                |
| **认证方式**   | Cookie 认证（`ngaPassportCid` + 相关 cookies）                        |
| **Auth Token** | 临时上传令牌，从发帖页面 HTML 中提取                                  |

---

## 2. 架构概览

```
用户输入:  Markdown / 飞书文档 + NGA_COOKIE + --fid
                    │
                    ▼
          ┌─────────────────────┐
          │   MarkdownConverter  │  (或 LarkDocxConverter)
          │   (已有代码)          │
          └─────────┬───────────┘
                    │
                    ▼
          ┌─────────────────────┐
          │   IR Document        │  ← 平台无关的中间表示
          └─────────┬───────────┘
                    │
          ┌─────────▼───────────┐
          │   NgaPublisher       │  ← 本指南主要描述的模块
          │                      │
          │   ① 获取 auth token  │
          │   ② 上传所有图片     │
          │   ③ 转换为 BBCode    │
          │   ④ 提交到 post.php  │
          └─────────┬───────────┘
                    │
                    ▼
          ┌─────────────────────┐
          │   NGA 帖子 ✓         │
          │   https://bbs.nga.cn │
          │   /read.php?tid=xxx  │
          └─────────────────────┘
```

### 2.1 核心类

| 类                 | 文件           | 职责                                                          |
| ------------------ | -------------- | ------------------------------------------------------------- |
| `NgaClient`        | `client.py`    | HTTP 客户端：Cookie 管理、auth token 获取、图片上传、帖子提交 |
| `NgaPublisher`     | `publisher.py` | IR → BBCode 转换，编排上传和发帖流程                          |
| `NgaPublishConfig` | `publisher.py` | 发布配置（fid、输出路径）                                     |
| `UploadedImage`    | `client.py`    | 图片上传结果（URL、attachment 数据）                          |

---

## 3. 认证机制

### 3.1 Cookie 认证

用户需要提供登录后的 Cookie 字符串。关键 Cookie：

```
ngaPassportCid=EXAMPLE_cid_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  # 会话 ID（httpOnly）
ngaPassportUid=12345678                                          # 用户 ID
ngaPassportUrlencodedUname=ExampleUser                           # 用户名
ngacn0comUserInfo=ExampleUser%09...                              # 用户信息
ngacn0comUserInfoCheck=example_md5_hash_32char_xxxxxxxxxxxxxx    # 会话校验（会变化）
ngacn0comInfoCheckTime=2000000000                                # 校验时间戳
```

> ⚠️ **`ngacn0comUserInfoCheck` 和 `ngacn0comInfoCheckTime` 会定期过期**，
> 需要重新从浏览器获取。

在 Python 中的设置方式：

```python
import requests

session = requests.Session()
session.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://bbs.nga.cn/",
        "Origin": "https://bbs.nga.cn",
    }
)

# 解析 Cookie 字符串并设置（domain 设为 .nga.cn 以覆盖所有子域）
for pair in cookie_str.split(";"):
    pair = pair.strip()
    if "=" in pair:
        key, value = pair.split("=", 1)
        session.cookies.set(key.strip(), value.strip(), domain=".nga.cn")
```

### 3.2 Auth Token（图片上传专用）

图片上传需要一个额外的 `auth` 令牌，通过访问发帖页面从服务器获取。

**请求：**

```
GET https://bbs.nga.cn/post.php?action=new&_newui=&fid=-34587507
Cookie: <用户登录 Cookie>
```

**响应中的关键片段：**

```html
<script>
var __U = {
    "action": "new",
    "fid": -34587507,
    "auth": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "attach_url": "https://img8.nga.cn/attach.php",
    // ... 其他字段
};
// ...
</script>
```

**提取 auth 的 Python 代码：**

```python
import re

resp = session.get(
    "https://bbs.nga.cn/post.php",
    params={"action": "new", "_newui": "", "fid": -34587507},
)

# 检查是否被重定向到登录页
if "login" in resp.url.lower():
    raise Exception("Cookie 已过期")

# 提取 auth token
match = re.search(
    r'"auth"\s*:\s*"([a-f0-9]+)"', resp.text.replace("\n", " ").replace("\r", "")
)
auth_token = match.group(1)
```

> ⚠️ **auth token 是临时性的**，与当前 session 绑定。不同请求获取的 auth 不同。
> 校验和（`attachments_check`）与 auth token 绑定，因此**必须使用同一个 session
> 完成上传和发帖**——否则校验和会不匹配。

---

## 4. 图片上传

### 4.1 请求结构

**Endpoint:** `POST https://img8.nga.cn/attach.php?`

**Content-Type:** `multipart/form-data`

**请求字段（按顺序）：**

| 字段名                           | 值示例                                    | 说明               |
| -------------------------------- | ----------------------------------------- | ------------------ |
| `attachment_file1_dscp`          | `(空)`                                    | 图片描述           |
| `attachment_file1_img`           | `1`                                       | 作为图片           |
| `attachment_file1_auto_size`     | `8`                                       | 自动尺寸           |
| `attachment_file1_watermark`     | `(空)`                                    | 水印               |
| `func`                           | `upload`                                  | 固定值             |
| `v2`                             | `1`                                       | 版本号             |
| `origin_domain`                  | `bbs.nga.cn`                              | 来源域名           |
| `__output`                       | `1`                                       | JSON 输出          |
| `auth`                           | `03a0xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxf8ed` | 认证令牌           |
| `fid`                            | `-34587507`                               | 版块 ID            |
| `attachment_file1_url_utf8_name` | `image%2epng`                             | URL 编码的原文件名 |
| `attachment_file1`               | `(binary)`                                | 图片文件           |

### 4.2 完整请求示例

```
POST https://img8.nga.cn/attach.php?
Content-Type: multipart/form-data; boundary=----WebKitFormBoundaryjkYfLwppwB8ACBBX

------WebKitFormBoundaryjkYfLwppwB8ACBBX
Content-Disposition: form-data; name="attachment_file1_dscp"

------WebKitFormBoundaryjkYfLwppwB8ACBBX
Content-Disposition: form-data; name="attachment_file1_img"
1
------WebKitFormBoundaryjkYfLwppwB8ACBBX
Content-Disposition: form-data; name="func"
upload
------WebKitFormBoundaryjkYfLwppwB8ACBBX
Content-Disposition: form-data; name="v2"
1
------WebKitFormBoundaryjkYfLwppwB8ACBBX
Content-Disposition: form-data; name="__output"
1
------WebKitFormBoundaryjkYfLwppwB8ACBBX
Content-Disposition: form-data; name="auth"
03a0xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxf8ed
------WebKitFormBoundaryjkYfLwppwB8ACBBX
Content-Disposition: form-data; name="fid"
-34587507
------WebKitFormBoundaryjkYfLwppwB8ACBBX
Content-Disposition: form-data; name="attachment_file1_url_utf8_name"
image%2epng
------WebKitFormBoundaryjkYfLwppwB8ACBBX
Content-Disposition: form-data; name="attachment_file1"; filename="image.png"
Content-Type: image/png

<binary>
------WebKitFormBoundaryjkYfLwppwB8ACBBX--
```

### 4.3 响应格式

```javascript
window.script_muti_get_var_store = {
    "data": {
        "attachments": "fid~-34587507~watermark~~aid~-klbw3Q6-3gsh~ext~webp~url_utf8_org_name~image%2epng~path~mon_202606/08~url_dscp~~size~140332~name~-klbw3Q6-3gshZeT3cS1wv-14n.webp~tmp_file~/data1/img.nga.cn/temp_attachments/-klbw3Q6-3gsh.png.tmp.webp~isanimg~0~tmp_shoot_size~140332~isimg~1~w~2479~h~1463~thumb~120",
        "attachments_check": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "url": "mon_202606/08/-klbw3Q6-3gshZeT3cS1wv-14n.webp",
        "isImg": "1",
        "thumb": "120",
        "isVideo": "0"
    }
}
```

### 4.4 关键响应字段详解

| 字段                | 说明                             | 用途                               |
| ------------------- | -------------------------------- | ---------------------------------- |
| `attachments`       | 附件信息字符串（~ 分隔的键值对） | 发帖时必须提交                     |
| `attachments_check` | 32 位 MD5 校验和                 | 发帖时必须提交，与 auth 绑定       |
| `url`               | 图片相对路径                     | 正文中用 `[img]./{url}[/img]` 引用 |

**attachments 字段解析：**

```
fid~-34587507~          ← 版块 ID
watermark~~             ← 水印（空）
aid~-klbw3Q6-3gsh~     ← 附件 ID（唯一标识）
ext~webp~               ← 扩展名（NGA 自动转为 webp）
url_utf8_org_name~image%2epng~  ← 原始文件名（URL 编码）
path~mon_202606/08~    ← 存储路径
url_dscp~~              ← 描述（空）
size~140332~            ← 文件大小
name~-klbw3Q6-3gshZeT3cS1wv-14n.webp~  ← 保存的文件名
tmp_file~/data1/img.nga.cn/temp_attachments/...  ← 临时文件路径
isanimg~0~              ← 非动画
tmp_shoot_size~140332~  ← 临时文件大小
isimg~1~                ← 是图片
w~2479~                 ← 宽度
h~1463~                 ← 高度
thumb~120               ← 缩略图
```

### 4.5 图片引用方式

上传后在正文中使用**相对路径**引用：

```
[img]./mon_202606/08/-klbw3Q6-3gshZeT3cS1wv-14n.webp[/img]
```

NGA 服务器在发布帖子时会自动将 `./mon_xxx/...` 解析为完整 CDN URL。

NGA 还会自动生成多尺寸缩略图：
- `.medium.jpg` — 中等尺寸
- `.thumb.jpg` — 320x240
- `.thumb_s.jpg` — 130x97
- `.thumb_ss.jpg` — 60x45

### 4.6 Python 实现

```python
def upload_image(self, file_path: Path) -> UploadedImage:
    auth = self.get_auth_token()
    file_name = file_path.name

    with open(file_path, "rb") as f:
        files = {
            "func": (None, "upload"),
            "v2": (None, "1"),
            "origin_domain": (None, "bbs.nga.cn"),
            "__output": (None, "1"),
            "auth": (None, auth),  # 关键：auth token
            "fid": (None, str(self.fid)),  # 关键：版块 ID
            "attachment_file1_url_utf8_name": (
                None,
                requests.utils.quote(file_name, safe=""),
            ),
            "attachment_file1": (file_name, f, "application/octet-stream"),
        }
        resp = self._session.post(ATTACH_UPLOAD_URL, files=files)

    # 解析响应...
    return UploadedImage(
        url=result["url"],
        attachment_str=result["attachments"],
        attachment_check=result["attachments_check"],
    )
```

---

## 5. 帖子提交

### 5.1 最重要的发现

> ⚠️ **图片必须通过 `attachments` 和 `attachments_check` 字段与帖子绑定。**
>
> 如果只提交 BBCode 而不附带附件数据，服务器不知道这些图片属于当前帖子，
> 图片将不可见（CDN 返回 404 / 浏览器拦截）。

### 5.2 请求结构

**Endpoint:** `POST https://bbs.nga.cn/post.php`

**Content-Type:** `application/x-www-form-urlencoded`

**编码:** GBK（所有中文字段必须先编码为 GBK，再 URL 编码）

### 5.3 完整请求示例

```
POST https://bbs.nga.cn/post.php
Content-Type: application/x-www-form-urlencoded

action=new&
fid=-34587507&
post_subject=%27%C5%DD...%27%BB%F9%BD%A8%BD%E2%CE%F6&
post_content=%5Bimg%5D.%2Fmon_202...%2Ewebp%5B%2Fimg%5D&
attachments=fid%7E-34587507%7Ewatermark%7E%7Eaid%7E-klbw3Q6-bbnh%7E...%7Ethumb%7E120%09&
attachments_check=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx%09&
hidden=2&
nojump=1&
lite=htmljs&
step=2
```

### 5.4 参数详解

| 参数                        | 必需      | 说明                                                  |
| --------------------------- | --------- | ----------------------------------------------------- |
| `action`                    | ✅         | `new`=新帖, `reply`=回复, `modify`=编辑, `quote`=引用 |
| `fid`                       | ✅         | 版块 ID（如 `-34587507`）                             |
| `tid`                       | 编辑时    | 主题 ID                                               |
| `post_subject`              | ✅         | 标题                                                  |
| `post_content`              | ✅         | **正文（BBCode 格式）**                               |
| `attachments`               | 有图片时✅ | **tab 分隔的附件信息字符串**                          |
| `attachments_check`         | 有图片时✅ | **tab 分隔的 MD5 校验和**                             |
| `hidden`                    |           | `2`=公开, `1`=版主可见                                |
| `self_reply`                |           | 仅作者和版主可回复                                    |
| `anony`                     |           | `1`=匿名                                              |
| `mention`                   |           | @提醒                                                 |
| `newvote` ~ `newvote_limit` |           | 投票相关                                              |
| `nojump`                    | ✅         | `1`=不跳转                                            |
| `lite`                      | ✅         | `htmljs`                                              |
| `step`                      | ✅         | `2`                                                   |
| `__inchst`                  |           | `UTF-8`（告知服务器输入为 UTF-8）                     |

### 5.5 attachments 和 attachments_check 的拼接规则

**前端核心代码（来自 `add1Attach` 函数）：**

```javascript
// 每次上传成功后，将附件信息追加到隐藏字段
this.o_attach.value += attach + '\t';       // tab 分隔多个附件
this.o_attachChk.value += checkSum + '\t';  // tab 分隔多个校验和
```

**多张图片时的拼接结果：**

```
attachments = "fid~...aid1~...~thumb~120\tfid~...aid2~...~thumb~24\t"
attachments_check = "hash1\thash2\t"
```

**Python 实现：**

```python
attach_value = "\t".join(attachment_strings) + "\t"
attach_check_value = "\t".join(attachment_checks) + "\t"
```

### 5.6 编码处理详解

NGA 使用 GBK 编码。从 Python 发帖时需手动编码：

```python
import urllib.parse

# 需要 GBK 编码的字段（含中文）
data = {
    "post_subject": "标题",
    "post_content": "[b]正文[/b]",
    # 其他 ASCII 字段...
}

body_parts = []
for key, value in data.items():
    k_enc = urllib.parse.quote(key.encode("gbk"), safe="")
    if key in ("post_subject", "post_content"):
        # 中文字段：GBK 编码 → URL 编码
        v_enc = urllib.parse.quote(value.encode("gbk", errors="replace"), safe="")
    else:
        # ASCII 字段：直接 URL 编码
        v_enc = urllib.parse.quote(value, safe="")
    body_parts.append(f"{k_enc}={v_enc}".encode("gbk"))

body = b"&".join(body_parts)
resp = session.post(
    "https://bbs.nga.cn/post.php",
    data=body,
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)
```

### 5.7 响应格式

**成功响应：**

```javascript
window.script_muti_get_var_store = {
    "error": {
        "0": "发贴完毕 ...",       // ← "发贴完毕" 表示成功
        "1": "",
        "2": "46944820"           // ← 新帖子 ID
    },
    "time": 1780888037
}
```

> ⚠️ NGA 用 `error` 字段表示操作结果。"发贴完毕" 不是错误，而是成功。

**失败响应：**

```javascript
window.script_muti_get_var_store = {
    "error": {
        "0": "2048:attach checksum error, please report to administrator",
        "1": "",
        "2": ""
    },
    "data": {
        "__MESSAGE": {
            "0": 2048,
            "1": "attach checksum error, please report to administrator",
            "3": 200
        }
    },
    "encode": "gbk",
    "time": 1780888037
}
```

**Python 响应解析：**

```python
def _parse_post_response(text: str) -> dict:
    match = re.search(
        r"window\.script_muti_get_var_store\s*=\s*(\{.+?\})", text, re.DOTALL
    )
    if not match:
        return {"error": {"0": f"无法解析响应: {text[:200]}"}}

    import json

    return json.loads(match.group(1))


# 判断成功/失败
result = _parse_post_response(text)
error_text = result.get("error", {}).get("0", "")
if error_text and "完毕" in error_text:
    print("成功！帖子 ID:", result.get("error", {}).get("2", ""))
elif error_text:
    print("失败:", error_text)
```

### 5.8 完整发帖流程（关键！）

```python
# ⚠️ 必须使用同一个 session 完成以下所有步骤

# 1. 创建 session（含 Cookie）
client = NgaClient(cookie_str, fid)

# 2. 上传所有图片（自动获取 auth token）
for img in images:
    uploaded = client.upload_image(img)
    attachment_strings.append(uploaded.attachment_str)
    attachment_checks.append(uploaded.attachment_check)

# 3. 生成 BBCode
bbcode = convert_to_bbcode(doc, images_uploaded)

# 4. 提交帖子（使用同一个 session！）
result = client.submit_post(
    subject=title,
    content=bbcode,
    attachment_strings=attachment_strings,
    attachment_checks=attachment_checks,
)
```

> 🔑 **关键：** `submit_post()` 与 `upload_image()` 使用**同一个 `requests.Session`**，
> 因此使用的 auth token 相同，校验和匹配。

---

## 6. 编辑已有帖子

### 6.1 与发新帖的区别

编辑已有帖子时：
- `action` 从 `new` 改为 **`modify`**
- 需要传入 **`tid`**（主题 ID）
- 已有附件**不会**自动保留，编辑时必须显式处理旧附件

> ⚠️ **关于旧附件的重要说明**
>
> 早期文档认为"已有附件不需要重新提交，NGA 服务器会保留"，但实际测试发现：
> 提交 `action=modify` 时，`attachments` 和 `attachments_check` 字段只包含当前请求中
> 附带的附件数据。如果不包含旧附件的信息，这些旧附件将变为"未被引用"的状态
> （帖子正文中可能还有 `[img]` BBCode 指向它们，但附件绑定关系已被新的附件数据替换）。
>
> 因此，编辑帖子时**必须**：
> 1. 先获取帖子当前的旧附件列表
> 2. **全量删除**所有旧附件（`del_attach` API）
> 3. 重新上传所有新图片
> 4. 提交 `action=modify`，仅携带新上传的附件数据

### 6.2 获取旧附件列表

**Endpoint:** `POST https://ngabbs.com/nuke.php?__lib=attachment&__act=get_recent_attach&__output=3`

**请求格式:** `application/x-www-form-urlencoded`

| 参数  | 类型 | 说明    |
| ----- | ---- | ------- |
| `tid` | int  | 主题 ID |

**完整请求示例：**

```
POST https://ngabbs.com/nuke.php?__lib=attachment&__act=get_recent_attach&__output=3
Content-Type: application/x-www-form-urlencoded

tid=46944336
```

**响应格式（GBK 编码 HTML，内含 JSON）：**

返回 `window.script_muti_get_var_store = { ... }` 格式的 JavaScript 赋值语句。
响应内容包含当前帖子的所有附件列表，每个附件条目包含 `url`、`name`、`size`、
`attachment_str`（即完整的 `fid~...aid~...~thumb~120` 字符串）、`attachments_check`
（MD5 校验和）等信息。

> 该响应体体积较大（约 6.5KB 未压缩），因为包含完整的附件元数据。
> 示例响应文件：`docs/nga_编辑帖子.har` 中第 10309 行附近的 `get_recent_attach` 条目。

### 6.3 删除附件

**Endpoint:** `POST https://ngabbs.com/nuke.php?__lib=del_attach&__act=del_attach&__output=3`

**请求格式:** `application/x-www-form-urlencoded`

| 参数  | 类型   | 说明                                                            |
| ----- | ------ | --------------------------------------------------------------- |
| `tid` | int    | 主题 ID                                                         |
| `pid` | int    | 楼层 ID（主楼为 `0`）                                           |
| `aid` | string | 附件标识符，值为附件数据中的 `name` 字段（即 NGA 存储的文件名） |

**完整请求示例：**

```
POST https://ngabbs.com/nuke.php?__lib=del_attach&__act=del_attach&__output=3
Content-Type: application/x-www-form-urlencoded

tid=46944336&pid=0&aid=-klbw3Q6-e4r9K1kT3cS1hc-u0.webp
```

> ⚠️ **`aid` 参数的值**：传入的是附件数据中 `name` 字段的值（即 NGA 存储端使用的文件名），
> 而非 `attachments` 字段中 `aid~` 后面的短 ID（如 `-klbw3Q6-3gsh`）。完整的 `name`
> 可在上传响应或 `get_recent_attach` 返回的附件数据中找到。

**响应：** 返回 HTML 页面，状态码 200 表示删除成功。
示例响应文件：`docs/nga_删除附件.har`

### 6.4 编辑流程（全量删除 + 全量重新上传）

整体流程如下：

```
                  ┌─────────────────────────┐
                  │  用户提供 --tid 进入编辑模式 │
                  └──────────┬──────────────┘
                             │
                             ▼
                  ┌─────────────────────────┐
                  │  get_recent_attach(tid)   │  ← 获取帖子当前的旧附件列表
                  └──────────┬──────────────┘
                             │
                             ▼
                  ┌─────────────────────────┐
                  │  逐个 delete_attachment()  │  ← 删除所有旧附件
                  └──────────┬──────────────┘
                             │
                             ▼
                  ┌─────────────────────────┐
                  │  上传所有新图片（现有逻辑）   │
                  └──────────┬──────────────┘
                             │
                             ▼
                  ┌─────────────────────────┐
                  │  submit_post(action=modify │  ← 仅携带新上传的附件数据
                  │   + tid, 仅新 attachments) │
                  └─────────────────────────┘
```

1. **获取旧附件列表：** 调用 `get_recent_attach(tid)` 获取所有旧附件数据
2. **全量删除：** 遍历旧附件列表，逐个调用 `delete_attachment(tid, aid)` 删除
3. **上传新图片：** 沿用现有上传逻辑，将所有图片上传到 NGA 图床
4. **提交编辑：** 调用 `submit_post()`，`action=modify`，`attachments` 只包含新上传的附件
5. **清理旧图片（可选）：** 如有需要，可以额外删除本地已无引用但服务器仍残留的附件

> ℹ️ **关于 `subject_not_modify` 和 `content_not_modify`**
>
> 在浏览器编辑帖子时，NGA 前端会发送 `subject_not_modify=1`（标题未修改时）和
> `content_not_modify=1`（正文未修改时）来控制"最后编辑时间"的显示。
> 本项目编辑时始终会提交新的标题和正文，因此不发送这两个参数。

```python
# CLI 调用方式
uv run -m article_publisher --platform nga --fid -34587507 --tid 46944336 markdown articles/article1/main.md

# 内部流程
config = NgaPublishConfig(fid=fid, tid=46944336)  # ← tid 非 None 时为编辑模式
publisher = NgaPublisher(client, config=config)
publisher.publish(doc)  # → 先删旧附件，再上传新图，最后 submit_post(tid=46944336)
```

### 6.5 HAR 参考文件

| 文件                    | 包含的 API                                          |
| ----------------------- | --------------------------------------------------- |
| `docs/nga_编辑帖子.har` | `get_recent_attach`（获取旧附件列表）、编辑页面加载 |
| `docs/nga_删除附件.har` | `del_attach`（删除单个附件）                        |

---

## 7. IR → NGA BBCode 转换

### 6.1 转换映射表

| IR 类型                 | NGA BBCode                         | 说明                                            |
| ----------------------- | ---------------------------------- | ----------------------------------------------- |
| `Heading` (H1)          | `[size=150%][b]标题[/b][/size]`    | NGA 无独立标题标签                              |
| `Heading` (H2)          | `[size=130%][b]标题[/b][/size]`    |                                                 |
| `Heading` (H3)          | `[size=120%][b]标题[/b][/size]`    |                                                 |
| `Paragraph`             | 纯文本                             | 段落间空行分隔                                  |
| `TextRun.bold`          | `[b]text[/b]`                      |                                                 |
| `TextRun.italic`        | `[i]text[/i]`                      | 注意长度限制                                    |
| `TextRun.underline`     | `[u]text[/u]`                      |                                                 |
| `TextRun.strikethrough` | `[del]text[/del]`                  |                                                 |
| `TextRun.color`         | `[color=预设颜色名称]text[/color]` | 所有来源颜色统一优先保持色相，再比较 Oklab 距离 |
| `TextRun.inline_code`   | `[color=crimson]text[/color]`      | 默认来源色 `#c7254e` 映射后的结果               |
| `TextRun.link_url`      | `[url=url]text[/url]`              |                                                 |
| `ImageBlock`            | `[img]./mon_xxx/...[/img]`         | 先上传，后引用                                  |
| `CodeBlock`             | `[code]\ncontent\n[/code]`         |                                                 |
| `Blockquote`            | `[quote]\n...\n[/quote]`           | 支持嵌套                                        |
| `OrderedList`           | `[list=1]\n[*]item[/*]\n[/list]`   |                                                 |
| `UnorderedList`         | `[list]\n[*]item[/*]\n[/list]`     |                                                 |
| `Divider`               | `[h][/h]`                          |                                                 |

### 6.2 BBCode 生成示例

**Markdown 输入：**

```markdown
# 一级标题

**粗体** *斜体* `行内代码`

> 引用内容

- 无序列表 1
- 无序列表 2
```

**生成的 NGA BBCode：**

```
[size=150%][b]一级标题[/b][/size]

[b]粗体[/b] [i]斜体[/i] [color=crimson]行内代码[/color]

[quote]
引用内容
[/quote]

[list]
[*]无序列表 1[/*]
[*]无序列表 2[/*]
[/list]
```

### 6.3 样式嵌套规则

样式从外到内应用（BBCode 解析从外到内）：

```python
from article_publisher.colors import NGA_TEXT_COLORS, nearest_text_color


def _textrun_to_bbcode(self, run: TextRun) -> str:
    text = run.text

    if run.link_url:
        return f"[url={run.link_url}]{text}[/url]"

    # 从外到内包裹样式
    if run.strikethrough:
        text = f"[del]{text}[/del]"
    if run.underline:
        text = f"[u]{text}[/u]"
    if run.italic:
        text = f"[i]{text}[/i]"
    if run.bold:
        text = f"[b]{text}[/b]"

    color = run.color or (_INLINE_CODE_COLOR if run.inline_code else "")
    matched_color = nearest_text_color(color, NGA_TEXT_COLORS)
    if matched_color:
        text = f"[color={matched_color.value}]{text}[/color]"

    return text
```

---

## 8. 完整执行流程

### 8.1 用户操作步骤

```bash
# 1. 在 .env 中配置
#    NGA_COOKIE=ngaPassportUid=xxx; ngacn0comUserInfo=...; ...

# 2. 运行（自动上传图片并发布）
uv run -m article_publisher --platform nga --fid -34587507 markdown articles/article1/main.md

# 3. 帖子发布成功，输出帖子 ID
# 帖子提交成功！tid=46944820
# https://bbs.nga.cn/read.php?tid=46944820
```

### 8.2 程序内部流程

```
┌─────────────────────────────────────────────────────────────┐
│  ① NgaClient.__init__(cookie_str, fid)                      │
│      → 解析 Cookie，创建 requests.Session                   │
│      → session 同时用于上传和发帖（关键！）                  │
├─────────────────────────────────────────────────────────────┤
│  ② 遍历 Document.blocks，对每个 ImageBlock：                │
│      a) NgaClient.get_auth_token()                          │
│         → GET post.php?action=new&fid=xxx                   │
│         → 从页面提取 __U.auth                                │
│      b) NgaClient.upload_image(path)                        │
│         → POST img8.nga.cn/attach.php? (multipart)          │
│         → 返回 UploadedImage(attachment_str, check)         │
│      c) 收集 attachment_str 和 attachment_check             │
├─────────────────────────────────────────────────────────────┤
│  ③ NgaPublisher._convert_document()                        │
│      → IR Block → NGA BBCode                                │
│      → 图片使用 [img]./{url}[/img]                          │
├─────────────────────────────────────────────────────────────┤
│  ④ NgaClient.submit_post(subject, content,                 │
│                           attachment_strings,               │
│                           attachment_checks)                │
│      → 构建 GBK URL-encoded body                            │
│      → POST bbs.nga.cn/post.php                             │
│      → 解析响应，提取帖子 ID                                │
├─────────────────────────────────────────────────────────────┤
│  ⑤ 输出结果                                                │
│      ✅ 帖子提交成功！tid=46944820                          │
└─────────────────────────────────────────────────────────────┘
```

### 8.3 数据流转图

```
上传图片响应:
┌─────────────────────────────────────┐
│  attachments: "fid~...~thumb~120"   │
│  attachments_check: "5fedc8452b..." │
│  url: "mon_202606/08/-xxx.webp"     │
└───────────┬─────────────────────────┘
            │
            ▼ 收集所有图片的 attachment 数据
┌─────────────────────────────────────┐
│  attachment_strings = [             │
│    "fid~...aid1~...~thumb~120",     │
│    "fid~...aid2~...~thumb~24",      │
│  ]                                  │
│  attachment_checks = [              │
│    "5fedc8452b...",                 │
│    "xxxxxxxx...",                   │
│  ]                                  │
└───────────┬─────────────────────────┘
            │
            ▼ 拼接为 tab 分隔的字符串
┌─────────────────────────────────────┐
│  attach_value = "fid~...\tfid~...\t"│
│  attach_check = "hash1\thash2\t"    │
└───────────┬─────────────────────────┘
            │
            ▼ 提交到 post.php
┌─────────────────────────────────────┐
│  POST /post.php                     │
│  action=new                         │
│  fid=-34587507                      │
│  post_subject=标题                   │
│  post_content=[img]...[/img]        │
│  attachments=fid~...\tfid~...\t     │ ← 关键！
│  attachments_check=hash1\thash2\t   │ ← 关键！
│  nojump=1&lite=htmljs&step=2       │
└─────────────────────────────────────┘
```

---

## 9. 常见问题

### 9.1 为什么不能只生成 BBCode 让用户粘贴？

因为 NGA 的图片需要**通过 `attachments` 和 `attachments_check` 字段绑定到帖子**。
这两个字段在用户粘贴 BBCode 时无法自动设置。服务器收到帖子内容中的 `[img]` 标签后，
会去附件系统中查找匹配的附件记录，如果没有（即没提交 `attachments`），图片就不可见。

### 9.2 为什么 checksum 校验失败？

`attachments_check` 是一个与 auth token 绑定的 MD5 校验和。如果：
- 上传图片时用的 auth A
- 提交帖子时用的 auth B（浏览器不同页面）

则校验和会不匹配。**解决方案：用同一个 session 完成上传和发帖。**

### 9.3 为什么图片上传后 CDN 访问 404？

正常现象。NGA 的图片 CDN 做了访问控制，图片只能在 NGA 帖子上下文中正常显示。
`[img]./mon_xxx/...[/img]` 这个相对路径会在帖子发布时由服务器解析。

### 9.4 Cookie 过期怎么办？

需要重新从浏览器获取 Cookie。在浏览器控制台执行：

```javascript
// 获取所有 Cookie 的 Name=Value 格式
document.cookie
```

复制输出到 `.env` 的 `NGA_COOKIE` 字段。

### 9.5 常见错误码

| 错误                         | 原因                      |
| ---------------------------- | ------------------------- |
| 你没有登录                   | Cookie 过期或无效         |
| attach checksum error        | auth token 与校验和不匹配 |
| 内容过短或过长(6~65530 byte) | 编码问题（GBK vs UTF-8）  |
| 发贴完毕                     | **实际上是成功！**        |

---

## 附录：关键常量

```python
# 域名
NGA_BASE = "https://bbs.nga.cn"
ATTACH_UPLOAD_URL = "https://img8.nga.cn/attach.php"
ATTACH_VIEW_BASE = "https://img.nga.178.com/attachments"

# 正文长度限制
CONTENT_MIN_BYTES = 6  # GBK 编码后至少 6 字节
CONTENT_MAX_BYTES = 65530  # GBK 编码后最多 65530 字节

# 图片限制
MAX_IMAGE_SIZE = 4 * 1024 * 1024  # 4MB
SUPPORTED_FORMATS = (".jpg", ".jpeg", ".png", ".gif", ".webp")

# 标题字号
HEADING_SIZE = {1: "150%", 2: "130%", 3: "120%"}

# 行内代码颜色（模拟）
INLINE_CODE_COLOR = "#c7254e"
```
