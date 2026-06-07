# builtin-web-tools Specification

## Purpose
Web 工具集，提供 agent 从互联网获取页面内容（web_fetch）和执行自托管搜索（web_search）的能力。所有外部服务均可自托管，数据不出内网。

## Requirements

### Requirement: web_fetch 获取并转换 Web 页面内容
`web_fetch` SHALL 接受 `url`（必填）、`format`（`"markdown"` | `"text"` | `"html"`，默认 `"markdown"`）、`timeout`（秒，默认 30，最大 120）参数；使用 httpx 异步 HTTP 客户端获取页面；`format="markdown"` 时将 HTML 转为 Markdown（html2text 库）；`format="text"` 时提取纯文本（跳过 script/style）；`format="html"` 时返回原始 HTML。响应大小 SHALL 限制在 5MB，超过时截断。

#### Scenario: 获取页面并转为 Markdown
- **WHEN** 调用 `web_fetch(url="https://example.com/docs")` （默认 format="markdown"）
- **THEN** 返回页面的 Markdown 格式文本，HTML 标签被转换为对应 Markdown 语法

#### Scenario: 获取纯文本内容
- **WHEN** 调用 `web_fetch(url="https://example.com", format="text")`
- **THEN** 返回页面可见文本，不含 HTML 标签、脚本和样式

#### Scenario: 请求超时返回错误
- **WHEN** 请求在 `timeout` 秒内无响应
- **THEN** 返回 `"error: 请求超时（{timeout}s）: {url}"`

#### Scenario: 响应大小超过 5MB 截断
- **WHEN** HTTP 响应体超过 5MB
- **THEN** 截断至 5MB，附加 `"[响应过大，已截断至 5MB]"` 提示

#### Scenario: 二进制内容（图片/PDF）返回提示
- **WHEN** Content-Type 为图片或 PDF
- **THEN** 返回 `"error: 内容为 {content_type}，图片请使用 analyze_image 工具"`

### Requirement: web_search 通过 SearXNG 执行自托管搜索
`web_search` SHALL 接受 `query`（必填）、`num_results`（默认 8，最大 20）参数；调用 `SEARXNG_URL` 环境变量指定的 SearXNG 实例 JSON API；返回结果列表，每条含标题、URL 和摘要。

#### Scenario: 搜索并返回结果列表
- **WHEN** 调用 `web_search(query="python asyncio tutorial")`
- **THEN** 返回最多 8 条结果，每条格式为 `1. [标题](URL)\n   摘要文字`

#### Scenario: SearXNG 无响应时返回错误
- **WHEN** SearXNG 实例不可达或返回非 200
- **THEN** 返回 `"error: SearXNG 搜索失败: {原因}"`

### Requirement: web_search 在未配置 SEARXNG_URL 时不暴露给 LLM
`web_search` SHALL 声明 `availability=lambda: bool(os.getenv("SEARXNG_URL"))`；当 `SEARXNG_URL` 未设置时，`get_schemas()` 过滤该工具，LLM 无法看到或调用它（不产生报错，工具不存在）。

#### Scenario: 未配置 SEARXNG_URL 时工具不在 schema 中
- **WHEN** 环境变量 `SEARXNG_URL` 未设置
- **THEN** `get_schemas()` 返回的列表中不包含 `web_search`

#### Scenario: 配置 SEARXNG_URL 后工具可用
- **WHEN** `SEARXNG_URL` 已设置为有效 SearXNG 地址
- **THEN** `get_schemas()` 返回的列表中包含 `web_search`
