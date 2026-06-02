## 0. 前置确认

- [x] 0.1 确认本 change 只改文档，不改代码
- [x] 0.2 确认 legacy shim cleanup 已完成，当前文档应使用 canonical package 作为实现位置
- [x] 0.3 确认 `docs/archive/**` 和 `openspec/changes/archive/**` 不纳入修改范围

## 1. Architecture docs sync

- [x] 1.1 检查 `docs/architecture.md` 中的 legacy package / module path
- [x] 1.2 将当前架构图、模块清单和数据流改为 canonical package 名称
- [x] 1.3 确认能力域文档索引仍指向 `owner-capability-roadmap.md`

## 2. Capability docs sync

- [x] 2.1 更新 `docs/capabilities/memory.md`，使用 `fleetent.intelligence.memory`
- [x] 2.2 更新 `docs/capabilities/long-term-ctx.md`，使用 memory canonical public API
- [x] 2.3 更新 `docs/capabilities/reflection.md`，使用 memory canonical public API
- [x] 2.4 更新 `docs/capabilities/vector-store.md`，使用 memory canonical package 名称
- [x] 2.5 更新 `docs/capabilities/mcp.md` 和 `docs/capabilities/connectors.md`，使用 `fleetent.integrations.mcp`
- [x] 2.6 更新 `docs/capabilities/sandbox.md`，使用 `fleetent.integrations.sandbox`
- [x] 2.7 更新 `docs/capabilities/governance.md`、`tools.md`、`im-gateway.md` 中的 governance canonical package 名称
- [x] 2.8 更新 `docs/capabilities/platform.md` 中的 admin CLI canonical entrypoint 表述
- [x] 2.9 检查 `docs/capabilities/owner-capability-roadmap.md` 是否需要同步 package migration 状态

## 3. Search and consistency checks

- [x] 3.1 搜索 `docs` 中的 `memory_layer`、`mcp_client`、`sandbox_client`、`permission_gate`、`agent_policy`、`fleetent.admin`
- [x] 3.2 逐项判断：当前文档应改；archive 或术语概念可保留
- [x] 3.3 搜索当前 docs / OpenSpec specs 中的 `intelligence-roadmap`，确认不再出现

## 4. Verification

- [x] 4.1 运行 `openspec validate 2026-06-02-capability-docs-package-path-sync --strict`
- [x] 4.2 运行 `git diff --check`
