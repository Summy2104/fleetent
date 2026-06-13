# link-proposal-to-report Design

## Context

核实的运行时事实（`reflection/reflection.py` 的 `run_reflection`）：
```
findings = _generate_findings(events, memory_signals)
report = ReflectionReport(id=..., ..., findings=findings)   # report.id 此刻已在内存
for mp in generate_memory_maintenance_proposals(scope, findings): _persist_memory_maintenance_proposal(mp)
for sp in generate_skill_proposals(findings=findings):           _persist_skill_proposal(sp)
_save_report(report)                                         # 当前在 proposals 之后
return report
```
report 与 proposal 同源（同一 `findings`）同生（同一调用），但 `reflection_proposals` 无 `report_id`，因果在持久化层断裂。proposal 已带 `source_finding` + `evidence_ids`，缺的只是指向 report 行的那一跳。当前 Y 最大版本 v31。

## Goals / Non-Goals

**Goals:**
- proposal 可双向追溯到源 report（提案→报告、报告→提案）
- 运行时已存在的 report→proposal 因果在持久化层保真
- standalone / 历史 / 非反思来源行不被破坏（可空语义）

**Non-Goals:**
- 不加 DB 外键（agent 侧库一贯约定引用，§3.3 note ③）
- 不回填存量行的 report_id（上线前窗口，存量为 throwaway；历史行 NULL 即可）
- 不改 KB 域语义（KB 只产 report 不产 proposal，report_id 不涉及）
- 不改 report 或 proposal 的其余 schema / 生命周期

## Decisions

**D1：`report_id` 可空，不设 NOT NULL**
当前唯一创建者 `run_reflection` 总是先有 report，理论上可 NOT NULL;但 (a) 上线前存量行无法回填源报告;(b) 为"将来非反思来源（手工/外部触发）提案"留余地——这类提案天然无源报告。可空是更稳健的契约，且与"约定引用、消费方容忍 NULL"的孤儿契约一致。

**D2：`report.id` 以参数透传，不让持久化层反查**
`run_reflection` 中 `report.id` 在 report 构造后即可得;沿 `generate_*_proposals(..., report_id=report.id)` → `ReflectionProposal.report_id` → `_persist_*` 的 INSERT 一路透传。否决"持久化时按 scope+时间窗反查最近 report"：脆弱、可能错配并发的反思运行。

**D3：把 `_save_report` 提到 proposals 持久化之前**
让被引用的 report 行先落库，引用它的 proposal 行后落库——provenance 目标存在性更自然。无 DB FK 故非强制（note ③ 明言库内 session_id 类引用无时序保证），但既然在改这段就顺手理顺，零额外成本。

**D4：public API 暴露 `report_id`**
proposal 的 list / get / 序列化加 `report_id` 字段，否则"报告→产出提案"这一向无法查询，provenance 只完成一半。

## Risks / Trade-offs

- [并发反思运行串扰 report_id] → D2 透传同一调用内的 report.id，不反查，结构上杜绝错配
- [既有 proposal 序列化的消费方未预期新字段] → 新增可空字段，向后兼容;全仓 grep proposal 序列化消费点确认
- [测试夹具构造 proposal 时缺 report_id] → 字段可空、默认 None，既有夹具不破;新增 provenance 测试显式带 report_id

## Migration Plan

Y 新版本 `ALTER TABLE reflection_proposals ADD COLUMN report_id TEXT`（append 在当前最大版本之后，apply 时以实际为准）。forward-only、nullable、无回填。代码与迁移同 change 落地。

## Open Questions

（无——加列、可空、provenance 方向已与用户对齐。）
