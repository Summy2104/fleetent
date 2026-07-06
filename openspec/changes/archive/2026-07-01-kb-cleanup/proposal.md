## Why

`kb-retire-platform-ingest`（2026-06-29）退掉了 platform 侧 KB ingest，但**实体抽取入口 `fleetent platform kb extract-entities` 漏网留了下来**——当时独立的抽取命令还不存在。现在 `#4 kb-standalone-extraction`（2026-07-01）已把抽取做成**架构正确的独立路径 `fleetent kb extract`**（入队 → kb-worker 单写者消费、纯 KB 服务侧、零 platform 依赖），旧的 platform 入口就成了冗余且反架构的残留：同步 in-process 抽取（绕开队列/单写者纪律）、耦合 `Settings`/`TenantRouter`、且模块名 `kb_connectors.py` 双重误导（既不做 connector、唯一职责 extract-entities 又已过时）。退掉它是收口"platform 零 KB ingest/extraction"的最后一步。

同时清掉一处前端死代码与补一处 docstring 缺口。

## What Changes

- **BREAKING（运维命令）**：移除 `fleetent platform kb extract-entities` 命令——删除 `src/fleetent/platform/platform_cli/kb_connectors.py`、在 `platform_cli/main.py` 去注册、清理引用它的单元测试断言。抽取改由独立 `fleetent kb extract` 承担（已落地）。
- 删除前端死 hook `useKbAgentsQuery`（`frontend/src/features/kb/api.ts`）——仅测试消费，产品 UI 用列表查询里的 `bound_agents`；保留 `kbAgentsKey` 供 invalidate 使用，后端 `/admin/kb/{kb_id}/agents` 端点与 UI 行为不变。
- 补 `knowledge_base/extract_cli.py` 私有辅助函数（如 `_wait_for_jobs`）的 docstring。
- 部署/运维文档不再引用 `fleetent platform kb extract-entities`，改指向 `fleetent kb extract`。

**不做**：`ingest_text` 三层（impl → wrapper → 动态导出）折叠——wrapper 层注入默认 KB settings/database，是有意的 public API 边界，折叠是倒退而非清理。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `deployment`: "Pilot connector operation guidance" 要求的文档命令清单中，移除 `fleetent platform kb extract-entities`，改为引导运维使用独立 `fleetent kb extract` 做实体抽取。

## Impact

- **代码**：删 `platform/platform_cli/kb_connectors.py`（91 行）；`platform_cli/main.py` 去注册（2 行）；`frontend/src/features/kb/api.ts` 删死 hook（~10 行）；`extract_cli.py` 补 docstring。
- **测试**：`tests/unit/test_coverage_cli_and_stats_handlers.py`、`tests/unit/test_admin_cli_commands.py`（`extract-entities` 断言改为"不存在"守卫）；`frontend/src/features/kb/api.test.tsx`（删除 hook 相关用例）。
- **文档/spec**：`deployment` spec 的 connector 运维指引 delta。
- **无迁移、无 DB schema 变更、无 API 端点变更、无 platform→agent 依赖变更**。
- 唯一能力回退：单文档同步抽取（无需 worker）——正是被有意淘汰的形态，不保留。
