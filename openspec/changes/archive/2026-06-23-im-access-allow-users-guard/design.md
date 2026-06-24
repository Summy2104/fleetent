## Context

`agent_config._reject_inline_secrets(agent, path)` 在 `load_agent_file` / `load_agent_home_file` 加载 `agent.yaml` 时调用。它把 `{"mcp_servers": [...], "im": agent.im.model_dump()}` 经 `secret_scan.flatten` 拍平成 `(dotted-key, value)` 列表，对每个字符串值跑 `looks_inline_secret`。

`flatten` 对列表项用下标编号，所以 `im.slack.access.allow_users` 的元素 key 形如：

```
im.slack.access.allow_users.0
im.telegram.access.allow_users.1
im.slack.access.allow_groups.0
```

现有豁免是一句子串匹配：

```python
if any(seg in key for seg in (".args.", ".command", ".id", ".transport")):
    continue
```

`secret_scan._SECRET_RE` 含 `[A-Za-z0-9_-]{24,}` 分支，36 字符 UUID（`5f5904ef-efcf-42bb-82fa-ad5a150b078c`）整体命中 → 误报。

## Goals / Non-Goals

**Goals**
- 让「配 IM + 绑 UUID user」的 `agent.yaml` 能被加载、不抛 inline-secret。
- 豁免精确到 `access.allow_users` / `access.allow_groups`，不波及其它字段。
- 真 secret（如 `bot_token_env` 写明文 token）仍被拒（防回归）。

**Non-Goals**
- 不动 `secret_scan._SECRET_RE`（不降低全局熵阈值）。
- 不改 materialize 写入内容、不改 IM 身份匹配语义。

## Decisions

### 决策 1：在 `_reject_inline_secrets` 的 skip-segment 列表里加 `im` access 路径

把豁免子串集合扩展为：

```python
_SKIP_SECRET_SCAN_SEGMENTS = (
    ".args.", ".command", ".id", ".transport",
    ".access.allow_users.", ".access.allow_groups.",
)
```

**为什么用 `.access.allow_users.`（带前后点）而非 `.allow_users.`**：精确锚定到 IM binding 的 access 子树，避免任何未来同名字段被无意豁免。元素 key `im.slack.access.allow_users.0` 含子串 `.access.allow_users.`，匹配成立；空列表不产生元素 key，无副作用。

**为什么不改 `secret_scan`**：`looks_inline_secret` 是 agent 侧与 platform 侧共享的中性纯函数，按值判断、无路径上下文；UUID 在别处（如某个真该是 secret 的字段里）仍应被当作可疑高熵串。豁免是「路径级」决策，归属在调用方 `_reject_inline_secrets` 的字段语义里，不属于值级检测器。

### 决策 2：豁免范围严格限定两个路径

只豁免 `access.allow_users` / `access.allow_groups`。`im.slack.bot_token_env` 等不含 `.access.allow_` 子串，仍走 secret 扫描；明文 token 仍 fail loud。

## Risks / Trade-offs

- **风险：豁免被滥填明文 secret**。`allow_users` / `allow_groups` 语义就是 id 列表，不是凭据承载字段；即便有人把 token 塞进 `allow_users`，它也只会被当作一个永不匹配的 allowlist 项（不会被解析/连接使用），无凭据泄漏路径。可接受。
- **Trade-off：子串匹配而非结构化路径解析**。沿用现有 `_reject_inline_secrets` 既有风格（`seg in key`），保持改动最小、与上下文一致。
