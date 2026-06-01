## Why

现状 `_compress` 每次压缩都把「待摘要中段」整段重新交给 LLM 摘要，生成一条全新的摘要消息（`[Earlier conversation summary]\n{text}`）。长会话会被压缩多次，每次都**从头重摘**已经摘过的内容：既浪费 LLM 调用（重复摘旧内容），又因为每次摘要文本都不同而**改写历史前缀**，使 LLM 的 prompt 缓存命中失效（与 AR12 抑制频繁压缩的初衷相悖）。

此外现状摘要有一个隐患：

- **摘要文本无来源标注**：注入的摘要前缀仅写 `[Earlier conversation summary]`，没有明确告诉 AI「这是历史对话摘要，仅供参考，不是新的用户指令」。AI 可能把摘要里的某句话误当成当前要执行的新命令。

**关键事实（修订）**：首次压缩后，旧中段消息已被物理移除——压缩输出为 `[*system头, summary_msg, *尾部]`，被摘的中段不再留在消息序列里。因此**第二次压缩时的「待摘中段」就是「上一条 summary_msg 之后到尾部之前的全部消息」**，本身已是「新增」的，**不需要任何 `covered_boundary` 边界标记**，也不需要把边界字段对 LLM 透明剥离。真正需要在多次压缩间延续的，只是**上一条 summary_msg 里的累积摘要文本 `prev_summary`**——而它本就作为一条普通 system 消息随 `session_mgr.save` 原样持久化、随 `session_mgr.load` 原样回来。增量摘要只需在压缩时**识别出这条 summary_msg、提取其 `prev_summary` 文本**，与当前中段合并即可。

AR14 要让多次压缩**增量化**：把「上一条摘要消息提取出的 `prev_summary` + 当前中段」合并为新累积摘要，而非重摘全部历史；摘要文本必须标注「这是历史对话摘要，仅供参考」；摘要失败时降级为静态保留头尾 + 截断中段，绝不崩溃。

## What Changes

- **增量摘要**：当会话已存在上一次压缩产生的摘要消息时，本次压缩 MUST 从该摘要消息提取 `prev_summary` 文本，与当前中段（上一条摘要消息之后、尾部之前的消息）合并为新累积摘要，而非重摘全部历史。无已有摘要消息时退化为对全部中段的全量摘要。
- **摘要来源标注**：摘要消息文本 MUST 显式标注「这是历史对话摘要，仅供参考」（防止 AI 将摘要内容误作新指令），替换现状仅 `[Earlier conversation summary]` 的弱标注。该标注前缀同时作为压缩时识别「这是上一条累积摘要消息」的依据。
- **摘要失败降级**：当 LLM 摘要调用失败（异常 / 超时 / 空响应）时，MUST 降级为静态保留头尾 + 截断中段（不调 LLM 的纯规则兜底），返回合法可用的消息序列，绝不抛异常中断主循环。
- **跨加载延续（无需新增持久化结构）**：累积摘要本就作为一条普通 system 摘要消息随 `session_mgr.save`/`load` 原样往返；本 change **不**新增伴随文件 / 数据库表 / 边界字段，仅要求压缩时能识别该摘要消息并提取 `prev_summary`，使重新加载后下一次压缩在已有摘要基础上继续增量。
- 不改 `Tmax` / `Tretained` 触发与目标线、手动 / 错误触发入口、分层切分（AR13）与尾部 tool-pair 完整性；不改 `maybe_compress` / `compress_for_context_overflow` 的 `list → list` 签名。

## Capabilities

### New Capabilities
- `compression-incremental-summary`: 上下文压缩的增量摘要策略（AR14）——多次压缩时从上一条摘要消息提取 `prev_summary`，与当前中段合并，不重摘旧内容；摘要文本标注「历史对话摘要，仅供参考」防误读（该前缀亦作识别上一条摘要消息的依据）；摘要失败降级为静态保留头尾 + 截断中段不崩溃；累积摘要随既有 session 持久化（普通 system 摘要消息原样往返）支持跨加载的增量延续，不新增持久化结构。本 change 以 ADDED 需求叠加在 AR12 双阈值之上，不重写 AR12 既有需求。

### Modified Capabilities
<!--
本次不修改 AR12 的 `context-compression-threshold` spec（该 spec 尚未 sync 进 openspec/specs/，AR12 未归档）。
增量摘要、来源标注、失败降级、跨加载延续全部以本 change 自有 capability 内的 ADDED 需求承载。
管线归档顺序为 AR15 → AR13 → AR14（本 change 为末环）。
-->
- （无）

## Impact

- **代码**：
  - 修改 `src/fleetent/context_mgr.py`：`_compress` 在切分出中段后，先识别消息序列中是否已存在上一条累积摘要消息（按来源标注前缀识别），存在则提取其 `prev_summary` 文本；`_summarize` 改为增量摘要（`prev_summary` + 当前中段 → 合并摘要），无 `prev_summary` 时全量；摘要消息文本加来源标注；摘要失败走静态兜底（截断中段，不调 LLM）。
  - **不改 `maybe_compress` / `compress_for_context_overflow` 签名**（仍 `list → list`），**不改 `session_mgr`**：累积摘要作为普通 system 摘要消息随既有整列表持久化往返，无需新增伴随结构、无需边界字段、无需对 LLM 透明剥离。
- **配置**：无新增必填 Settings 字段。若累积摘要最大长度需可配，复用既有 config dict 注入模式，不引入全局可变状态。
- **测试**：扩展 `tests/test_context_mgr.py`：增量摘要从上一条摘要消息提取 `prev_summary`、只把 `prev_summary` + 当前中段交 LLM、不重摘旧内容；无已有摘要消息时全量；摘要文本含「历史对话摘要，仅供参考」标注；摘要失败时降级为静态截断中段不抛异常；累积摘要不无限增长。持久化往返（save → load → 再压缩仍在已有摘要上增量）用 `monkeypatch session_mgr.SESSIONS_DIR` 隔离验证（验证摘要消息原样往返即可，无需新增持久化结构）。LLM 摘要调用按规范 mock（`patch get_client_and_config`），失败路径用 mock 抛异常验证降级。
- **不影响**：`Tmax` / `Tretained` 触发与目标线判定、手动 / 错误触发入口、AR13 分层切分与 `_keep_tail` identity check、`session_mgr` 持久化结构与签名、agent_loop 主循环、model fallback、终止框架；不引入新依赖（无 AI 框架、无 ORM、无云服务）。
