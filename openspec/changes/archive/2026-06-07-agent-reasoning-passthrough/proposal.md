## Why

支持推理的自托管后端（DeepSeek-R1 / QwQ 等）在流式响应里带 `reasoning_content`（思考轨迹），但 fleetent 的流式只透出 `text_delta`，客户端 / TUI 看不到推理过程。

注：**请求侧"开启 reasoning" 已经可用**——`ResolvedModelConfig.params` 以 `**params` 透传给 `chat.completions.create`，运维在 `agent.yaml` 的 `models.targets[].params` 写 `reasoning_effort` 或 `extra_body.reasoning` 即可开启后端推理，无需新增配置字段（原计划的 `models.targets[].reasoning` 字段冗余，不做）。

## What Changes

- **流式透出推理轨迹**：`run_stream` 的 chunk 循环若 delta 携带 `reasoning_content`（str），额外 yield 一个 `{"type": "reasoning_delta", "content": ...}` 事件供客户端展示。`reasoning_content` **不计入回复文本、不回传给 LLM**（部分后端禁止 reasoning_content 作为输入）；缺失时 no-op（防御式 `isinstance(str)` 守卫，兼容标准 SDK 与 mock）。
- **文档**：在 `agent.yaml.example` 注明用 `target.params` 的 `reasoning_effort` / `extra_body.reasoning` 开启请求侧 reasoning。

## Capabilities

### New Capabilities

- `agent-reasoning-passthrough`: 流式透出后端推理轨迹（reasoning_delta），请求侧经既有 params 开启。

### Modified Capabilities

（无）

## Impact

- **修改文件**：`src/fleetent/runtime/loop.py`（`run_stream` chunk 循环 + 事件类型 docstring）；`agents/default/agent.yaml.example`（文档注释）。
- **解耦合规**：纯 `runtime/`，防御式、无新依赖、无 platform、未配置/不支持时零行为变化。
- **暂缓（documented）**：`reasoning_content` 跨轮保留/回传（后端语义不一、回传风险高）；阻塞 `run()` 的 reasoning 捕获（无流式出口、价值低）；新增 `reasoning` 配置字段（params 已覆盖请求侧）。
