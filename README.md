# B站 专栏程序化发布工具

将本地 Markdown 文章（支持多级标题、图片、格式化文本）一键发布到 **B站创作中心草稿箱**。

## 快速开始

```bash
# 1. 安装依赖
pip install requests pillow

# 2. 运行（首次会引导输入Cookie）
python main.py articles/article1
```

---

## 文章目录结构

一个专栏项目是一个文件夹，例如 `articles/article1/`：

```
articles/
└── article1/
    ├── main.md          # Markdown 文章正文 (必需)
    └── images/          # 图片文件夹 (可选)
        ├── photo1.png
        └── photo2.jpg
```

### main.md 示例

```markdown
# 这是一级标题 (B站 H1)

## 这是二级标题 (B站 H2)

### 这是三级标题 (B站加粗正文)

这是普通段落。支持 **加粗**、*斜体*、~~删除线~~、`行内代码` 等内联格式。

![第一张图片](images/photo1.png)

---

> 注意：B站专栏不支持标准 Markdown 引用块语法，上面的 `>` 仅用于注释
```

---

## 获取 Cookie（认证信息）

程序需要 **三个 Cookie 字段** 来代表你的账号操作：

| 字段 | 说明 | 保密级别 |
|------|------|----------|
| `SESSDATA` | 登录会话令牌 | ⚠️ 绝对不要泄露！ |
| `bili_jct` | CSRF 防护令牌 | ⚠️ 绝对不要泄露！ |
| `buvid3` | 设备标识符 | 低敏感度 |

### 提取步骤（带图指引）

