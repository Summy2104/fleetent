## Context

`kb-retire-platform-ingest`（2026-06-29）退掉 platform 侧 KB ingest，但实体抽取入口 `fleetent platform kb extract-entities`（`platform/platform_cli/kb_connectors.py`）漏网。`#4 kb-standalone-extraction`（2026-07-01）已落地架构正确的独立抽取命令 `fleetent kb-extract`（入队 → kb-worker 单写者消费、`--config kb-service.yaml`、零 platform 依赖）。本 change 是纯清理：退旧入口 + 删一处前端死代码 + 补 docstring。无迁移、无 schema、无端点变更。

## Goals / Non-Goals

**Goals**
- 移除冗余且反架构的 `fleetent platform kb extract-entities`，收口"platform 零 KB ingest/extraction"。
- 删除前端死 hook `useKbAgentsQuery`。
- 补 `extract_cli.py` 私有函数 docstring；文档改指向 `kb-extract`。

**Non-Goals**
- 不折叠 `ingest_text` 三层（wrapper 注入默认 settings/db，是有意的 public API 边界）。
- 不改 `/admin/kb/{kb_id}/agents` 后端端点、不改 KB 详情 UI 行为（仍用 `bound_agents`）。
- 不改抽取本身的实现（`run_entity_extraction` / extraction schema 保持不变）。

## Decisions

**决策 1：退役而非改名 `kb_connectors.py`。**
旧命令做同步 in-process 抽取、耦合 `Settings`/`TenantRouter`，功能已被 `kb-extract` 以队列 + 单写者方式覆盖。改名只保留反架构残留；退役才收口。备选（改名为 `kb_extract_cli.py`）被否决——保留一个绕过单写者纪律的第二抽取入口无价值。

**决策 2：删 `useKbAgentsQuery`，保留 `kbAgentsKey`。**
hook 仅被测试消费，UI 走列表查询的 `bound_agents`。`kbAgentsKey` 仍被其他 hook 的 `invalidateQueries` 引用，故保留 key 与类型，仅删 hook 函数与其专属测试用例。

**决策 3：spec 层只动 `deployment`。**
唯一引用旧命令的规范是 `deployment` 的 "Pilot connector operation guidance"（要求文档列出该命令）。改为指向 `kb-extract`。`useKbAgentsQuery`/docstring 不涉及 spec 行为，不产生 delta。

## Risks / Trade-offs

- **失去单文档同步抽取（无需 worker）** → 这正是被有意淘汰的形态；`kb-extract` 的入队 + `--wait` 已覆盖回填场景，可接受。
- **测试断言方向反转**（原断言"存在" `extract-entities`）→ 改为"不存在"守卫，与 `test_kb_admin_api.py:271` 既有 pattern 一致，降低回归风险。
- **前端删除误伤 invalidate** → 通过保留 `kbAgentsKey` 规避；跑 frontend 测试确认。

## Migration Plan

纯删除，无数据迁移。部署方若有脚本调用 `fleetent platform kb extract-entities`，改用 `fleetent kb-extract --config <kb-service.yaml> --kb <kb_id> [--wait]`。回滚 = revert commit。

## Open Questions

无。
