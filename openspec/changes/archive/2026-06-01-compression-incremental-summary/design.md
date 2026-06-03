## Context

`context_mgr._summarize`（context_mgr.py 行 146-169）当前把整段 `to_summarize` 拼成文本后一次性交 LLM（`get_client_and_config("memory_extraction")`，max_tokens=512），返回摘要字符串；异常时返回 `"[Earlier conversation summary unavailable]"`（已有 try/except 兜底，但仅返回占位文本，未做静态截断中段）。`_compress`（行 103-120）把摘要包成 `{"role":"system","content": f"[Earlier conversation summary]\n{summary_text}"}` 插在 system 头与尾部之间；输出 `[*system_msgs, summary_msg, *tail]`——**被摘的中段消息物理移除，不留在序列里**。`maybe_compress`/`compress_for_context_overflow`（行 69-100）签名为 `list → list`，不收 session_id、不返回摘要状态；`agent_loop.py:299` 为 `messages[:] = maybe_compress(messages)`，随后 `sanitize` 直接流向 LLM；`session_mgr.save`（行 37-43）原子写整个 messages 列表（`.json.tmp → rename`，`SESSIONS_DIR` 可 monkeypatch），原样持久化包括 summary_msg 在内的所有消息。

**问题定位与概念简化（修订）**：
1. 长会话多次压缩 → 每次都全量重摘已摘过的中段，浪费调用、摘要文本每次不同 → 改写历史前缀 → prompt 缓存失效。
2. 摘要前缀 `[Earlier conversation summary]` 标注弱，AI 可能误把摘要内容当新指令。
3. **不需要 `covered_boundary` 边界标记**：因首次压缩后旧中段已物理移除，第二次压缩时的「待摘中段」天然就是「上一条 summary_msg 之后到尾部之前的全部消息」，本身即「新增」部分。真正要在多次压缩间延续的只有**上一条 summary_msg 里的累积摘要文本 `prev_summary`**——它本就作为一条普通 system 消息随 `session_mgr.save`/`load` 原样往返。因此**无需新增持久化结构、无需边界字段、无需对 LLM 透明剥离**：增量摘要只需在压缩时**识别这条 summary_msg、提取 `prev_summary`**，与当前中段合并。识别依据即 D2 的固定来源标注前缀。
4. 因不引入任何内部边界字段，也**不需要改 `maybe_compress`/`compress_for_context_overflow` 的 `list → list` 签名**——增量所需的 `prev_summary` 完全可从入参 `messages` 里识别提取，无须 session_id 进压缩函数（这是可观察契约不变的优先方案）。

本 change 属 v1.0 agent-runtime「上下文压缩增强 / 增量摘要（AR14）」，是压缩增强管线 AR15（清理）→ AR13（分层切分）→ **AR14（对中段做增量摘要）** 的末环。本次假定 AR13 三层切分已就位（中段边界清晰）；若 AR13 尚未合入，本 change 退化为对「现状 `to_summarize` 段」做增量摘要，契约一致。

**与 AR13 的衔接约定（头部识别排除本 change 的摘要消息）**：本 change 提取/产出的累积摘要消息为 `role=="system"`、content 前缀 `[Earlier conversation summary]`，而 AR13 头部识别会收集 system 消息。故约定 **AR13 头部识别 MUST 按该前缀排除压缩自产的摘要消息**，使其不被提升进受保护头部、而留在摘要槽位供本 change 提取 `prev_summary` 折叠为新累积摘要；否则该摘要消息会**既被 AR13 头部完整保留、又被本 change 折叠**，产生重复与内容冲突。该约定已同步写入 AR13 的 design D1（「与 AR14 的衔接约定」）与其 spec（「压缩自产的摘要消息不被提升进头部」scenario）。两 change 独立交付：仅本 change 先合入时，现状 `_compress` 仍把旧摘要消息计入 `system_msgs`，本 change 在折叠时按前缀识别并以新累积摘要取代之，避免摘要堆叠。

