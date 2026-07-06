# workflow-steps Specification

## Purpose
工作流步骤执行器（tool/agent/notify）：输入渲染与输出规约、治理 fail-closed 门控、结构化输出、内部审批 fail-closed（M1）。

## Requirements

### Requirement: 输入渲染（运行期字段映射）

step 执行前，系统 SHALL 渲染其全部模板字段：`${inputs.<path>}` 从 run 冻结的 `inputs_json` 取值，`${steps.<id>.output.<path>}` 从对应 step 的 `output_json` 按点路径取值（dict key / list index）。占位符独占整个值时 SHALL 保留原类型（数值/对象/列表），嵌入文本中时 SHALL 字符串化拼接。路径不可解析（键不存在、索引越界、类型不匹配）SHALL 使该 step 失败并报明确错误（指出 step id、占位符与失败原因），MUST NOT 以空值/None 静默继续。

#### Scenario: 点路径取值成功
- **WHEN** 上游 step 输出 `{"summary": "ok", "items": [{"id": 1}]}` 且下游引用 `${steps.a.output.items.0.id}`
- **THEN** 渲染结果为整数 `1`

#### Scenario: 路径解析失败 fail-closed
- **WHEN** 下游引用 `${steps.a.output.missing}` 而该键不存在
- **THEN** 该 step 失败，错误信息含占位符原文与"键不存在"，下游级联 skip

### Requirement: tool step 执行

`type: tool` 的 step SHALL 经工具注册表 dispatch 执行：渲染后的 `args` 作为工具参数，执行上下文经 `ToolContext` 带外注入（run 的冻结 principal、run 标识等），MUST NOT 进入工具参数。工具输出 SHALL 尝试 JSON 解析：成功则 `output_json` 为解析对象，失败则为 `{"text": <原文>}`。工具执行异常按 step 失败处理（error 记录摘要，不吞异常）。

#### Scenario: JSON 输出可被下游寻址
- **WHEN** 工具返回合法 JSON 字符串 `{"count": 3}`
- **THEN** `output_json` 为该对象，下游可引用 `${steps.x.output.count}`

#### Scenario: 非 JSON 输出包裹为 text
- **WHEN** 工具返回纯文本
- **THEN** `output_json` 为 `{"text": "..."}`，下游经 `.output.text` 引用

### Requirement: tool step 治理门控（fail-closed，不旁路）

每次 tool step 执行前 SHALL 评估该工具的风险等级并解析处置模式（与对话路径同一套 `evaluate_risk_level → resolve_action_mode` 判定，含 allowlist 与 blocklist 语义）。M1 语义：解析为 `DIRECT` 才执行；解析为 `APPROVAL` / `SANDBOX` / `REJECT` 一律 step 失败，错误信息 SHALL 指明所需处置模式与建议（"包进 agent step 或待审批接通"）。critical 风险 MUST 恒定失败，任何 workflow 声明都 MUST NOT 使其降级。workflow 路径的门控判定 MUST 与对话路径对同一工具+参数给出一致结果（无独立豁免通道）。

#### Scenario: 高风险工具被拒绝
- **WHEN** tool step 引用一个解析为 `APPROVAL` 模式的工具
- **THEN** step 失败且不执行工具，错误指明"需要审批，M1 不支持"，run `failed`

#### Scenario: critical 恒拒
- **WHEN** tool step 引用 critical 风险工具
- **THEN** step 失败（REJECT），无任何配置可使其执行

#### Scenario: 低风险直通
- **WHEN** tool step 引用解析为 `DIRECT` 的低风险工具
- **THEN** 工具正常执行，无审批交互

### Requirement: agent step 执行

`type: agent` 的 step SHALL 以渲染后的 `prompt` 发起一次完整 agent 运行：指定 `agent` 名时加载该 agent 的快照（system_prompt / allowed_tools / model_policy）执行，省略时以宿主 agent 自身身份执行；均以 sub-agent 模式进入 loop（继承 run 冻结 principal，受 CancelToken 与 step 超时约束）。默认输出 `{"text": <最终回复>}`。agent 运行异常按 step 失败处理。

#### Scenario: 指定 agent 委派
- **WHEN** step 声明 `agent: analyst` 且该 agent 快照存在
- **THEN** 以 analyst 的 system_prompt/allowed_tools/model_policy 执行 prompt，输出落 `{"text": ...}`

#### Scenario: 省略 agent 用宿主
- **WHEN** step 未声明 `agent`
- **THEN** 以宿主 agent 自身配置执行

### Requirement: agent step 结构化输出（output_schema）

声明 `output_schema` 的 agent step SHALL 强制结构化输出：向 agent 运行注入"最终回复必须是符合该 JSON Schema 的 JSON"指令，运行结束后解析并按 schema 校验；首次解析/校验失败 SHALL 追加纠正指令重试一次；再失败则 `output_json` 落 `{"text": <原文>}`（下游若寻址 schema 字段将按映射失败 fail-closed）。解析成功则 `output_json` 为该结构化对象。

#### Scenario: 结构化输出成功
- **WHEN** step 声明 `output_schema` 含 `summary` 字段且 agent 返回合法 JSON
- **THEN** `output_json` 为解析对象，下游 `${steps.x.output.summary}` 可用

#### Scenario: 两次失败落回 text
- **WHEN** agent 两次输出均无法通过 schema 校验
- **THEN** `output_json = {"text": ...}`；依赖 `summary` 的下游 step 因映射失败而失败（不静默传坏数据）

### Requirement: agent step 内部审批 fail-closed（M1）

agent step 内部工具调用 SHALL 受 loop 现有治理门控约束（与对话路径完全一致）。M1 语义：agent 运行因等待审批而挂起（`awaiting_approval` 终止）时，该 step SHALL 按失败处理，错误注明"内部工具需审批，M1 不支持挂起恢复"，MUST NOT 无限等待、MUST NOT 绕过门控执行。

#### Scenario: 内部审批即失败
- **WHEN** agent step 中 LLM 调用了需审批的工具
- **THEN** loop 按现有门控挂起该工具后 step 以失败收场（原因含 awaiting_approval），run `failed`

### Requirement: notify step 执行

`type: notify` 的 step SHALL 将渲染后的 `text` 主动投递：`to` 显式指定投递目标时用之，省略时回落 run 的 `origin` 投递解析（与终态投递同一解析规则）。投递成功 `output_json` 记录投递结果摘要；无可解析目标或投递失败按 step 失败处理（此为 step 的本职，区别于 run 终态通知的 best-effort）。

#### Scenario: 回落 origin 投递
- **WHEN** notify step 未声明 `to` 且 run 由 IM 对话发起
- **THEN** 消息投递到发起对话地址，step 成功

#### Scenario: 无目标即失败
- **WHEN** notify step 未声明 `to` 且 run 由 CLI 发起（无 origin 可投递）
- **THEN** step 失败并报"无可解析投递目标"
