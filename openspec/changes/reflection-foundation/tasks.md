## 0. 前置确认

- [x] 0.1 确认本 change 只生成 reflection report，不自动应用建议
- [x] 0.2 确认本 change 不修改 `memory_items`
- [x] 0.3 确认本 change 不写 `skills/`，不实现 skill proposal 审批流
- [x] 0.4 确认本 change 不依赖 knowledge-base

## 1. Report 数据模型

- [x] 1.1 Write failing tests: `ReflectionReport`、`ReflectionFinding`、`run_reflection` 可导入
- [x] 1.2 Write failing tests: report 包含 id、scope、time_window、findings、created_at
- [x] 1.3 实现 reflection public model 和 public API 占位
- [x] 1.4 运行 `uv run pytest -x -q`，确认 1.1/1.2 红测转绿

## 2. Trace 输入

- [x] 2.1 Write failing tests: `run_reflection()` 通过 `observability.query_trace_events()` 读取指定 scope/time window 的 traces
- [x] 2.2 Write failing tests: 无 traces 时返回空 findings report，不报错
- [x] 2.3 实现 trace query 输入层
- [x] 2.4 运行 `uv run pytest -x -q`，确认 2.1/2.2 红测转绿

## 3. Memory 输入只读

- [x] 3.1 Write failing tests: `run_reflection()` 可读取 memory-layer 信号用于分析
- [x] 3.2 Write failing tests: reflection 不调用 memory create/update/delete 写回 API
- [x] 3.3 实现 memory 只读输入边界
- [x] 3.4 运行 `uv run pytest -x -q`，确认 3.1/3.2 红测转绿

## 4. Finding 生成

- [x] 4.1 Write failing tests: 重复出现的用户事实生成 `memory_candidate` finding
- [x] 4.2 Write failing tests: 相互矛盾的事实生成 `memory_conflict` finding
- [x] 4.3 Write failing tests: 重复任务模式生成 `skill_opportunity` finding
- [x] 4.4 实现 deterministic finding 生成规则；LLM 分析可留为后续增强，不作为本 change 必需
- [x] 4.5 运行 `uv run pytest -x -q`，确认 4.1/4.2/4.3 红测转绿

## 5. Report 持久化

- [x] 5.1 Write failing tests: Alembic upgrade 后存在 reflection-owned `reflection_reports` 表
- [x] 5.2 Write failing tests: `run_reflection()` 可保存 report，payload 不包含完整 trace transcript
- [x] 5.3 新增 migration 和保存逻辑
- [x] 5.4 运行 `uv run pytest -x -q`，确认 5.1/5.2 红测转绿

## 6. 不自动应用建议

- [x] 6.1 Write failing tests: 生成 `memory_candidate` 或 `memory_conflict` 不修改 `memory_items`
- [x] 6.2 Write failing tests: 生成 `skill_opportunity` 不创建、更新或删除 `skills/` 文件
- [x] 6.3 实现/确认只读保护
- [x] 6.4 运行 `uv run pytest -x -q`，确认 6.1/6.2 红测转绿

## 7. 收尾验证

- [x] 7.1 运行 `uv run pytest -x -q`
- [x] 7.2 运行 `uv run ruff format src tests`
- [x] 7.3 运行 `uv run ruff check src tests`
- [x] 7.4 运行 `uv run mypy src`
- [x] 7.5 运行 `openspec validate reflection-foundation`