1. **打开浏览器**，登录 [bilibili.com](https://www.bilibili.com)
2. **进入创作中心** [专栏编辑页](https://member.bilibili.com/platform/upload/text/new-edit)
3. **打开开发者工具**：
   - Chrome/Edge: 按 `F12` 或 `Ctrl+Shift+I`
   - 切换到 **Application（应用）** 选项卡
4. **找到 Cookie**：
   - 左侧展开 **Storage → Cookies**
   - 点击 `https://www.bilibili.com`
5. **复制三个字段的值**：
   - 在右侧列表中找到 `SESSDATA` → 双击 Value 列 → `Ctrl+C` 复制
   - 找到 `bili_jct` → 复制
   - 找到 `buvid3` → 复制

> 💡 **提示**：首次运行 `python main.py articles/article1` 会提示粘贴这三个值，
> 并可选保存到 `config.json`，后续无需重复输入。

---

## 运行

```bash
# 发布 articles/article1 到草稿箱
python main.py articles/article1

# 也可以指定其他文章目录
python main.py articles/我的新文章
```

### 首次运行输出示例

```
============================================================
  B站 认证配置
============================================================
请从浏览器 Cookie 中获取以下三项：

  1. 打开 https://member.bilibili.com 并登录
  2. 按 F12 → Application → Cookies → bilibili.com
  3. 复制以下字段的值：

  SESSDATA: <你粘贴的值>
  bili_jct (CSRF): <你粘贴的值>
  buvid3: <你粘贴的值>

是否保存到 config.json？(y/N): y
配置已保存到 config.json

📄 专栏: D:\BioHazard\...\articles\article1
----------------------------------------
正在解析 Markdown ...
  正在上传图片: ...\images\image.png
    → 上传成功: https://i0.hdslb.com/bfs/.../image.png
  解析完成，共 5 个段落
  摘要: 一级标题 二级标题 三级标题 斜体文本 加粗文本...
正在保存到草稿箱 ...
  ✔ 成功！草稿 ID: 350758

✅ 完成！草稿 ID: 350758
   可在创作中心查看: https://member.bilibili.com/...?aid=350758
```

### 查看草稿

运行成功后，打开 [创作中心 - 专栏草稿](https://member.bilibili.com/platform/upload/text/manage) 即可看到刚保存的草稿，
继续编辑后点击 **发布** 即可公开。

---

## 支持的 Markdown 语法

| Markdown | B站 Opus 效果 |
|----------|--------------|
| `# 标题` | H1 大标题（20px，加粗） |
| `## 标题` | H2 中标题（18px，加粗） |
| `### 标题` | 加粗正文（17px，加粗） |
| `**粗体**` | 加粗样式 |
| `*斜体*` | 斜体样式 |
| `~~删除线~~` | 删除线样式 |
| `` `行内代码` `` | 红色等宽文本 |
| `![描述](images/x.png)` | 图片（自动上传到B站图床） |
| `---` / `***` / `___` | 分隔线 |
| 普通文本段落 | B站正文（17px） |
| 空行分隔 | 段落分隔 |

### 注意事项

- **图片路径**：相对于 `main.md` 所在目录。例如 `images/photo.png`。
- **图片格式**：支持 PNG、JPG、GIF、WebP、BMP。
- **文件大小**：B站单张图片限制通常为 10MB 以内。
- **标题长度**：建议 30 字以内，最多 50 字。
- **正文长度**：最多 100,000 字。

---

## 配置文件

认证信息可保存在项目根目录的 `config.json` 中：

```json
{
  "SESSDATA": "8617220d%2...",
  "bili_jct": "8f40195bf...",
  "buvid3": "9DCA061E-..."
}
```

> ⚠️ **安全提醒**：
> - `config.json` 包含你的登录凭据，**不要**提交到 Git 仓库
> - 已自动添加到 `.gitignore`？如果没有，请手动添加
> - `SESSDATA` 和 `bili_jct` 泄露等同账号被盗

---

## 高级用法

### 指定分区

```python
# 在 bili_publisher.py 的 publish_article() 调用中修改 category_id
result = publish_article(client, article_dir, category_id=4)  # 4=游戏
```

常用分区 ID：
- `15` = 生活（默认）
- `4` = 游戏
- `2` = 动画
- `3` = 音乐
- `5` = 娱乐
- `17` = 单机游戏
- `22` = 影视
- `26` = 时尚
- `36` = 知识

### 设为仅自己可见

```python
result = publish_article(client, article_dir, private_pub=1)
```

### 更新已有草稿

```python
result = publish_article(client, article_dir, article_id=350758)
```

### 关闭评论

```python
result = publish_article(client, article_dir, up_closed_reply=1)
```

---

## 项目文件结构

```
├── main.py                # 入口脚本
├── bili_publisher.py      # 核心逻辑（B站API封装、Markdown解析）
├── config.json            # 认证配置（自动生成，已gitignore）
├── pyproject.toml         # Python 项目配置
├── README.md              # 本文件
├── member.bilibili.com.har # 接口分析文件（仅供开发参考）
├── analyze_har.py         # HAR文件分析工具
└── articles/
    └── article1/
        ├── main.md
        └── images/
            └── image.png
```

---

## 技术原理

整个发布流程涉及 B站 的以下 API：

1. **获取 WBI 签名密钥**：`GET /x/web-interface/nav`
   - 从 `wbi_img` 中提取 img_key 和 sub_key
   - 通过固定位移表生成 mixin_key

2. **上传图片**：`POST /x/article/creative/article/upcover`
   - 使用 multipart/form-data 上传到 B站 图床
   - 返回 B站 CDN 图片 URL

3. **保存草稿**：`POST /x/dynamic/feed/article/draft/add`
   - 请求参数需附带 WBI 签名（`w_rid` + `wts`）
   - 正文以 Opus 格式组织为 `paragraphs` 数组
   - 首次调用创建草稿，后续传入 `article_id` 更新草稿

---

## 免责声明

- 本工具仅供 **学习交流** 使用
- 请遵守 [Bilibili 用户协议](https://www.bilibili.com/protocal/licence.html) 和平台规则
- 请勿用于发布违规内容
- 使用者需自行承担相关责任
