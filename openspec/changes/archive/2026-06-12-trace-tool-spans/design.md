# Design — trace-tool-spans

## Context

traces 表 schema 已含 `run_id/span_id/parent_span_id/session_id/event_type/payload_json`，但事件面只有 3 种 run 级事件，且写入点（`record_injected_context(run_id, sources)`、loop 的 `log_run(...)` 调用）不传 session_id。loop 的 backfill 阶段（`runtime/loop.py` 三相执行的第三相）已有"仅真实执行触发"的判定点（`not is_placeholder`），post_tool_use hook 即挂在此处——tool_call 事件与其同点挂接，天然排除审批 placeholder 与 guardrail 短路。

## Goals / Non-Goals

**Goals:**

- 任一会话可用一条 SQL 重建"调了哪些工具、参数概要、成败、耗时"。
- 真实执行才记录：placeholder（审批挂起/guardrail 拒绝）不产生 tool_call 事件。
- 所有 run 级与 tool 级事件绑定 session_id。
- 零 schema 迁移、零新表。

**Non-Goals:**

- 嵌套 span 树（parent_span_id 暂不填充层级，列保留）；OpenTelemetry 对接；trace 采样/保留策略；平台侧 trace UI 扩展（`request-trace-view` 不动）。
- 投递回执事件（属 delivery-receipts-postcondition）。

## Decisions

### D1 挂接点 = backfill 真实执行判定点

与 post_tool_use hook 同点（`not is_placeholder` 分支），run 与 run_stream 两路一致。备选"在 dispatch 前后包裹"会把 placeholder 也记进去且与并行执行相交错；backfill 串行按原始顺序，事件顺序即工具顺序。

### D2 payload 形状与脱敏

`{tool_name, tool_call_id, args_summary, failed, duration_ms, risk}`；`args_summary` 经 `tool-arg-secret-redaction` 基线脱敏后 JSON 序列化并截断（上限 2KB），杜绝 secret 落 traces 与 payload 膨胀。耗时取 dispatch 实测（并行批内为单工具耗时）。

### D3 session 绑定方式

trace 记录函数全部增加可选 `session_id` 参数（默认 None 兼容存量调用），loop 各 `log_run`/record 调用点补传作用域内已有的 session_id。不引入全局上下文变量（避免跨 task 污染，repo 反对全局可变状态）。

### D4 失败隔离

trace 写入失败 MUST 只记 warning，不影响工具结果与 run（observability 是旁路，沿用 `_record_run` 同款 best-effort 范式）。

## Risks / Trade-offs

- [高频工具调用增加 traces 行数] → 每行 ≤2KB、无索引新增；保留策略属 future（Non-Goal），先以现有表量级观察。
- [args 脱敏遗漏新形态 secret] → 复用统一脱敏基线，基线升级自动受益；截断进一步限制暴露面。
- [sub_agent run 的事件归属] → 沿用其自身 run_id；session_id 取父会话传入值（sub_agent 无独立会话）。

## Migration Plan

纯增量：部署即生效，旧行 session_id 为空属历史数据，查询按"新事件起"解读。回滚 = 去掉写入点，无数据破坏。

## Open Questions

- 无。