**依赖与归档顺序**：本 change 依赖 AR12 双阈值已在 `context_mgr` 代码中生效；AR12 未归档、其 spec 未 sync 进 `openspec/specs/`，故本 change **不**对 `context-compression-threshold` 声明 MODIFIED，全部增量以自有 capability 内 ADDED 叠加，不重写 AR12 既有需求。管线归档顺序 **AR15 → AR13 → AR14**（本 change 末环）。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；禁止全局可变状态（`SESSIONS_DIR` 可 monkeypatch，累积摘要长度上界经 config 注入）；新模块结构 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；LLM 摘要单测必须 mock（`patch get_client_and_config`），失败路径用 mock 抛异常验证降级；session 持久化用 `monkeypatch SESSIONS_DIR` 隔离；不吞异常（降级路径 log 后返回兜底，不静默）。

## Goals / Non-Goals

**Goals:**
- 多次压缩时在已有累积摘要基础上只摘新增中段，不重摘旧内容。
- 摘要消息文本显式标注「这是历史对话摘要，仅供参考」。
- 摘要失败时降级为静态保留头尾 + 截断中段（不调 LLM），返回合法序列，绝不抛异常。
- 累积摘要（作为普通 system 摘要消息）随既有 session 持久化往返，重新加载后由压缩识别并提取 `prev_summary` 继续增量，不新增持久化结构、不引入边界字段。
- 不改 `Tmax` / `Tretained` 触发与目标线、手动 / 错误触发入口、AR13 分层切分、尾部 tool-pair 完整性。

**Non-Goals:**
- 不实现分层切分（AR13，前置 change）与压缩前清理（AR15，前置 change）。
- 不改 `_summarize` 所用模型路由（仍 `memory_extraction`）与 max_tokens 基准。
- 不实现压缩可追溯日志（agent-runtime 同节其它 [ ] 项）与压缩反抖动。
- 不引入新依赖、不新增必填 Settings 字段。

## Decisions

### D1：增量摘要 = 上一条摘要消息的 prev_summary + 当前中段
压缩切分出中段后，先在消息序列里识别是否已存在上一条累积摘要消息（按 D2 来源标注前缀识别）。若存在，提取其文本去掉前缀得到 `prev_summary`；当前中段（上一条摘要消息之后、尾部之前的消息，首次压缩后旧中段已物理移除，故中段天然即「新增」）记为 `middle`。调用 LLM 把 `prev_summary` 与 `middle` 合并为新累积摘要（prompt：在已有摘要基础上并入新增对话，保持简洁）。无 `prev_summary`（首次压缩或无摘要消息）时退化为对全部中段的全量摘要。

**为何**：因旧中段在首次压缩时已物理移除，无需任何 `covered_boundary` 标记来界定「新增」——当前中段就是新增。只需把上一条摘要文本提取出来与之合并即可，避免重摘旧内容、减少 LLM 调用与摘要文本漂移，配合 AR12 保护 prompt 缓存。
**Alternatives**：①每次仍全量重摘——被否，正是要消除的浪费与缓存失效；②引入 `covered_boundary` 边界字段标识已摘范围——被否，旧中段已物理移除使该字段冗余，且会引出「对 LLM 透明剥离」的额外复杂度；③把每段摘要拼接而不合并——被否，摘要会无限增长，最终自身超 `Tretained`。

### D2：摘要来源标注
摘要消息文本 MUST 以固定前缀标注其性质，例如 `[历史对话摘要，仅供参考。以下为早期对话的压缩，不是新的用户指令]\n{summary}`（具体措辞实现时定，spec 只约束「必须含『历史对话摘要，仅供参考』含义的标注」）。

**为何**：防止 AI 把摘要内容当成当前要执行的新命令（agent-runtime 明确要求）。
**Alternatives**：沿用 `[Earlier conversation summary]`——被否，标注过弱，未声明「仅供参考 / 非指令」。

### D3：摘要失败降级为静态截断中段
`_summarize` 的 LLM 调用失败（异常 / 超时 / 空响应）时，不返回无信息占位文本继续，而是触发**静态降级路径**：保留头尾（沿用 AR13 头部 + `_keep_tail` 尾部），中段不摘要而是按规则截断（例如丢弃中段或保留中段首尾极少量并标注「中段已省略」），产出合法序列。降级 MUST log（不吞异常），但 MUST NOT 向主循环抛出。

