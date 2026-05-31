## Context

主循环把 `messages`（dict 列表）直接传给 `_call_with_fallback` / `_stream_with_fallback`，再交给 OpenAI 兼容 SDK。消息序列在多处被改写：`maybe_compress`（context_mgr）会重组历史；`run()` 审批被拒时手动补占位 tool_result（agent_loop.py 行 238-243）；`_safe_dispatch` 把工具崩溃归一化为错误字符串 result；session 持久化往返（JSON）也可能引入不一致。这些环节单独看都尽力保契约，但缺一个统一的发送前兜底。

OpenAI 兼容后端对非法序列（连续同角色、tool_call/result 不配对）返回 400，整次任务崩溃，且崩溃栈离成因很远。本 change（AR6）在发给 LLM 前做一次集中校验与修复，把「非法序列」挡在 LLM 之前，并把修复动作记进 trace 以便回溯成因。

约束（CLAUDE.md）：禁止 AI 框架；禁止全局可变状态；新模块结构为 import → 常量 → 数据类 → 函数；mypy strict；TDD Hard Gate；异常不吞、catch 后必 log 或 re-raise。

## Goals / Non-Goals

**Goals:**
- 提供 `sanitize(messages) -> (clean_messages, HygieneReport)`：纯函数式校验+修复，不改入参（返回新列表）。
- 修复三类违规：连续同角色消息、缺失 tool_result、孤立 tool_result。
- 修复动作写入 trace（修复类型 + 数量）。
- 无法安全修复的违规在调用 LLM 前抛出明确错误。
- `run()` / `run_stream()` 在 `maybe_compress` 后、LLM 调用前接入，行为一致。

**Non-Goals:**
- 不替代既有的点对点保契约逻辑（审批占位、压缩保 tool 对）——卫生层是其上游统一兜底，二者叠加。
- 不做语义级修复（不改写消息文本内容、不重排工具调用顺序之外的内容）。
- 不处理多模态内容块的合法性（属 AR21 多模态输入范围）。
- 不改动终止框架、压缩、permission_gate、fallback 既有行为；不新增 Settings 字段。

## Decisions

### D1：纯函数 sanitize + HygieneReport，不就地改 messages
新增 `src/fleetent/message_hygiene.py`：
- `RepairKind`：`str` 枚举，`merged_same_role` / `inserted_placeholder` / `filled_missing_tool_result` / `removed_orphan_tool_result`。
- `HygieneReport` 数据类：`repairs: dict[RepairKind, int]`（各类修复计数）、`changed: bool`。
- `sanitize(messages: list[dict]) -> tuple[list[dict], HygieneReport]`：返回新列表与报告，**不修改入参**。

**为何**：纯函数易单测、无副作用；返回报告让主循环决定是否写 trace，符合「禁止全局可变状态」。返回新列表避免就地改 `messages` 影响 session 持久化与调用方持有的引用。
**Alternatives**：①就地原地修改 messages——被否，副作用难测且易污染 session 状态；②抛异常驱动修复——被否，可修复的违规是正常控制流。

### D2：修复规则与顺序
固定执行顺序（后一步依赖前一步的结果合法性）：
1. **移除孤立 tool_result**：扫描所有 `role == "tool"` 消息，其 `tool_call_id` 若不在「之前出现过的 assistant.tool_calls 的 id 集合」中 → 移除。计 `removed_orphan_tool_result`。
2. **补缺失 tool_result**：对每条含 `tool_calls` 的 assistant 消息，其每个 `tool_call.id` 若后续无对应 `role == "tool"` 消息 → 在该 assistant 消息之后补一条占位 `{"role": "tool", "tool_call_id": id, "content": "工具执行失败（缺失结果，已自动补全）"}`。计 `filled_missing_tool_result`。
3. **修复连续同角色**：扫描相邻消息，两条同 `role`（限 user / assistant 文本类，不含 tool）相邻 → 合并 content（文本拼接）。若无法安全合并（如一条是 `tool_calls` 载体）则插占位消息隔开。计 `merged_same_role` / `inserted_placeholder`。

**为何**：先清孤立、再补缺失，保证 tool 配对集合稳定后再处理同角色相邻；顺序固定使结果确定、可单测。占位文本中文、明确标注「自动补全」，避免 AI 误读。
**Alternatives**：合并 vs 插占位的取舍——优先合并（保留信息），仅在合并会破坏 tool 契约时插占位；不一刀切，按消息类型择优。

### D3：无法安全修复 → 尽早 raise
若校验出本层规则无法安全修复的违规（如消息缺 `role`、tool 消息缺 `tool_call_id` 且无法归属、结构性损坏），`sanitize()` MUST raise 明确异常（自定义 `MessageContractError`），由主循环在调用 LLM 前捕获并按错误处理（写 trace + 终止），绝不把非法序列传给 LLM。
**为何**：契约文档要求「修复失败尽早报错，不传非法消息给 LLM」；在本地 raise 比远端 400 的诊断成本低得多。异常携带违规描述，不吞。
**Alternatives**：尽力修复后放行——被否，把不确定的非法序列发给 LLM 违背契约，且远端报错信息差。

### D4：接入点与 trace
`run()` / `run_stream()` 在 `maybe_compress(messages)` 之后、`_call_with_fallback` / `_stream_with_fallback` 之前调用 `sanitize()`，用返回的 clean 列表替换 `messages`。`HygieneReport.changed` 为真时，经 `log_run` 新增的 `hygiene_repairs` 参数写入 trace（默认 None，仅修复发生时写）。
**为何**：放在压缩之后能兜底「压缩引入的残缺」（覆盖 agent-runtime.md 场景 10）；放在 LLM 调用之前满足契约「发送前合法」。trace 写入复用现有唯一出口，与 AR1 `stop_reason` 模式一致。

### D5：与既有点对点保契约逻辑的关系
审批被拒补占位（行 238-243）、压缩保 tool 对（context_mgr）保持不变。卫生层是幂等兜底：对已合法的序列 `sanitize()` 返回 `changed=False`、原样列表，不重复修复。
**为何**：不削弱既有保护、不引入回归；幂等性保证叠加无副作用，可单测「合法序列进出不变」。

## Risks / Trade-offs

- [合并同角色消息可能丢失结构信息] → 仅对文本类同角色合并，遇 tool_calls 载体改插占位；合并策略单测覆盖；report 记录便于回溯。
- [补占位 tool_result 可能掩盖真正的工具缺失成因] → 占位文本明确标注「自动补全」，且 report + trace 记录修复计数，成因可在 trace 追溯。
- [sanitize 顺序敏感，规则交互产生意外结果] → 顺序固定（清孤立→补缺失→修同角色），每条规则与组合均有单测；幂等性测试守卫二次 sanitize 不再变更。
- [接入后对正常序列增加每轮开销] → `sanitize` 为线性扫描、无 LLM 调用、毫秒级；合法序列走快路径（`changed=False`）。
- [与压缩/审批的点对点逻辑叠加导致双重修复] → 幂等设计 + 既有逻辑已保契约，卫生层对合法序列 no-op；测试覆盖「审批占位 + 卫生层」组合。

## Open Questions

- 连续同角色「合并 vs 插占位」的边界细则（system 消息是否参与、assistant tool_calls 载体相邻如何处理）——实现首步用 `tests/test_agent_loop.py` 现有消息构造与 SDK 期望格式核实后定。
- `MessageContractError` 在主循环出口如何归类（是否复用 AR5 错误分类的 `unknown`/新增码）——若 error-classification 已合入则对齐其分类码，否则本次按普通异常 + trace 处理，留接口。
