## Why

现状 `_compress`（context_mgr.py:103-120）在确定要压缩后，直接把中段整段交给 `_summarize`（行 146-169）调 LLM。但中段里常含两类**无需 LLM、用纯规则就能廉价瘦身**的内容：

- **图片 / 二进制占位块**：`estimate_tokens` 已把 image 块按固定 `_IMAGE_BLOCK_TOKENS=1000` 估算（行 49-50），但 `_summarize` 拼摘要输入时经 `_content(m)`（行 191-194）对整条消息的 `content` 做 `str(...)`——当 content 是含 image 块的 list 时，整个 list（含巨大 base64）被 `str()` 化拼进摘要文本，膨胀 prompt 且对摘要无帮助；早期图片在压缩阶段其实只需保留「这里曾有一张图」的占位信息。膨胀点在 `_content` 层，因此清理应在「构造摘要输入前替换 content list 内的 image block」。
- **重复的工具调用**：AI 在探索阶段常对**同一工具用同一参数**反复调用，且**结果相同**（例如多次 `read_file` 同一路径、多次 `list_dir` 同一目录）。这些重复的 tool_call / tool_result 对在历史里冗余，留在中段会无谓增大待摘要规模。

这些清理是**毫秒级纯规则预处理，绝不调 LLM**。在进入 LLM 摘要前先做一遍，可减小待摘要中段规模、利于 `estimate_tokens` 回落到 `Tretained`、并让后续 AR13 分层切分 / AR14 增量摘要处理更少、更干净的中段。

## What Changes

- 新增**压缩前轻量清理**阶段：在进入 LLM 摘要之前、对待处理消息执行纯规则预处理（毫秒级，MUST NOT 调用 LLM）。
- **图片 / 二进制占位兜底替换**：把消息 content list 内的图片 / 二进制占位块替换为简短文本占位 `[图片：{尺寸}]`（尺寸缺失时用兜底值，仍产出合法占位），消除巨大 base64 / 二进制经 `_content` 的 `str()` 化对摘要输入的膨胀。（注：agent-runtime.md 列示的占位格式含 `{时间戳}` 维度，但当前 messages dict 无 timestamp 字段来源，故占位简化为仅 `{尺寸}`；见 design Open。）
- **重复工具调用去重**：对「同一工具 + 同一参数」多次调用且**结果相同**的 tool_call / tool_result 对，只保留最新一条，删除更早的等价重复（保持消息序列对 LLM 合法，不切断保留下来的 tool-pair）。去重直接**减小待摘要中段规模**（注意：`_summarize` 当前不摘 tool 消息，去重并不减小摘要 prompt 本身，而是减小中段总量、利于目标线回落与 AR13 更干净的切分）。
- 清理是压缩管线的**第一环**：AR15（清理）→ AR13（分层切分）→ AR14（增量摘要）；清理产出的更干净消息序列再交给后续阶段。
- 清理可独立交付：在 AR13 / AR14 尚未合入时，清理直接作用于现状 `_compress` 的待摘要中段，契约一致。

## Capabilities

### New Capabilities
- `compression-pre-cleanup`: 压缩前轻量清理（AR15）——进入 LLM 摘要前的纯规则预处理（毫秒级、不调 LLM）：消息 content list 内的图片 / 二进制占位块兜底替换为 `[图片：{尺寸}]`；同工具 + 同参数多次调用且结果相同的 tool_call / tool_result 对（block 粒度判等）只保留最新一条；产出更干净的消息序列供后续切分与摘要，保持序列对 LLM 合法、不产生孤立 tool_result。本 change 以 ADDED 需求叠加在 AR12 双阈值之上，不重写 AR12 既有需求。

### Modified Capabilities
<!--
本次不修改 AR12 的 `context-compression-threshold` spec。
原因：AR12（compression-dual-threshold）尚未归档、其 spec 尚未 sync 进 openspec/specs/，
若此处声明 MODIFIED 将在归档时找不到目标需求；且「压缩回落到 Tretained 目标线」需求会与 AR13 对同一目标线需求的修改互相覆盖。
AR15 的增量（摘要前纯规则清理，不改变触发与目标线语义）以本 change 自有 capability 内的 ADDED 需求承载。
管线归档顺序为 AR15 → AR13 → AR14。
-->
- （无）

## Impact

- **代码**：
  - 修改 `src/fleetent/context_mgr.py`：在 `_compress` 进入 `_summarize` 之前插入清理阶段（新增纯规则清理辅助函数：图片占位替换、重复工具调用去重）。清理函数无副作用、不调 LLM、可单独单测。
- **配置**：无新增 Settings 字段（清理为纯规则，不需部署级配置）。
- **测试**：新增 / 扩展 `tests/test_context_mgr.py`：content list 内的图片块被替换为 `[图片：…]` 占位且尺寸缺失时有兜底；同工具同参数同结果的重复 tool 对（block 粒度判等）仅留最新；结果不同或参数不同的调用不去重；一条 assistant 含多个 tool_use block 时仅当全部 tool 对都等价才删整条、否则保留；去重不产生孤立 tool_result；清理后消息序列对 LLM 合法、不切断保留的 tool-pair；清理不触发任何 LLM 调用（断言 mock 的 `get_client_and_config` 未被清理阶段调用）。
- **不影响**：`Tmax` / `Tretained` 触发与目标线判定、手动 / 错误触发入口、`estimate_tokens` 的 image 估算口径、AR13 分层切分、AR14 增量摘要、`_keep_tail` identity check、agent_loop 主循环、model fallback、终止框架；不引入新依赖（无 AI 框架、无 ORM、无云服务）。
