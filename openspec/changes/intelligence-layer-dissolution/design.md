## Context

阶段1~4 完成后，原 `intelligence/` 的内容已全部平铺到顶层（vector_store / knowledge_base / reflection / memory / long_term_ctx），`intelligence/` 仅剩 re-export shim。此前分层靠 proposal 约定和 review 维持，没有机器强制——容易随时间漂移。本 change 收口：删干净 + 上护栏 + 改契约。

纲领 §6 的依赖规则（待强制）：

```
long_term_ctx · reflection ─▶ memory · knowledge_base.retrieval ─▶ vector_store · 各域 core
runtime ─▶ long_term_ctx · memory · knowledge_base.retrieval
platform ─▶ knowledge_base.ingest · vector_store · (reflection 审批 API)
memory · knowledge_base ──✗──▶ long_term_ctx · reflection
knowledge_base.retrieval ──✗──▶ knowledge_base.ingest
任何组件 ──✗──▶ platform
```

## Goals / Non-Goals

**Goals:**
- 物理删除 intelligence/ 与所有过渡 shim，调用方无残留。
- 把纲领 §6 依赖规则升级为 CI 强制护栏。
- CLAUDE.md 契约与新架构一致。

**Non-Goals:**
- 不改任何行为；不动组件内部。
- 不引入运行时新依赖。

## Decisions

### D1：护栏用自写测试断言，不引 import-linter（待确认）
默认方案：写一个 `tests/` 下的护栏测试，用 AST / 模块 import 静态检查断言禁止的依赖边（如 `knowledge_base.retrieval` 不得 import `knowledge_base.ingest`；任何组件不得 import `fleetent.platform`）。阶段1 已用过同类轻量断言，零新依赖，符合 fleetent 保守风格。

- *替代*：引入 `import-linter`（成熟、声明式 contract）。但它是新 dev 依赖，需走"新依赖讨论"流程；且自写断言已够覆盖这几条规则。**留作待确认**——若规则增多/复杂，再考虑 import-linter。

### D2：shim 删除集中在本阶段
各阶段（1~4）迁移期保留的 re-export shim，统一在本阶段确认无调用方后删除，避免每阶段都纠结删除时机。删前用全仓 grep + 护栏测试双重确认。

### D3：CLAUDE.md 改动范围
按纲领 §8 六条，集中改三处：架构目录树（移除 intelligence/ 节点、平铺组件）、Forbidden Patterns（更新依赖禁令、KB 读写边界）、Agent/Platform 解耦章节（组件定位、自进化审批门、清理待审计依赖条目）。

## Risks / Trade-offs

- **删 shim 漏掉调用方** → 护栏测试 + 全仓 grep 双保险；CI 全绿才删。
- **护栏测试误报/漏报** → 先覆盖纲领 §6 的明确禁止边，宁严勿漏；规则以 §6 为准。
- **CLAUDE.md 与代码不同步** → 本阶段同一 PR 内改代码 + 改 CLAUDE.md，保持原子。

## Migration Plan

1. 确认阶段1~4 已合并、调用方全迁移。
2. 写护栏测试（覆盖 §6 禁止边）→ 此时若有残留违规 import 会红。
3. 修残留 → 绿。
4. 删除所有过渡 shim + 空的 intelligence/ 目录。
5. 同 PR 更新 CLAUDE.md（§8 六条）。
6. 全量测试 + check_test_layers 绿。

## Open Questions

- 护栏工具最终选型（D1）——倾向自写断言，待 Randy 确认。
- 是否顺带把 `governance/` 自身的 agent 治理 / platform 治理混杂问题一起理（纲领 §9 标注为另一条线，倾向不扩入本阶段）。
