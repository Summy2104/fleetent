## 0. 前置确认

- [ ] 0.1 确认本 change 只处理 User Memory，不实现 Shared Memory
- [ ] 0.2 确认不把 `memory_items` 泛化为 `scope_type + scope_id`
- [ ] 0.3 确认不允许管理员默认替用户确认 User Memory 修改
- [ ] 0.4 确认不做完整 UI、CI 审批流、skill proposal apply 或 KB 写回

## 1. Memory terminology and boundary

- [ ] 1.1 Write failing tests/docs check: memory capability 文档明确 Memory 是能力域，当前实现是 User Memory
- [ ] 1.2 Write failing tests/docs check: reflection 文档删除“memory reflection 直接写回（自动维护）”表述
- [ ] 1.3 Implement: 更新 memory / reflection capability 文档和 roadmap 边界说明
- [ ] 1.4 Verify green: 运行相关 docs check 或 `git diff --check`

## 2. Proposal data model and public API

- [ ] 2.1 Write failing tests: memory maintenance proposal dataclass 可从 reflection public API 导入
- [ ] 2.2 Write failing tests: migration 创建 reflection-owned proposal 表，包含 user_id、action、risk、status、evidence 和 timestamps
- [ ] 2.3 Write failing tests: proposal 默认状态为 `pending`
- [ ] 2.4 Implement: proposal dataclasses、migration、store 和 public exports
- [ ] 2.5 Verify green: 运行 `uv run pytest tests/unit/test_memory_reflection_maintenance.py -x -q`

## 3. Proposal lifecycle

- [ ] 3.1 Write failing tests: pending proposal 可以 approve / reject
- [ ] 3.2 Write failing tests: rejected proposal 不可 apply
- [ ] 3.3 Write failing tests: expired proposal 不可 apply
- [ ] 3.4 Write failing tests: apply 成功后状态变为 `applied`
- [ ] 3.5 Implement: approve / reject / expire / apply 状态机
- [ ] 3.6 Verify green: 运行 `uv run pytest tests/unit/test_memory_reflection_maintenance.py -x -q`

## 4. Owner-approved apply

- [ ] 4.1 Write failing tests: proposal 必须绑定 `user_id`
- [ ] 4.2 Write failing tests: apply 必须由 proposal owner 或显式授权策略触发
- [ ] 4.3 Write failing tests: high-risk `delete` 没有 owner approval 时不能执行
- [ ] 4.4 Write failing tests: apply 通过 memory-layer public API，不直接写 `memory_items`
- [ ] 4.5 Implement: owner approval checks and memory-layer integration
- [ ] 4.6 Verify green: 运行 `uv run pytest tests/unit/test_memory_reflection_maintenance.py -x -q`

## 5. Maintenance actions

- [ ] 5.1 Write failing tests: `mark_stale` 只在 approved 或低风险自动策略开启后应用
- [ ] 5.2 Write failing tests: `merge`、`rewrite`、`compact` 默认需要 owner approval
- [ ] 5.3 Write failing tests: `delete` 必须 owner approval，且不能被低风险自动策略执行
- [ ] 5.4 Write failing tests: `suggest_shared_memory_or_kb` 不写 User Memory，只保留 proposal
- [ ] 5.5 Implement: action handlers and risk checks
- [ ] 5.6 Verify green: 运行 `uv run pytest tests/unit/test_memory_reflection_maintenance.py -x -q`

## 6. Reflection integration

- [ ] 6.1 Write failing tests: memory_candidate / memory_conflict 可以生成 maintenance proposals，但不修改 memory
- [ ] 6.2 Write failing tests: 当前对话证据明确时可以生成适合交互中轻量确认的 proposal metadata
- [ ] 6.3 Write failing tests: 疑似团队共识、项目惯例或客户背景生成 `suggest_shared_memory_or_kb`
- [ ] 6.4 Implement: reflection-to-proposal generation
- [ ] 6.5 Verify green: 运行 `uv run pytest tests/integration/test_memory_reflection_maintenance.py -x -q`

## 7. Observability and final verification

- [ ] 7.1 Write failing tests: proposal created / approved / rejected / applied 事件可被 observability 记录或查询
- [ ] 7.2 Implement: observability event hooks discovered by tests
- [ ] 7.3 更新 `docs/capabilities/memory.md`
- [ ] 7.4 更新 `docs/capabilities/reflection.md`
- [ ] 7.5 更新 `docs/capabilities/intelligence-roadmap.md`
- [ ] 7.6 运行 `uv run ruff format src tests`
- [ ] 7.7 运行 `uv run ruff check src tests`
- [ ] 7.8 运行 `uv run mypy src`
- [ ] 7.9 运行 `uv run pytest -x -q`
- [ ] 7.10 运行 `openspec validate memory-reflection-maintenance --strict`
- [ ] 7.11 运行 `git diff --check`
