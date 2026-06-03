## Context

`context_mgr._compress`（context_mgr.py 行 103-120）确定压缩后直接 `summary_text = _summarize(to_summarize)`。`_summarize`（行 146-169）**并非**对每个 block 做 `str(block)`，而是 `text = "\n".join(f"{_role(m)}: {_content(m)}" for m in messages if _role(m) in ("user","assistant") and _content(m))`（行 149-153）——只摘 `user` / `assistant` 消息，**不摘 `tool` 消息**；其中 `_content(m)`（行 191-194）对整条消息的 `content` 做 `str(msg.get("content", ""))`。`estimate_tokens` / `_estimate_message_tokens`（行 43-53）已识别 `block.get("type")=="image_url"` 并按固定 `_IMAGE_BLOCK_TOKENS=1000` 估算（避免 base64 膨胀触发阈值），但 `_content` 在拼摘要输入时不区分 image 块——当 content 是含 image 块的 list 时，整个 list（含巨大 base64）被 `str()` 化拼进摘要文本。重复工具调用现状无任何去重。

**问题定位**：
1. **膨胀点在 `_content` 层**：含 image 块的 content list 经 `_content` 的 `str()` 把 base64 整体拼进摘要输入，膨胀 prompt 且对摘要无价值；摘要阶段只需「这里曾有图」的占位。清理应在「构造摘要输入前替换 content list 内的 image block」。
2. 同工具 + 同参数 + 同结果的 tool_call / tool_result 对在历史里冗余。注意 `_summarize` 本就不摘 `tool` 消息，故去重 tool 对**不会减小摘要 prompt 本身**；其真实收益是**减小待摘要中段总规模**、利于 `estimate_tokens` 回落到 `Tretained`、并让 AR13 的三层切分更干净。

本 change 属 v1.0 agent-runtime「上下文压缩增强 / 压缩前轻量清理（AR15）」，是压缩增强管线 **AR15（清理）** → AR13（分层切分）→ AR14（增量摘要）的第一环。清理是纯规则预处理，毫秒级，绝不调 LLM。可独立交付：AR13/AR14 未合入时，清理作用于现状 `to_summarize` 中段，契约一致。

**依赖与归档顺序**：本 change 依赖 AR12（compression-dual-threshold）的双阈值已在 `context_mgr` 代码中生效。AR12 截至本 change 尚未归档、其 spec 亦未 sync 进 `openspec/specs/context-compression-threshold/`，因此本 change **不**对该 spec 声明 MODIFIED（否则归档时找不到目标需求，且会与 AR13 对同一「目标线」需求的修改互相覆盖）。本 change 的增量（摘要前纯规则清理，不改变 `Tmax` 触发判定与 `Tretained` 目标线语义）以自有 capability `compression-pre-cleanup` 内的 ADDED 需求叠加，不重写 AR12 既有需求。管线归档顺序为 **AR15 → AR13 → AR14**。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；禁止全局可变状态（清理为纯函数，无模块级可变量）；新模块结构 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；清理 MUST NOT 调 LLM（单测断言 mock 的 `get_client_and_config` 未被清理阶段触发）；不吞异常（占位 / 去重遇异常数据用兜底，不静默崩溃）。

## Goals / Non-Goals

**Goals:**
- 在 `_compress` 进入 `_summarize` 之前插入纯规则清理阶段（毫秒级，不调 LLM）。
- content list 内的图片 / 二进制占位块替换为 `[图片：{尺寸}]`（无时间戳维度，见 Open），缺失字段有兜底。
- 同工具 + 同参数 + 同结果的 tool_call / tool_result 对只保留最新一条。
- 清理后消息序列对 LLM 合法，不切断保留下来的 tool-pair。
- 清理函数无副作用、可单独单测、不调 LLM。

**Non-Goals:**
- 不实现分层切分（AR13，后续 change）与增量摘要（AR14，后续 change）。
- 不改 `estimate_tokens` 的 image 估算口径（`_IMAGE_BLOCK_TOKENS`）。
- 不改 `Tmax` / `Tretained` 触发与目标线、手动 / 错误触发入口、阈值注入契约。
- 不对「结果不同」或「参数不同」的工具调用去重（仅去除完全等价的重复）。
- 不引入新依赖、不新增 Settings 字段。

## Decisions

### D1：清理为 `_compress` 内的纯规则前置阶段
在 `_compress` 中，确定待摘要内容后、调用 `_summarize` 之前，先过一遍清理：`cleaned = _pre_cleanup(to_summarize)`，再 `_summarize(cleaned)`。`_pre_cleanup` 为纯函数（输入消息列表 → 输出清理后的新列表），不修改入参、无副作用、不调 LLM。

**为何**：清理是摘要的预处理，逻辑上属压缩内部；纯函数易单测、可被 AR13/AR14 复用（清理产出再切分 / 增量摘要）。
**Alternatives**：①把清理塞进 `_summarize`——被否，混淆「规则清理」与「LLM 摘要」两件事，不利单测「清理不调 LLM」；②清理整个 messages（含头尾）——被否，头尾要完整保留（AR13），清理只应作用于待摘要中段。

