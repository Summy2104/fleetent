## Why

主循环把工具结果原样写回 `messages`：`run()`（`agent_loop.py` 行 676）与 `run_stream()`（行 947）都执行 `messages.append({"role": "tool", "tool_call_id": ..., "content": result})`，`result` 是 `dispatch()` 返回的完整字符串，未经任何长度约束。一个返回大文件、长日志、抓取的整页 HTML 或大 JSON 的工具，会把数万 token 一次性塞进上下文，挤占后续轮次的可用空间，甚至单次就触发 `context_overflow`。

`context_mgr.maybe_compress`（AR12）确实会在累计超过 Tmax 时压缩历史，但它是**事后的、对整段历史的**摊还式压缩：超大结果先已进入 `messages` 占满当前轮的 prompt，压缩在下一轮才发生，本轮 LLM 调用仍要承受这条超大消息（极端情况单条就超模型上限，压缩都来不及救场）。

`docs/capabilities/tools.md`「规划中（v1.0）」明确列出「工具结果截断：输出超过阈值（如 10k tokens）时截断 + 写 breadcrumb，避免工具结果撑爆 context」，并在「待决问题」留下「截断到多少 token？breadcrumb 格式是什么？」。本 change 把该规划项落为 spec：在工具结果**写入 `messages` 之前**做一次源头侧的大小约束，避免单条结果撑爆上下文，与 AR12 的历史压缩形成「源头截断 + 历史压缩」的两道防线。

## What Changes

- 引入**工具结果截断**：在工具结果写回 `messages` 之前，对超过阈值的结果做「头尾保留 + 中间省略」截断，省略处插入 breadcrumb（标明原始字节数、被省略字节数），确保单条 `tool` 消息不超过阈值上限。
- 引入 **`self_truncates` opt-out（自截断工具豁免）**：工具可经 `@tool(self_truncates=True)` 声明「自己负责截断输出」，该元数据与 `risk_level` / `connector` 等平行存放于 `tool_registry`、**不进入 LLM schema**；T4 在写回 `messages` 前 SHALL **跳过**已声明 `self_truncates=True` 的工具，由该工具的专门截断器独占其输出截断。典型即 `run_code`——其输出由 SB6 独占截断，故 `run_code` 声明 `self_truncates=True`、对 T4 豁免。
- 阈值以**字节口径**（`len(s.encode("utf-8"))`）定义，与兄弟 change `sandbox-output-truncation`（SB6）保持完全一致的字节口径；阈值可注入（模块级常量 / 配置），未配置时使用安全默认值。T4 默认阈值保持 **~40KB（10k tokens 量级）**，**不为迁就 sandbox（SB6 stdout 50KB + stderr 10KB = 60KB）抬高到 64KB**——否则每个工具都能灌 64KB（≈16k tokens），破坏 T4 通用的 ~10k-token 帽。`run_code` 的大输出由 SB6 独占管控、对 T4 豁免，因此 T4 无需为它抬高默认值。
- 截断策略本 change 定为**头尾保留 + 中间省略**（保留首尾各一段、中间替换为 breadcrumb），不做 LLM 摘要——摘要属 AR12 历史压缩职责，源头截断必须是纯规则、零 LLM 调用、毫秒级。
- **trace 记录截断后内容**：截断只影响写入 `messages`（占 context）的副本，但 trace 靠序列化 `messages` 落盘、截断在 `append` 之前完成，故 trace 记录的就是 LLM 实际所见的截断内容（与 `eval_logger`「只记元数据/样本、不落原始大对象」的克制原则一致）；breadcrumb 的原始/省略字节数即审计所需大小元数据。完整原文若需归档属工具自身日志职责、不归通用 trace、不在本 change。
- 截断在工具结果写回点统一发生（`run()` 行 676 / `run_stream()` 行 947 两处共用同一截断函数），不下沉到每个工具内部。

## Capabilities

### New Capabilities
- `tool-result-truncation`: 工具结果在写入消息（占用上下文）前按字节阈值做头尾保留 + 中间省略截断并插入 breadcrumb，未配置时回退安全默认（~40KB / 10k tokens 量级）；字节口径与 SB6 一致，纯规则零 LLM；声明 `self_truncates=True` 的工具（如 `run_code`，其输出由 SB6 独占截断）被 T4 跳过、不受 T4 阈值约束；trace 序列化 messages 故记录的是截断后内容（= LLM 所见），breadcrumb 提供原始/省略字节数作审计元数据。

### Modified Capabilities
<!-- 不修改既有 spec。tools 能力的「工具结果截断」此前仅为 docs 规划项（无对应 spec 需求），本 change 首次以 spec 表达，落在新 capability `tool-result-truncation` 下以 ADDED 表达，不对 tools 主 spec 做 MODIFIED（否则 archive sync 找不到同名既有需求）。 -->

