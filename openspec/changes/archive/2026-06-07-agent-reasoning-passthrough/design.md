## Context

`ResolvedModelConfig.params` 已 `**params` 透传给 `chat.completions.create`（loop.py `_call_policy_chat`/`_stream_policy_chat`），故请求侧 reasoning（`reasoning_effort` / `extra_body.reasoning`）已可经 `agent.yaml` 的 `target.params` 配置——无需新字段。缺口仅在流式不透出后端返回的 `reasoning_content`（DeepSeek-R1/QwQ 等的非标准 delta 字段）。

## Goals / Non-Goals

**Goals:** 流式 surface `reasoning_delta`（防御式、不回传）；文档化 params-based 请求侧 reasoning。

**Non-Goals（暂缓）:** `reasoning_content` 跨轮保留/回传（后端语义不一、回传风险高）；阻塞 `run()` 的 reasoning 捕获（无流式出口）；新增 `reasoning` 配置字段（params 已覆盖）。

## Decisions

### D1：防御式 `isinstance(str)` 检测
`reasoning = getattr(delta, "reasoning_content", None); if isinstance(reasoning, str) and reasoning:` —— 标准 SDK 无此属性（getattr→None）、测试 MagicMock 自动属性非 str，两者都安全跳过；仅真实后端的字符串轨迹触发。零行为变化保证。

### D2：只透出、不回传
`reasoning_delta` 仅作为流式事件供客户端展示；`reasoning_content` 不进 `reply_parts`、不进 `messages`（DeepSeek 等明确要求不要把 reasoning_content 当输入回传）。

### D3：请求侧复用 params，不加字段
既有 `params` 已透传，新增 `reasoning` 字段冗余且扩大配置面；仅在示例里文档化用法。

## Risks / Trade-offs

- **[Risk] SDK 是否暴露 reasoning_content** → 防御式 getattr + isinstance：不暴露则 no-op，永不报错。真实后端行为需该后端验证（本 change 不依赖特定后端，安全降级）。
- **[Trade-off] 不保留 reasoning 轨迹到 session** → 仅实时透出；跨轮保留留作后续（回传语义风险）。
