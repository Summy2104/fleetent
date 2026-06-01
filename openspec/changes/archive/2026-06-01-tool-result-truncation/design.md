## Context

主循环两处把工具结果原样写回 `messages`：
- `run()`（`agent_loop.py` 行 676）：`messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})`
- `run_stream()`（`agent_loop.py` 行 947）：`messages.append({"role": "tool", "tool_call_id": tc_data["id"], "content": result})`

`result` 来自 `tool_registry.dispatch()`，是工具返回的完整字符串，无长度约束。`context_mgr.maybe_compress`（AR12）在累计超过 `Tmax` 后压缩整段历史，但那是写入后的摊还式压缩——超大结果已先占满本轮 prompt。`loop_detector.result_digest`（`loop_detector.py` 行 70-85）已有「头尾各取 `_DIGEST_EDGE_BYTES=1024` 字符后哈希」的截断先例，可作为本 change 头尾保留策略的参照（但 digest 是为去重哈希，不写回 `messages`，与本 change 目标不同）。

`docs/capabilities/tools.md` 把「工具结果截断」列为 v1.0 规划项（「输出超过阈值（如 10k tokens）时截断 + 写 breadcrumb」），并把阈值与 breadcrumb 格式留作待决问题。本 change 把它落为 spec。

兄弟 change `sandbox-output-truncation`（SB6）对沙箱 `run_code` 的 stdout/stderr 做特化截断（stdout 50KB / stderr 10KB，按 `sandbox.md`）。`sandbox_client.py` 已用 `len(s.encode("utf-8"))` 作字节口径（SB6 落地），本 change 的字节口径与之保持一致（同仓库一致度量惯例）。关键边界：**SB6 独占 `run_code` 输出截断，T4 管其余工具**——`run_code` 经 `self_truncates` 对 T4 豁免（见 D5），二者不叠加、无数值耦合（详见 D5 与「与 SB6 边界」段）。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；禁止全局可变状态（阈值常量可 `monkeypatch`）；新模块 import → 常量 → 数据类 → 函数；mypy strict 全注解；行长 100；TDD Hard Gate；测试 mock LLM、路径隔离 tmp_path；不吞异常。

## Goals / Non-Goals

**Goals:**
- 在工具结果写回 `messages` 之前，对超过字节阈值的结果做「头尾保留 + 中间省略 + breadcrumb」截断，保证单条 `tool` 消息不超过阈值上限。
- 字节口径 `len(s.encode("utf-8"))`，与 SB6 一致（同仓库度量惯例）。
- 提供 `self_truncates` opt-out：声明 `self_truncates=True` 的工具（如 `run_code`）由其专门截断器独占截断、对 T4 豁免，T4 写回前跳过它（D5）。
- 阈值可注入（模块级常量，可 `monkeypatch`），未配置回退安全默认值 **~40KB（10k tokens 量级），不为单一工具特例抬高**。
- 截断是纯规则、零 LLM 调用、毫秒级（与 AR15 pre-cleanup 同性质）。
- trace 记录的是 LLM 实际所见的截断内容（trace 序列化 `messages`，截断在 append 之前完成）；breadcrumb 的原始/省略字节数即审计所需大小元数据。
- `run()` 与 `run_stream()` 两处共用同一截断函数（单一事实来源）。

**Non-Goals:**
- 不做 LLM 摘要（摘要属 AR12 历史压缩职责，源头截断必须零 LLM）。
- 不改 AR12 历史压缩逻辑、不改 AR12 的 token 估算口径。
- 不实现 SB6 的沙箱内 stdout/stderr 截断（属 SB6；SB6 独占 `run_code` 输出截断，本 change 经 `self_truncates` 对其豁免，不碰 `run_code`）。
- 不为 `run_code` 等大输出工具抬高 T4 默认阈值（走 `self_truncates` 豁免，而非污染通用帽）。
- 不实现完整 per-tool 阈值字典（仅做 `self_truncates` 布尔豁免，覆盖当前唯一真实需求 `run_code`）。
- 不改 `dispatch()` 的返回值本身（截断只作用于写入 `messages` 的副本）。
- 不引入新依赖、不引入 `Settings` 强制字段（接入 `Settings` 为可选增强）。

