---
name: common-web-capture
description: 网页截图和内容抓取。对公开网页进行截图、全页截图或 CSS 选择器内容提取。触发词：截图、网页截图、抓取网页、网页内容、screenshot、web capture、帮我截图、给我看看这个页面。遇到用户提供 URL 并要求"看看"、"截图"、"抓取内容"时，优先使用此 skill。
status: active
metadata:
  author: RD Team
  version: 1.0.0
triggers:
  - 截图
  - 网页截图
  - 抓取网页
  - 网页内容
  - screenshot
  - web capture
  - 帮我截图
  - 给我看看这个页面
---

# 网页截图与内容提取

通过 Playwright 无头浏览器对公开网页进行截图和数据提取。fleetent 通过 playwright MCP server 调用浏览器，工具名为 `playwright__browser_*`（双下划线）。

> 简单的纯文本/HTML 抓取（无需浏览器渲染）优先用内置 `web_fetch`；需要渲染、截图、交互或读取动态内容时才用下面的 playwright 浏览器流程。

---

## 截图（两步走，顺序不可颠倒）

`playwright__browser_take_screenshot` 本身不导航——新 session 是空白页，必须先 navigate 再立即截图。**navigate 和 screenshot 之间不要插入其他操作**，避免多 tab 并发时焦点漂移到错误页面。

**第一步：导航**

```
playwright__browser_navigate(url="https://example.com")
```

navigate 默认等待 `load` 事件（DOM + 基础资源），对静态页面足够。动态内容页面（图表、懒加载）可在 navigate 完成后调用一次 `playwright__browser_wait_for` 或 `playwright__browser_snapshot` 确认内容已到位，再截图。

**第二步：立即截图**

```
playwright__browser_take_screenshot(type="png", fullPage=false)
```

- `fullPage=false`（默认）：视口截图，适合首屏预览
- `fullPage=true`：整页截图，适合文章、报表、仪表盘

### 发送截图

截图保存到 workspace 后，用内置 `send_file` 发回当前对话：

```
send_file(path="outbound/screenshots/<文件名>.png")
```

## 内容提取（优先于截图）

需要读取文字、链接、表格数据时，用 snapshot 而不是截图——更快且可直接处理：

```
playwright__browser_navigate(url="https://example.com")
playwright__browser_snapshot()
```

`playwright__browser_snapshot` 返回页面可访问性树，可直接从中提取结构化内容。需要按 CSS 选择器取特定元素时用 `playwright__browser_evaluate` 执行页面脚本。

## 失败处理

截图内容空白或明显缺失时：

1. 重新 navigate（不跳过）
2. 调用 `playwright__browser_snapshot` 确认页面内容已加载
3. 再次截图

不要在失败后直接重截，必须重新导航以确保 tab 状态正确。

---

## 场景速查

| 需求 | 方案 |
|------|------|
| 首屏预览 | navigate → screenshot（`fullPage=false`） |
| 完整文章 / 报表 | navigate → screenshot（`fullPage=true`） |
| 读取文字 / 数据 | navigate → snapshot（不截图） |
| 动态图表 / 懒加载 | navigate（`waitFor=2000`）→ snapshot 确认 → screenshot |
| 截图空白 / 错误 | 重新 navigate → snapshot 确认 → 再截图 |

---

## 前置依赖

playwright 浏览器能力由 agent.yaml 挂载的 `playwright` MCP server 提供。若未挂载该 server（`playwright__browser_*` 工具不可用），对纯静态/文本页面退化为内置 `web_fetch`；需要截图或动态渲染但 server 缺失时，向用户说明该能力未配置。
