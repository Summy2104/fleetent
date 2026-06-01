# Wave-3 Apply 决策日志

> 全自主 apply 期间，遇到的冲突 / Open Question 及其自解决策记录，供 zy 最后核实。
> 每个 change 一节：遇到什么、怎么解的、影响。
> 执行顺序见 `v1.0-roadmap.md` 波次 3；硬约束 AR18(cost-budget-control) → MR2(cost-aware-routing)。
> **顺序修订（见下方「执行顺序自解决策」）**：AR20 提前到第 2 位，因其提供 T2/SB7 依赖的 `CancelToken.parent` 原语。

## 执行顺序自解决策（2026-06-01）

执行 #2 原定 tool-timeout(T2) 时核实发现：T2 与 SB7 的 spec 均**强制**依赖 `CancelToken.parent` 字段（run 级取消经 `parent` 链接传播到在途工具），而该 `parent` 原语在各 spec 中被明确**归属于 AR20（sub-agent-lifecycle）对 AR19 `cancellation.py` 的增量补全**（见 `sub-agent-lifecycle/design.md` D3）。当前 `cancellation.py` 的 `CancelToken` 只有 `deadline`、无 `parent`。

- **冲突**：原顺序把 AR20 排第 12，但 T2(#2)/SB7(#6) 依赖它先落地。roadmap 依赖列只标 T2 dep=AR5·AR19，未含 AR20——这是 spec 作者后续引入的更细耦合。
- **决策**：把 **sub-agent-lifecycle(AR20) 提前为 #2**，先落地 `parent` 原语 + `sub_agent_runs` 表，再做 T2、SB7。其余顺序与轨道分组不变；AR18→MR2 硬约束仍满足。
- **核实**：`compression-trace` 的 "parent" 仅指 `TRACE_PATH.parent`（文件路径），与 CancelToken 无关，不受影响。

## 执行进度（修订后顺序）

| # | 阶段/轨 | change | roadmap | 状态 |
|---|---|---|---|---|
| 1 | C | tool-arg-sanitization | T3 | ✅ 已完成 |
| 2 | A | sub-agent-lifecycle | AR20 | 🔵 进行中 |
| 3 | C | tool-timeout | T2 | ⬜ |
| 4 | C | tool-result-truncation | T4 | ⬜ |
| 5 | C | tool-call-guardrails | AR10 | ⬜ |
| 6 | F | sandbox-output-truncation | SB6 | ⬜ |
| 7 | F | sandbox-exec-timeout | SB7 | ⬜ |
| 8 | B | compression-trace | AR16 | ⬜ |
| 9 | B | compression-anti-flap | AR17 | ⬜ |
| 10 | E | mcp-degradation | MCP4 | ⬜ |
| 11 | H | scheduled-task-session-binding | S3 | ⬜ |
| 12 | A | cost-budget-control | AR18 | ⬜ |
| 13 | D | cost-aware-routing | MR2 | ⬜ |

---

## tool-arg-sanitization（T3）— feat/tool-arg-sanitization

**实现：** 在 `eval_logger` 序列化层（与 `_placeholder_images` 同层、同范式）新增 `_redact_tool_calls`/`_redact_tool_call`：序列化 assistant 消息时，解析其 `tool_calls[].function.arguments`（LLM 产出的原始 JSON 字符串），把**顶层参数名**命中 `sandbox_secrets.is_sensitive_name` 的值替换为占位符 `[REDACTED]`，再重新序列化回 JSON 字符串保持 trace 形态。`_serialize` 改为 `_redact_tool_calls(_placeholder_images(...))` 组合两道脱敏。复用 SB5 单一规则源（`from fleetent import sandbox_secrets`，monkeypatch `SENSITIVE_TOKENS` 即时生效），未在 `eval_logger` 另立常量。

**自解决策（针对 design 的 Open Questions，全部自行拍板并记录）：**
1. **占位符形态**：design OQ 问 `***` / `[REDACTED]` / `ab***yz` 哪种。**定为 `[REDACTED]`**，提为模块级常量 `REDACTED_PLACEHOLDER` 作单一事实来源（测试引用该常量、不硬编码）。理由：审计语义最清晰、不暴露任何原值前后缀，且 `_placeholder_images` 本就用方括号风格 `[图片：…]`，方括号占位符与既有范式一致。
2. **是否在 trace entry 加"曾发生脱敏"布尔标记**：design OQ 倾向需要。**本 change 不做**。理由：spec 的 4 条 Requirement 与全部 scenario 均只约束"逐条消息脱敏"，未要求该标记；加它需把状态从逐消息 transform 上抛到 entry 组装层，破坏 `_serialize` 的纯函数/逐条洁净性。归属与形态留作后续 change 与 trace owner 对齐（design 原文亦许可"实现期对齐"）。
3. **脱敏粒度**：只处理解析后 arguments **顶层键**（即工具的直接参数名）。嵌套 dict 不递归——spec scenario 皆为顶层参数，递归属过度工程且易误杀；与"仅名过滤"边界一致。
4. **非法 JSON 容错**：`function.arguments` 解析失败（`JSONDecodeError`/`ValueError`）或解析结果非 dict 时，原样返回该 tool_call、不抛异常（退化为既有行为），满足 design Risks 的容错要求。
5. **路径穿越保护（任务 5.1）**：按 design D3 仅文档重定向，本 change 不产出 safe_path 代码/测试。

**影响：**
- 改 `src/fleetent/eval_logger.py`（+1 常量 +2 函数 +`_serialize` 组合）、`tests/test_eval_logger.py`（+9 测试）。
- 测试：`test_eval_logger.py` 36 passed（既有 27 + 新增 9）。全量 1036 passed（基线 1027 + 9），**170 个失败为 `feature/zhangyang` 基线预存**（webhook 等，与本 change 无关，已 stash 对比确认零回归）。
- ruff：仅对改动文件 `format`+`check` 全绿（未跑全仓 `ruff format`，避免重排无关文件）。
- mypy：`uv run mypy src` 74 errors，与基线一致，`eval_logger.py` 零错误，无新增。

**需 zy 核实：**
1. 占位符定为 `[REDACTED]`（自解决策 #1）是否认可。
2. 不加"曾脱敏"布尔标记（自解决策 #2）是否认可；如需，后续接 trace entry 层。
3. 仅脱敏顶层键、不递归嵌套（自解决策 #3）是否够用作 v1.0 起点。