### D2：图片 / 二进制占位兜底替换
膨胀发生在 `_content` 把含 image 块的 content list 整体 `str()` 化（见 Context）。清理在**构造摘要输入前**对消息 content list 内的 image / 二进制占位块（沿用 `estimate_tokens` 的判据：`block.get("type")=="image_url"`，以及其它已知二进制占位形态）替换为简短文本占位 `[图片：{尺寸}]`：
- 尺寸：从块元数据取（如 url 的 data 头 / 附带的 width×height）；取不到用兜底标识（如 `未知尺寸`）。
- **时间戳维度去除**：message dict 无 timestamp 字段来源（消息由 `msg.model_dump()` 产生，不含时间戳），故占位简化为仅 `[图片：{尺寸}]`，不含 agent-runtime.md 列示的 `{时间戳}` 维度（见 Open）。
- 替换后仍是合法文本块，摘要输入不再含 base64。

**为何**：摘要阶段只需「曾有图」的占位信息；消除 base64 膨胀，降低摘要 prompt 体量与成本。缺失字段兜底保证「绝不因缺元数据而崩溃」。
**Alternatives**：①直接删除图片块——被否，丢失「这里有过图」的上下文线索；②保留原 base64——被否，正是要消除的膨胀。

### D3：重复工具调用去重（同工具 + 同参数 + 同结果，block 粒度）
清理扫描 tool_call / tool_result 对，对「工具名相同 + 调用参数相同 + 结果相同」的多次出现，只保留**最新一条**（时间上最后出现的），删除更早的等价重复。判等以工具名、规范化后的参数、结果内容三者全等为准；任一不同则不去重。

**去重单位 = block 粒度**：OpenAI 兼容消息里，一条 assistant 消息的 `tool_calls` 可含**多个 tool_call block**，分别对应多条 `role=="tool"` 的 tool_result（按 `tool_call_id` 关联）。因此去重的判等与删除单位是「单个 tool_call block + 其对应 tool_result」，而非整条消息：
- 仅当某条 assistant 消息的**全部** tool_call block 都能在更新位置找到等价重复时，才删整条 assistant 消息及其全部 tool_result；
- 否则保留该 assistant 消息（连同未被去重的 block），不按消息粒度误删非重复 block，也不留孤立 tool_result。

去重 MUST 保持序列合法：被保留的 tool_call 与其 tool_result 成对保留，MUST NOT 产生孤立 tool_result。

**为何**：探索阶段对同一目标的重复读取（同路径 read_file、同目录 list_dir）冗余；去重直接**减小待摘要中段规模**（注意：`_summarize` 不摘 tool 消息，去重不减小摘要 prompt 本身，收益在中段总量与目标线回落）。保留最新一条符合「以最近状态为准」。按消息粒度删会误删非重复 block 或留孤立 result，故采用 block 粒度。
**Alternatives**：①保留最早一条——被否，最新结果更贴近当前会话状态；②对「参数相同但结果不同」也去重——被否，结果不同意味着状态变化，不能丢；③模糊判等（忽略部分参数）——被否，规则要可单测、可预测，只做严格全等去重；④按消息粒度删——被否，多 tool_call 同消息时会误删或留孤立 result。
**Open**：参数 / 结果的「规范化判等」是否需忽略空白 / key 顺序——实现首步核实工具调用记录的实际结构后定。「一条 assistant 含多个 tool_use block」的去重处置为实现首步必核项。

### D4：清理不调 LLM 且毫秒级
`_pre_cleanup` 及其子步骤（图片替换、去重）全部为本地纯规则操作，MUST NOT 调用 `get_client_and_config` 或任何 LLM。单测断言：执行清理时 mock 的 `get_client_and_config` 调用次数为 0。

**为何**：agent-runtime 明确要求清理「毫秒级，不调 LLM」；与 `_summarize`（调 LLM）严格分离。

## Risks / Trade-offs

- [图片块元数据缺尺寸致占位信息不全] → 缺失尺寸用兜底值（如 `未知尺寸`），仍产出合法占位，绝不崩溃（D2）。
- [去重误删非等价调用] → 严格全等判等（工具名 + 参数 + 结果三者全等），任一不同不去重；单测覆盖「参数不同」「结果不同」均不去重。
- [去重产生孤立 tool_result] → 去重以 tool_call/tool_result 成对为单位，保留对完整；加单测断言无孤立 tool_result，序列对 LLM 合法。
- [清理改变消息序列引入合法性回归] → 清理为纯函数、只删等价重复与替换图片块，不重排其余消息；保留并扩展 AR12 既有 `test_context_mgr` 序列合法性用例。
- [清理被误认为会调 LLM] → D4 单测断言清理阶段 `get_client_and_config` 零调用。

## Open Questions

- 图片 / 二进制占位块的全部已知形态（除 `image_url` 外是否有其它二进制占位类型）——实现首步核实 messages content block 实际类型后定判据。
- 工具调用参数 / 结果的规范化判等粒度（是否忽略空白 / key 顺序）——实现首步核实工具调用记录结构后定（D3 Open）。
- 「一条 assistant 含多个 tool_use block」的去重处置（仅当全部 block 等价才删整条，否则保留）——实现首步核实多 tool_call 消息结构后核定（D3 必核项）。
- 占位时间戳维度：agent-runtime.md 列示 `[图片：{尺寸}，{时间戳}]`，但当前 messages dict 无 timestamp 来源；本 change 简化为 `[图片：{尺寸}]`。若实现首步确认消息确有时间戳来源（如调用方注入），再决定是否补回时间戳维度。
