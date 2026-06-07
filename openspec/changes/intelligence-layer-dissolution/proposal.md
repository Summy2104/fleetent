> **状态：较完整 DRAFT**。依赖阶段1~4 全部落地后才实施。唯一显著决策是护栏工具选型（见 design），其余较机械。

## Why

[intelligence 分层重构纲领](../../../docs/architecture/intelligence-layering.md) **阶段5（收口）**。阶段1~4 把 vector_store / knowledge_base / reflection / memory / long_term_ctx 都平铺到顶层后，`intelligence/` 目录已空（或只剩 re-export shim）。本 change 删除它，删除各阶段遗留的 shim，并把此前靠"约定"维持的分层升级为**机器强制的依赖护栏**，同时更新 CLAUDE.md 架构契约。

## What Changes

- **删除 `intelligence/` 目录**及其 re-export shim（确认无调用方残留后）。
- **删除各阶段过渡 shim**（vector_store / knowledge_base / memory 等旧路径）。
- **上依赖护栏**：用测试断言（或 import-linter，见 design）强制纲领 §6 的依赖方向规则。
- **更新 CLAUDE.md**：落地纲领 §8 的 6 条契约改动（移除 intelligence 聚合层、重新定位组件、KB 读写边界、三条判据、自进化审批门、清理待审计依赖条目）。

## Capabilities

### New Capabilities
- `module-dependency-guardrails`: 把纲领 §6 的依赖方向规则固化为可执行护栏契约（哪些 import 被禁止）。

### Modified Capabilities
<!-- 视阶段1~4 落地的 spec 而定，收口时补 -->

## Impact

- **BLOCKED ON**：阶段1~4 全部完成且调用方迁移完毕。
- 删除 `intelligence/` 目录、所有过渡 shim。
- 新增护栏测试（`tests/` 下，CI 强制）。
- 修改 CLAUDE.md（架构目录树 + Forbidden Patterns + 解耦章节）。
- 行为零变更——纯结构收口 + 契约固化。

## 待讨论决策点

1. **护栏工具选型**（见 design D1）：自写 AST/import 测试断言（无新依赖）vs 引入 `import-linter`（dev 依赖，需按"新依赖讨论"流程）。倾向前者。
