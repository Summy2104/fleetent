## 1. skill_hits 表 + store

- [x] 1.1 Write failing test（integration, 真实 DB+migration）：record_hit 写入后 observe(skill) 返回真实 hits 计数 + 去重 sessions，stale=False
- [x] 1.2 运行确认红
- [x] 1.3 实现：migration 057 建 skill_hits 表（id PK / skill_name / agent_id / session_id / triggered_at + index）；skill_admin_store 加 record_hit + observe
- [x] 1.4 运行确认绿

## 2. read_skill 记录命中（best-effort）

- [x] 2.1 Write failing test（unit）：read_skill 成功 load 后调 record_hit（mock 验证 + 传入 tool_context 的 agent/session）；record_hit 抛异常时 read_skill 仍返回正文；audit_blocked/未知名不记
- [x] 2.2 运行确认红
- [x] 2.3 实现：read_skill 成功分支 best-effort try/except 调 skill_admin_store.record_hit（import 函数内）
- [x] 2.4 运行确认绿

## 3. engine_observability 接真实数据

- [x] 3.1 Write failing test（unit）：engine_observability 调 skill_admin_store.observe（mock 验证透传，非 stale 占位符）
- [x] 3.2 运行确认红
- [x] 3.3 实现：skill_admin_api.engine_observability 改调 skill_admin_store.observe
- [x] 3.4 运行确认绿

## 4. 验证与收尾

- [x] 4.1 运行相关测试：observability integration + skill_admin_api + builtin_tools_skill
- [x] 4.2 运行全套测试：`uv run pytest -q`
- [x] 4.3 运行 lint + 类型检查：ruff + mypy（store / api / builtin_tools）
- [x] 4.4 运行测试层级检查