## Decisions

### D1：截断在工具结果写回点统一发生，纯函数实现

新增 `truncate_tool_result(result: str, max_bytes: int | None = None) -> str`（建议 `src/fleetent/tool_result_truncation.py`，import → 常量 → 函数）：
- 模块级 `MAX_TOOL_RESULT_BYTES: int`（安全默认，可 `monkeypatch`）作为单一阈值事实来源。
- `max_bytes is None` 时取 `MAX_TOOL_RESULT_BYTES`；调用方可按次传入覆盖。
- 在 `agent_loop.run()`（行 676）与 `run_stream()`（行 947）写回 `tool` 消息前调用：对非 `self_truncates` 工具 `content=truncate_tool_result(result)`，对 `self_truncates` 工具（如 `run_code`）跳过截断、原样写回（其输出已由专门截断器管控，D5）。

**为何**：写回点是上下文占用的唯一入口，集中在此截断可覆盖**除自截断工具外的所有**工具（含 MCP `{server}__{tool}`、connector 工具）而无需改每个工具；纯函数无副作用、易测、可注入阈值。两处写回共用同一函数避免口径漂移（与 `loop_detector` 用单一 `result_digest` 同理）。
**Alternatives**：①在 `tool_registry.dispatch()` 内截断——被否，`dispatch` 的返回值还被 `loop_detector.result_digest`、`run_stream` 的 `tool_result` SSE 事件等消费，在 dispatch 截断会改变这些下游看到的内容，越权；截断只该影响写入 `messages` 的副本。②每个工具自己截断——被否，无法统一口径、易遗漏、MCP / 动态工具无法约束。

### D2：截断策略 = 头尾保留 + 中间 breadcrumb（非摘要）

超过 `max_bytes` 时：保留头部 `head_bytes` 与尾部 `tail_bytes`（按 UTF-8 字节切，且不切碎多字节字符），中间替换为单行 breadcrumb：
```
[...工具结果已截断：原始 {orig} 字节，省略中间 {omitted} 字节...]
```
- 头尾字节预算之和 + breadcrumb 字节数 SHALL ≤ `max_bytes`（截断后结果不反超阈值）。
- 多字节字符（UTF-8）按字节切时若落在字符中段，回退到上一个完整字符边界，绝不产生非法 UTF-8。

**为何**：头尾保留兼顾「开头通常含结构/状态信息」与「结尾通常含结论/错误」，是日志/JSON/HTML 的实用折中；breadcrumb 用明确字节数告知 LLM「这里被截断了多少」，避免 LLM 误以为结果完整。纯规则零 LLM 保证毫秒级、不增成本、不引入失败点（摘要会引 LLM 调用与失败降级，属 AR12 范畴）。`loop_detector.result_digest` 已验证头尾保留在本仓的可行性。
**Alternatives**：①只保留头部（直接尾部硬切）——被否，丢掉结尾的结论/错误信息，对长日志尤其有害。②LLM 摘要——被否，违反「源头截断零 LLM」目标，且与 AR12 职责重叠。

### D3：字节口径 `len(s.encode("utf-8"))`，与 SB6 统一