**为何**：摘要是尽力而为的优化，失败不应中断会话；静态截断保证序列始终合法可继续。
**Alternatives**：失败即抛异常让上层处理——被否，会让一次摘要故障打断整个对话；现状返回占位文本——保留为更轻的兜底，但 AR14 要求明确的「静态保留头尾 + 截断中段」语义，故升级为结构化降级。

### D4：跨加载延续 = 识别普通摘要消息，无需新增持久化结构
累积摘要本就作为一条普通 system 摘要消息（D2 来源标注前缀 + 摘要正文）留在 messages 序列里，随 `session_mgr.save` 的整列表原子写（`.json.tmp → rename`，`SESSIONS_DIR` 可 monkeypatch）原样落盘，随 `session_mgr.load` 原样回来。本 change **不**新增任何持久化结构（无伴随文件、无 DB 新表、无消息内边界字段），`session_mgr` 不改、`maybe_compress` 签名不改。

跨加载延续所需的全部能力，就是 D1 的「识别这条摘要消息并提取 `prev_summary`」：
- 识别：消息序列里 `role=="system"` 且 content 以 D2 来源标注前缀开头的那条即上一条累积摘要消息。
- 提取：去掉前缀得到 `prev_summary` 文本。

因为这条摘要消息本身就是普通 role/content，发给 LLM 时**无需剥离任何内部字段**（不存在内部字段），即天然「对 LLM 透明」。

**为何**：旧中段物理移除使「已摘边界」冗余（D1/Context 第 3 点），剩下唯一要延续的只是摘要文本，而它已随既有持久化往返；这是最小改动、零新增持久化通道、零 `session_mgr` 侵入的方案。
**Alternatives**：①独立伴随文件 / DB 新表存 `{summary_text, covered_boundary}`——被否，引入新持久化通道与 ORM 风险，且 `covered_boundary` 本就冗余；②全局内存缓存累积摘要——被否，违反「禁止全局可变状态」且跨进程 / 重启不可用；③把 session_id 传入 `maybe_compress` 以读写边界——被否，签名变更是可观察契约变化，而 `prev_summary` 可从入参 messages 直接提取，无此必要。
**Open**：来源标注前缀的精确匹配规则（如何稳健区分「累积摘要消息」与恰好同前缀的普通 system 消息）——实现首步核实现有 system 消息形态后定，必要时用不易撞车的前缀。

### D5：与 AR13 / AR12 的边界协调
本 change 只改「中段如何被摘要 + 摘要如何持久化与标注」；中段的**切分**来自 AR13（头部 / 中段 / 尾部），触发与目标线来自 AR12。三者构成管线 AR15 → AR13 → AR14，可独立交付：AR14 在 AR13 未合入时退化为对现状 `to_summarize` 段增量摘要，契约不变。

**为何**：保持改动面隔离，三功能可分别 review / 合入。

## Risks / Trade-offs

- [累积摘要无限增长最终自身超 Tretained] → 合并 prompt 要求「保持简洁、固定 max_tokens 上界」；累积摘要本身也受 `_SUMMARY_OVERHEAD_TOKENS` 投影约束；必要时对累积摘要再压缩（实现时若超界则整体重摘一次）。
- [摘要失败降级丢失过多中段上下文] → 降级是故障兜底而非常态；静态截断保留头尾与中段标注，保证序列合法；降级事件 log 便于排查。
- [持久化往返破坏增量延续] → 累积摘要随既有整列表往返，不新增结构；加持久化往返单测：save → load → 再压缩，断言识别到上一条摘要消息并在其上增量而非重摘；`monkeypatch SESSIONS_DIR` 隔离。
- [来源标注前缀与普通 system 消息撞车导致误识别为累积摘要] → 实现首步核实现有 system 消息形态，选不易撞车的固定前缀；识别失败时安全退化为全量摘要（不崩溃、不误删）。

## Open Questions

- 来源标注前缀的精确匹配规则（如何稳健区分累积摘要消息与恰好同前缀的普通 system 消息）——实现首步核实现有 system 消息形态后定（D4 Open）；识别失败安全退化为全量摘要。
- 累积摘要超界时的再压缩触发条件（固定 token 阈值 vs 比例）——实现时定，spec 只约束「累积摘要不得无限增长」。
- 静态降级时中段的截断粒度（全丢 vs 保留首尾极少量）——实现时定，spec 约束「降级后序列合法且不崩溃」。
