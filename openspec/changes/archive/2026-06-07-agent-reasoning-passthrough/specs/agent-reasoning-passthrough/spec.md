## ADDED Requirements

### Requirement: 流式透出后端推理轨迹

流式 `run_stream` SHALL 在 LLM 响应 chunk 的 delta 携带 `reasoning_content`（字符串）时，额外产出一个 `reasoning_delta` 事件（`{"type": "reasoning_delta", "content": <文本>}`）供客户端展示推理过程。该 `reasoning_content` MUST NOT 计入最终回复文本，MUST NOT 被回传给 LLM（避免部分后端拒收 reasoning_content 作为输入）。检测 MUST 为防御式：仅当 `reasoning_content` 为非空字符串时透出，缺失 / 非字符串时 MUST 为 no-op（不改变既有流式行为）。请求侧开启 reasoning 经既有 `models.targets[].params`（`reasoning_effort` / `extra_body.reasoning`）透传，本能力 MUST NOT 新增 reasoning 专用配置字段。

#### Scenario: 后端带 reasoning_content 时透出 reasoning_delta
- **WHEN** 流式响应某 chunk 的 delta 含非空字符串 `reasoning_content`
- **THEN** `run_stream` 产出一个 `reasoning_delta` 事件，其 content 为该推理文本；该文本不出现在最终回复里

#### Scenario: 无 reasoning_content 时行为不变
- **WHEN** 流式响应的 delta 不含 `reasoning_content`（标准后端）
- **THEN** `run_stream` 不产出任何 `reasoning_delta` 事件，行为与未引入本能力时一致

#### Scenario: 请求侧 reasoning 经既有 params 配置
- **WHEN** 运维在 `agent.yaml` 的某 target `params` 设 `reasoning_effort` 或 `extra_body.reasoning`
- **THEN** 该参数随既有 `**params` 透传给后端调用以开启推理，无需新增专用字段