阈值与切分一律按 UTF-8 字节，不按字符数、不按 token：`len(s.encode("utf-8"))`。
**为何**：与兄弟 change SB6（`sandbox_client.py` 已用 `len(s.encode("utf-8"))`）保持口径一致是同仓库的一致度量惯例；字节是确定性、无依赖、跨工具一致的度量；token 口径需 tokenizer 且因模型而异，不适合源头硬截断（token 度量留给 AR12 的估算）。docs 提到的「10k tokens」量级落为字节阈值 **~40KB（10k tokens × ~4 byte/token）**，作为 T4 通用默认。注意：口径一致此处**不**承担「防止 T4 二次截 `run_code`」职责——`run_code` 由 SB6 独占截断、对 T4 豁免（D5），T4 根本不碰它，故两道关卡不存在「同一份输出走两遍」的情形。
**Alternatives**：①按字符数 `len(s)`——被否，与 SB6 字节口径不一致；②按 token 估算——被否，引入 tokenizer 依赖且与 SB6 口径冲突。

### D4：截断作用于写回 messages 的内容；trace 记录的是 LLM 实际所见的截断内容

截断函数返回新字符串，**不改** `dispatch()` 的原始返回值。写入 `messages` 的 `content` 是截断后的副本。trace 靠 `log_run` **序列化 `messages`** 落盘，而截断在 `messages.append` **之前**完成，故 trace 记录的就是 LLM 实际所见的截断内容；breadcrumb 标明的「原始 {orig} 字节 / 省略 {omitted} 字节」即审计所需的大小元数据 + 头尾样本，正是 `eval_logger`「只记元数据/样本、不落原始大对象」的既有克制风格（参照 `_placeholder_images` 占位 base64 图片、`log_sandbox_exec` 只记 stdout/stderr 字节大小不落原文、compression-trace 只记摘要指纹 + 长度）。截断不动 `dispatch` 返回值，保证 `loop_detector.result_digest`（去重）与 `run_stream` 的 `tool_result` SSE 事件（实时展示）看到的仍是工具原始结果，行为不被本 change 改变。

> 注：本决策不再涉及「`run_code` 经 SB6 后由 T4 二次截断」——`run_code` 经 `self_truncates` 对 T4 豁免（D5），T4 不碰它，故无需「幂等防双重截断」的职责设计。`truncate_tool_result` 对自身输出保持幂等仍是良好习惯（字节口径一致使已在阈值内的输入原样返回），但它不再承担「防 SB6 后被 T4 二次截」的职责。
**为何**：trace 序列化的就是已截断的 `messages`，无法（也不应）单独保留完整结果——若为此另行 capture 完整结果入 trace，会重新引入 T4 本要避免的体积膨胀，并违背 `eval_logger` 的克制原则。
**Alternatives**：单独 capture 完整结果入 trace——被否，违背 `eval_logger`「只记元数据/样本、不落原始大对象」的克制原则，重新引入 T4 要避免的体积膨胀，且需在 messages（截断版）之外再存一份完整原文（存两份）。完整原文若确需归档，属工具自身日志职责，不归通用 trace，不在本 change。
**Trade-off**：trace 随截断一并变小——LLM 所见与 trace 所记一致、不再自相矛盾，且 trace 体积同步收敛，双赢。breadcrumb 的原始/省略字节数已满足审计对大小元数据的需求。

### D5：自截断工具（`self_truncates`）对 T4 豁免

`@tool` 新增一项布尔元数据 `self_truncates: bool = False`，与 `risk_level` / `connector` / `timeout` 同范式——存放于 `tool_registry` 模块级 dict（与 `_risk_levels` / `_connectors` 平行），**不进入 LLM-facing schema**；提供 `is_self_truncating(name) -> bool` 查询。声明 `self_truncates=True` 的工具表示「自己负责截断输出」，T4 在写回 `messages` 前 SHALL **跳过**它、不施加 T4 阈值。`run_code` 声明 `self_truncates=True`：其 stdout/stderr 由 SB6 独占截断（stdout 50KB / stderr 10KB），T4 不再碰它。

