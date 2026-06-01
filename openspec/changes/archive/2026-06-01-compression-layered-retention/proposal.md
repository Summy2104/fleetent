## Why

AR12（双阈值，已合入）让压缩有了 `Tmax` 触发线与 `Tretained` 目标线，但**压缩的切分方式仍是隐式的二分**：`_compress` 把非 system 消息分成「待摘要的前段」与「保留的尾部」（`_select_tail` 反推规模、`_keep_tail` 保 tool-pair 完整）。这带来一个具体风险——**用户最初的需求意图消息位于会话靠前位置，会落入「待摘要前段」被 LLM 摘要压缩**。一旦摘要丢失或改写了初始意图（例如「把这三个文件翻译成日语并保留格式」被摘成「翻译文件」），后续轮次的 AI 就可能偏离用户真正想要的目标。

现状只有「系统提示头 + 摘要 + 尾部」三块，其中**头部仅含 role==system 的消息**，不含用户的初始意图消息（通常是第一条 `user` 消息）。AR13 要把切分显式化为「头部 / 中段 / 尾部」三层，并把「用户最初的需求意图」纳入完整保留的头部，不进入摘要。

## What Changes

- 把压缩的隐式二分切分显式化为**分层保留三层结构**：
  - **头部（完整保留）**：系统提示消息 + 用户初始意图消息（会话开头的引导性 `user` 消息）。这一层 MUST NOT 进入 LLM 摘要。
  - **中段（摘要压缩）**：头部与尾部之间的早期对话，交给 LLM 摘要为一条摘要消息（沿用现 `_summarize`）。
  - **尾部（完整保留）**：最近若干 token 的消息，沿用现 `_keep_tail` 的 tool-pair 完整性与 identity check。
- **明确保护用户最初的需求意图不被截断或摘要**：初始意图消息归入头部完整保留。
- 头部 + 尾部完整保留后，仅对中段做摘要；最终序列为 `[头部完整消息..., 摘要消息, 尾部完整消息...]`。
- `Tretained` 目标线达成仍以尾部规模选取为主；头部因含初始意图为「固定保留」，其 token 计入投影（与现 `_select_tail` 把 system 头计入 `fixed` 的口径一致，本次扩展为「头部完整层」）。
- 退化场景兜底：当会话过短（头部与尾部已覆盖全部消息、中段为空）时，MUST NOT 产生空摘要消息或破坏序列合法性。

## Capabilities

### New Capabilities
- `compression-layered-retention`: 上下文压缩的分层保留策略（AR13）——把压缩切分显式化为「头部（系统提示 + 用户初始意图，完整保留）/ 中段（LLM 摘要）/ 尾部（最近消息，完整保留）」三层；明确保护用户最初的需求意图不被摘要或截断；初始意图保留条数受上界约束以防头部过大挤占 `Tretained`；尾部沿用 tool-pair 完整性与 identity check。本 change 以 ADDED 需求叠加在 AR12 双阈值之上，不重写 AR12 既有需求。

### Modified Capabilities
<!--
本次不修改 AR12 的 `context-compression-threshold` spec。
原因：AR12（compression-dual-threshold）尚未归档、其 spec 尚未 sync 进 openspec/specs/，
若此处声明 MODIFIED 将在归档时找不到目标需求；且「目标线」相关需求会与 AR15 的同名修改互相覆盖。
AR13 的增量（头部纳入初始意图、目标线为初始意图让位）全部以本 change 自有 capability 内的 ADDED 需求承载。
AR12 的 `Tmax` / `Tretained` 触发判定、手动 / 错误触发入口、阈值注入契约在代码中已生效，本 change 不重写。
-->
- （无）

## Impact

- **代码**：
  - 修改 `src/fleetent/context_mgr.py`：`_compress` 改为三层切分——先析出头部（system 消息 + 初始意图消息），中段交 `_summarize`，尾部经 `_keep_tail`；`_select_tail` 的 `fixed` 投影从「system 头」扩展为「头部完整层」。新增头部识别辅助函数（识别初始意图消息）。
- **配置**：新增**可选** Settings 字段 `compression_initial_intent_max: int = 2`（初始意图保留条数上界），可由 `.env` / `config/settings.yaml` 动态覆盖，亦可经既有 config dict 注入；带默认值、非必填，不破坏既有部署，不引入全局可变状态。
- **测试**：扩展 `tests/test_context_mgr.py`：初始意图消息在压缩后完整保留、不进摘要；三层结构顺序正确；中段为空的退化场景不产生空摘要；尾部 tool-pair 完整性仍成立。LLM 摘要调用按规范 mock（`patch get_client_and_config`）。
- **不影响**：`Tmax` / `Tretained` 触发与目标线判定、手动 / 错误触发入口、`_keep_tail` identity check 算法、`estimate_tokens` 口径、agent_loop 主循环、model fallback、终止框架；不引入新依赖（无 AI 框架、无 ORM、无云服务）。
