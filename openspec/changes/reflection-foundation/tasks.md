## 0. 前置确认

- [ ] 0.1 确认本 change 只生成 reflection report，不自动应用建议
- [ ] 0.2 确认本 change 不修改 `memory_items`
- [ ] 0.3 确认本 change 不写 `skills/`，不实现 skill proposal 审批流
- [ ] 0.4 确认本 change 不依赖 knowledge-base

## 1. Report 数据模型

- [ ] 1.1 Write failing tests: `ReflectionReport`、`ReflectionFinding`、`run_reflection` 可导入
- [ ] 1.2 Write failing tests: report 包含 id、scope、time_window、findings、created_at
- [ ] 1.3 实现 reflection public model 和 public API 占位
- [ ] 1.4 运行 `uv run pytest -x -q`，确认 1.1/1.2 红测转绿

## 2. Trace 输入

- [ ] 2.1 Write failing tests: `run_reflection()` 通过 `observability.query_trace_events()` 读取指定 scope/time window 的 traces
- [ ] 2.2 Write failing tests: 无 traces 时返回空 findings report，不报错
- [ ] 2.3 实现 trace query 输入层
- [ ] 2.4 运行 `uv run pytest -x -q`，确认 2.1/2.2 红测转绿

## 3. Memory 输入只读

- [ ] 3.1 Write failing tests: `run_reflection()` 可读取 memory-layer 信号用于分析
- [ ] 3.2 Write failing tests: reflection 不调用 memory create/update/delete 写回 API
- [ ] 3.3 实现 memory 只读输入边界
- [ ] 3.4 运行 `uv run pytest -x -q`，确认 3.1/3.2 红测转绿

## 4. Finding 生成

- [ ] 4.1 Write failing tests: 重复出现的用户事实生成 `memory_candidate` finding
- [ ] 4.2 Write failing tests: 相互矛盾的事实生成 `memory_conflict` finding
- [ ] 4.3 Write failing tests: 重复任务模式生成 `skill_opportunity` finding
- [ ] 4.4 实现 deterministic finding 生成规则；LLM 分析可留为后续增强，不作为本 change 必需
- [ ] 4.5 运行 `uv run pytest -x -q`，确认 4.1/4.2/4.3 红测转绿

## 5. Report 持久化

- [ ] 5.1 Write failing tests: Alembic upgrade 后存在 reflection-owned `reflection_reports` 表
- [ ] 5.2 Write failing tests: `run_reflection()` 可保存 report，payload 不包含完整 trace transcript
- [ ] 5.3 新增 migration 和保存逻辑
- [ ] 5.4 运行 `uv run pytest -x -q`，确认 5.1/5.2 红测转绿

## 6. 不自动应用建议

- [ ] 6.1 Write failing tests: 生成 `memory_candidate` 或 `memory_conflict` 不修改 `memory_items`
- [ ] 6.2 Write failing tests: 生成 `skill_opportunity` 不创建、更新或删除 `skills/` 文件
- [ ] 6.3 实现/确认只读保护
- [ ] 6.4 运行 `uv run pytest -x -q`，确认 6.1/6.2 红测转绿

## 7. 收尾验证

- [ ] 7.1 运行 `uv run pytest -x -q`
- [ ] 7.2 运行 `uv run ruff format src tests`
- [ ] 7.3 运行 `uv run ruff check src tests`
- [ ] 7.4 运行 `uv run mypy src`
- [ ] 7.5 运行 `openspec validate reflection-foundation`
