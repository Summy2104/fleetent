# link-proposal-to-report

## Why

agent_state.db 实体关系审计（2026-06-13）发现自进化两表之间一条断掉的 provenance 链：`run_reflection` 在**同一次调用、用同一批 findings** 先建 `reflection_reports` 行（存 `findings_json`）、紧接着 `generate_*_proposals(findings)` 生成并持久化 `reflection_proposals`——report 与 proposal 同源同生、有明确因果。但持久化时 `reflection_proposals` **无 `report_id` 列**：给定一条提案查不到它出自哪份反思报告，给定一份报告也列不出它产出了哪些提案。提案本身已存 `source_finding`（finding 类型）+ `evidence_ids`——它本就想要可追溯性，却独独没连回 report 行。这是持久化时丢失的运行时因果，与本审计线一路在消灭的"断链/双真相源"同类；自进化提案要进审批生命周期、要全程可审计，缺了"为什么提这条"的源头追溯是实打实的缺口。

## What Changes

- **schema**：`runtime/agent_state_migrations.py` 在当前最大版本之后追加新版本（**不硬编码版本号**——当前 v31，以 apply 时实际最大版本为准）：`ALTER TABLE reflection_proposals ADD COLUMN report_id TEXT`。列**可空**——上线前存量行回 NULL、且为"将来可能存在的非反思来源（手工）提案"留余地
- **生成与持久化**：`ReflectionProposal` dataclass 加 `report_id` 字段；`generate_memory_maintenance_proposals` / `generate_skill_proposals` 接收并透传 `report.id`（`run_reflection` 中 report 已在开头构造、`report.id` 在内存可得）；`_persist_memory_maintenance_proposal` / `_persist_skill_proposal` 的 INSERT 写入 `report_id`
- **持久化顺序**：把 `_save_report` 提到 proposals 持久化之前，让 provenance 目标行先于引用它的提案落库（无 DB FK、不强制，符合 §3.3 note ③ 约定引用语义，但更干净）
- **public API**：proposal 的 list / get / `ReflectionProposal` 序列化暴露 `report_id`，供追溯查询（"这条提案出自哪份报告"、"这份报告产出了哪些提案"）
- **文档**：`docs/architecture/data-model.md` §3.3 图加 `reflection_reports ||--o{ reflection_proposals : "report_id 源报告"` 边，note 补一条 provenance 说明（可空：历史/非反思来源行为 NULL）

边界说明：`reflection_proposals.domain` 仅 `memory|skill`，KB 域只产 report 不产 proposal，`report_id` 语义不涉及 KB。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `reflection`: 「统一自进化数据模型（report 三域 · proposal 两域）」requirement 增加 provenance——每条 `reflection_proposals` 行 SHALL 经 `report_id` 关联生成它的源 `reflection_reports`（可空，承认 standalone/历史/非反思来源行无源报告）

## Impact

- **owning package**：`runtime`（agent_state_migrations 新版本）、`reflection`（dataclass / 生成 / 持久化 / public API）
- **public API surface**：`ReflectionProposal` 增 `report_id` 字段；`generate_memory_maintenance_proposals` / `generate_skill_proposals` 签名增 report id 参数（透传）；proposal list/get 返回结构增 `report_id` 键
- **owned tables**：`agent_state.db.reflection_proposals` 增 `report_id` 列（嵌入式 Y 新版本，forward-only，nullable）
- **config namespace**：无
- **cross-module dependencies**：无新增；纯 agent 侧库内关系（report_id 指向同库 `reflection_reports`），不触碰 agent/platform 边界
- **migration / shim plan**：Y 新版本 ADD COLUMN（nullable，存量行 NULL，无回填——上线前窗口）；无代码 shim
- **相邻切片**：无在跑 change 触碰 reflection / agent_state_migrations（已确认）
