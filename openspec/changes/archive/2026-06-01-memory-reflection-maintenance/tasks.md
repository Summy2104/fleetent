## 0. 前置确认

- [x] 0.1 确认本 change 只处理 User Memory，不实现 Shared Memory
- [x] 0.2 确认不把 `memory_items` 泛化为 `scope_type + scope_id`
- [x] 0.3 确认不允许管理员默认替用户确认 User Memory 修改
- [x] 0.4 确认不做完整 UI、CI 审批流、skill proposal apply 或 KB 写回

## 1. Memory terminology and boundary

- [x] 1.1 Write failing tests/docs check: memory capability 文档明确 Memory 是能力域，当前实现是 User Memory
- [x] 1.2 Write failing tests/docs check: reflection 文档删除“memory reflection 直接写回（自动维护）”表述
- [x] 1.3 Implement: 更新 memory / reflection capability 文档和 roadmap 边界说明
- [x] 1.4 Verify green: 运行相关 docs check 或 `git diff --check`

## 2. Proposal data model and public API

- [x] 2.1 Write failing tests: memory maintenance proposal dataclass 可从 reflection public API 导入
- [x] 2.2 Write failing tests: migration 创建 reflection-owned proposal 表，包含 user_id、action、risk、status、evidence 和 timestamps
- [x] 2.3 Write failing tests: proposal 默认状态为 `pending`
- [x] 2.4 Implement: proposal dataclasses、migration、store 和 public exports
- [x] 2.5 Verify green: 运行 `uv run pytest tests/unit/test_memory_reflection_maintenance.py -x -q`

## 3. Proposal lifecycle

- [x] 3.1 Write failing tests: pending proposal 可以 approve / reject
- [x] 3.2 Write failing tests: rejected proposal 不可 apply
- [x] 3.3 Write failing tests: expired proposal 不可 apply
- [x] 3.4 Write failing tests: apply 成功后状态变为 `applied`
- [x] 3.5 Implement: approve / reject / expire / apply 状态机
- [x] 3.6 Verify green: 运行 `uv run pytest tests/unit/test_memory_reflection_maintenance.py -x -q`

## 4. Owner-approved apply

- [x] 4.1 Write failing tests: proposal 必须绑定 `user_id`
- [x] 4.2 Write failing tests: apply 必须由 proposal owner 或显式授权策略触发
- [x] 4.3 Write failing tests: high-risk `delete` 没有 owner approval 时不能执行
- [x] 4.4 Write failing tests: apply 通过 memory-layer public API，不直接写 `memory_items`
- [x] 4.5 Implement: owner approval checks and memory-layer integration
- [x] 4.6 Verify green: 运行 `uv run pytest tests/unit/test_memory_reflection_maintenance.py -x -q`

## 5. Maintenance actions

- [x] 5.1 Write failing tests: `mark_stale` 只在 approved 或低风险自动策略开启后应用
- [x] 5.2 Write failing tests: `merge`、`rewrite`、`compact` 默认需要 owner approval
- [x] 5.3 Write failing tests: `delete` 必须 owner approval，且不能被低风险自动策略执行
- [x] 5.4 Write failing tests: `suggest_shared_memory_or_kb` 不写 User Memory，只保留 proposal
- [x] 5.5 Implement: action handlers and risk checks
- [x] 5.6 Verify green: 运行 `uv run pytest tests/unit/test_memory_reflection_maintenance.py -x -q`

## 6. Reflection integration

- [x] 6.1 Write failing tests: memory_candidate / memory_conflict 可以生成 maintenance proposals，但不修改 memory
- [x] 6.2 Write failing tests: 当前对话证据明确时可以生成适合交互中轻量确认的 proposal metadata
- [x] 6.3 Write failing tests: 疑似团队共识、项目惯例或客户背景生成 `suggest_shared_memory_or_kb`
- [x] 6.4 Implement: reflection-to-proposal generation
- [x] 6.5 Verify green: 运行 `uv run pytest tests/integration/test_memory_reflection_maintenance.py -x -q`

## 7. Observability and final verification

- [x] 7.1 Write failing tests: proposal created / approved / rejected / applied 事件可被 observability 记录或查询
- [x] 7.2 Implement: observability event hooks discovered by tests
- [x] 7.3 更新 `docs/capabilities/memory.md`
- [x] 7.4 更新 `docs/capabilities/reflection.md`
- [x] 7.5 更新 `docs/capabilities/intelligence-roadmap.md`
- [x] 7.6 运行 `uv run ruff format src tests`
- [x] 7.7 运行 `uv run ruff check src tests`
- [x] 7.8 运行 `uv run mypy src`
- [x] 7.9 运行 `uv run pytest -x -q`
- [x] 7.10 运行 `openspec validate memory-reflection-maintenance --strict`
- [x] 7.11 运行 `git diff --check`
