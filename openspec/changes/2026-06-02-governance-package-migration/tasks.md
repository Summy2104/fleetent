## 0. 前置确认

- [ ] 0.1 确认本 change 只迁移 governance 文件结构，不改业务语义
- [ ] 0.2 确认不新增数据库 migration
- [ ] 0.3 确认旧顶层文件只保留 thin shim
- [ ] 0.4 确认不迁移 runtime、platform、channels、infrastructure 文件

## 1. Package skeleton and import compatibility

- [ ] 1.1 Write failing tests: `fleetent.governance.permission_gate`、`fleetent.governance.quota`、`fleetent.governance.audit_log`、`fleetent.governance.blocklist`、`fleetent.governance.agent_policy` 可 import
- [ ] 1.2 Write failing tests: 旧路径 `fleetent.permission_gate`、`fleetent.quota`、`fleetent.audit_log`、`fleetent.blocklist`、`fleetent.agent_policy` 仍可 import 对应 public API
- [ ] 1.3 Implement: 新增 `src/fleetent/governance/` package skeleton
- [ ] 1.4 Verify green: 运行相关 import / boundary 测试

## 2. Move permission and policy modules

- [ ] 2.1 Write failing tests: permission gate 旧路径和新路径暴露同一 public API
- [ ] 2.2 Write failing tests: agent policy 旧路径和新路径暴露同一 public API
- [ ] 2.3 Implement: 迁移 `permission_gate.py` 和 `agent_policy.py` 到 `governance/`
- [ ] 2.4 Implement: 顶层 `permission_gate.py` 和 `agent_policy.py` 改为 shim
- [ ] 2.5 Verify green: 运行 permission gate / agent policy 相关测试和 `uv run pytest tests/unit -x -q`

## 3. Move quota, audit, and blocklist modules

- [ ] 3.1 Write failing tests: quota 旧路径和新路径暴露同一 public API
- [ ] 3.2 Write failing tests: audit log 旧路径和新路径暴露同一 public API
- [ ] 3.3 Write failing tests: blocklist 旧路径和新路径暴露同一 public API
- [ ] 3.4 Implement: 迁移 `quota.py`、`audit_log.py`、`blocklist.py` 到 `governance/`
- [ ] 3.5 Implement: 顶层 `quota.py`、`audit_log.py`、`blocklist.py` 改为 shim
- [ ] 3.6 Verify green: 运行 quota / audit / blocklist 相关测试和 `uv run pytest tests/integration -x -q`

## 4. Canonical imports and shim cleanup

- [ ] 4.1 Write failing tests: shim 文件不承载业务逻辑或可变状态
- [ ] 4.2 Implement: 将项目内部明显属于治理域的 import 更新到 `fleetent.governance.*`
- [ ] 4.3 Implement: 确保 shim 只 re-export public names，并定义准确 `__all__`
- [ ] 4.4 Verify green: 运行 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`

## 5. Docs and final verification

- [ ] 5.1 更新 `docs/architecture/source-module-organization-roadmap.md`，标记 governance package migration 已有 implementation spec
- [ ] 5.2 更新 OpenSpec `module-boundaries` 说明治理域 package 迁移
- [ ] 5.3 运行 `uv run ruff format src tests`
- [ ] 5.4 运行 `uv run ruff check src tests`
- [ ] 5.5 运行 `uv run mypy src`
- [ ] 5.6 运行 `uv run pytest -x -q`
- [ ] 5.7 运行 `openspec validate 2026-06-02-governance-package-migration --strict`
- [ ] 5.8 运行 `git diff --check`