### 边界与共享引用
- **与 SB6（`sandbox-output-truncation`）的边界**：**SB6 独占 `run_code` 输出（stdout/stderr）的截断**（stdout 50KB / stderr 10KB，按 `sandbox.md`），发生在沙箱执行结果产出处；**T4 管所有【其他】工具结果**——对除 `run_code` 外、所有 `dispatch()` 返回的工具结果在写回 `messages` 前生效（~40KB）。`run_code` 经 `@tool(self_truncates=True)` 声明对 T4 **豁免**，T4 写回前直接跳过它，故二者**各管各的工具、不叠加、无数值耦合**（不存在「T4 阈值须 ≥ SB6 两流之和 60KB」这种脆弱耦合）。两者字节口径仍统一为 `len(s.encode("utf-8"))`（同一仓库的一致度量惯例），但不再依赖此一致性来「防止二次截断」——因为 T4 根本不碰 `run_code`。
- **与 AR12（`context_mgr.maybe_compress`）的边界**：T4 是写入前的源头截断（纯规则、单条粒度、零 LLM）；AR12 是写入后的历史压缩（可调 LLM、整段粒度）。两者职责不重叠、互补。

## Impact

- **代码**：
  - 新增截断逻辑（建议 `src/fleetent/tool_result_truncation.py`，或并入 `tool_registry.py`，按 design 定）：`truncate_tool_result(result: str, max_bytes: int | None = None) -> str`，字节口径 `len(s.encode("utf-8"))`，超阈值头尾保留 + breadcrumb。
  - 修改 `src/fleetent/tool_registry.py`：`@tool` 新增 `self_truncates: bool = False` 元数据，与 `risk_level` / `connector` 平行存放于模块级 dict、**不进入 LLM schema**；提供 `is_self_truncating(name) -> bool` 查询；`run_code` 声明 `self_truncates=True`。
  - 修改 `src/fleetent/agent_loop.py`：在 `run()`（行 676）与 `run_stream()`（行 947）写回 `tool` 消息前对 `result` 调用截断函数；先判断该工具是否 `self_truncates`，是则**跳过截断**（如 `run_code`）。
  - trace：`eval_logger` 序列化 `messages` 落盘，截断在 `append` 之前完成，故 trace 记录的是截断后内容（= LLM 所见）；本 change 不在 trace 侧新增任何 capture。
- **配置**：阈值常量可注入（模块级 `MAX_TOOL_RESULT_BYTES`，默认 ~40KB / 10k tokens 量级，可 `monkeypatch`）；如接入 `Settings` 字段则为可选、缺省安全默认。**不为单一工具（如 run_code）特例抬高默认值**——大输出工具应走 `self_truncates` 豁免，而非抬高全局帽。
- **测试**：新增 `tests/test_tool_result_truncation.py`（阈值内不变 / 超阈值头尾保留 + breadcrumb / 字节口径多字节字符 / 边界值 / 阈值可注入）；扩充 `tool_registry` 测试断言 `self_truncates` 元数据可声明、可查询、不进 schema；扩充 `agent_loop` 测试断言写回 `messages` 的 `tool` 消息已被截断（trace 记录的即此截断内容）、声明 `self_truncates` 的工具（如 `run_code`）被 T4 跳过不截，`dispatch()` 返回值与 `tool_result` SSE 事件仍为原始结果。LLM 全程 mock，路径隔离 tmp_path。
- **不影响**：AR12 历史压缩逻辑、SB6 沙箱内截断（`run_code` 输出仍由 SB6 独占截断）、`dispatch` 返回值本身、工具访问控制 / 凭证注入。
- **不引入新依赖**（仅标准库）。

## Dependencies

- `tool_registry`（`dispatch()` 返回工具结果字符串——本 change 的截断对象；`@tool` 新增 `self_truncates` 平行元数据与 `is_self_truncating` 查询）/ `agent_loop`（`run()` 行 676、`run_stream()` 行 947 工具结果写回 `messages` 的点——截断接入点，写回前对 `self_truncates` 工具跳过）。
- `context_mgr`（AR12 `maybe_compress`）——本 change 是其互补的源头防线，不改其逻辑；字节/token 口径在 design 钉死边界。
- `agent-error-classification`（AR5）——源头截断降低单条结果触发 `context_overflow` 的概率；本 change 不改 AR5，仅在 design 说明协同关系。
- 兄弟 change `sandbox-output-truncation`（SB6）——**SB6 独占 `run_code` 输出截断**（stdout 50KB / stderr 10KB），`run_code` 经 `self_truncates` 对 T4 豁免；T4 管其余工具（~40KB）。字节口径统一 `len(s.encode("utf-8"))`，但二者各管各的工具、**不叠加、无数值耦合**（不存在「T4 须 ≥ 60KB」的脆弱约束）。