**为何**：根因在于 `run_code` 既是「工具」又是「sandbox 输出」，被 `tools.md`（工具结果 ~10k tokens ≈ 40KB）与 `sandbox.md`（stdout 50KB + stderr 10KB = 60KB）两个上限同时覆盖；更具体的 `sandbox.md` 应对 `run_code` 生效。若沿用旧叙述「SB6 先截 `run_code`、T4 再兜底」，会制造「T4 阈值须 ≥ SB6 两流之和（60KB）」的脆弱数值耦合——而 T4 默认 40KB < 60KB，该声明本就破；且会产生双 breadcrumb。正确关系是**SB6 独占 `run_code` 截断、T4 管所有其他工具、`run_code` 对 T4 豁免，二者不叠加、无数值耦合**。`self_truncates` 是「per-tool 阈值」的退化版（对该工具直接无 T4 上限），比实现完整的 per-tool 阈值字典小得多，却恰好覆盖 `run_code` 这一真实需求；保持 T4 默认 ~40KB 通用帽不被单一工具污染。
**Alternatives**：①抬高 T4 默认到 64KB 迁就 sandbox——被否，每个工具都能灌 64KB（≈16k tokens），破坏 T4 通用 ~10k-token 帽。②让 T4 二次截 `run_code`（旧叙述）——被否，制造 60KB 数值耦合 + 双 breadcrumb，且违反「更具体的 sandbox.md 对 run_code 生效」。③实现完整 per-tool 阈值字典——被否，当前仅 `run_code` 一个真实需求，布尔豁免足够，per-tool 阈值留待后续。

## Risks / Trade-offs

- [按字节硬切割碎多字节字符产生非法 UTF-8] → 切分回退到完整字符边界（D2）；spec 用 scenario 覆盖「多字节字符不被切碎」。
- [breadcrumb 自身 + 头尾预算反超 `max_bytes`] → 预算分配保证「头 + 尾 + breadcrumb ≤ max_bytes」（D2）；spec scenario 断言截断后字节数不超过阈值。
- [在 `dispatch` 处截断会污染 digest / SSE / trace] → 已选择只在写回 `messages` 处截断（D1/D4），`dispatch` 返回值不变；扩充 `agent_loop` 测试断言 trace / digest 不受影响。
- [与 SB6 口径漂移] → 字节口径硬绑定 `len(s.encode("utf-8"))`（D3）；但 `run_code` 经 `self_truncates` 对 T4 豁免（D5），SB6 独占其截断、T4 不碰它，故根本不存在「同一份 `run_code` 输出走 SB6 与 T4 两遍」的双重截断情形，口径一致仅为同仓库度量惯例。
- [为迁就 sandbox 抬高 T4 默认致通用帽被破坏] → T4 默认保持 ~40KB（10k tokens 量级），**不**抬高到 64KB；`run_code` 这类大输出工具走 `self_truncates` 豁免、由各自专门截断器管控，而非抬高 T4 全局帽（D5）。
- [阈值过小截掉有用信息 / 过大失去意义] → 阈值可注入、默认取 ~40KB（10k tokens 量级）保守安全值；运维可按部署调整。

## Open Questions

- ~~默认阈值 `MAX_TOOL_RESULT_BYTES` 的具体字节量级~~ **已收敛**：默认 **~40KB（10k tokens 量级，1 token≈4 byte）**，**不为迁就 sandbox（SB6 60KB）抬高到 64KB**（否则破坏 T4 通用 ~10k-token 帽，D5）。头尾预算分配（如各 40% / breadcrumb 余量）为实现细节，由 D2 预算约束「头 + 尾 + breadcrumb ≤ max_bytes」保证。
- 阈值是否需要接入 `Settings`（可配置）还是仅模块级常量可注入即可？（本 change 至少保证模块级常量可 `monkeypatch`。）
- 是否需要**完整** per-tool 阈值覆盖（某些工具天然产出大结果）？本 change 先做全局阈值 + `self_truncates` 布尔豁免（per-tool 阈值的退化版，对声明工具直接无 T4 上限，D5），覆盖 `run_code` 这一真实需求；完整 per-tool 阈值字典留待后续。
