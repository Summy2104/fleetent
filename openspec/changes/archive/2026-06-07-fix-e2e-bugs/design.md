## Context

E2E 测试发现四个 bug，涉及 IM 网关工具过滤、DB schema 漂移、skills 扫描、standalone agent 审批流。均为现有代码路径的实现缺陷，不引入新架构依赖。

## Goals / Non-Goals

**Goals:**
- `allowed_tools: []` 语义修正：空列表 → None，与文档"空=全部允许"一致
- `approvals.id` schema 修正：INTEGER → TEXT，与代码生成的 UUID 字符串对齐
- `skills/registry.py` 支持 symlink 目录下的 SKILL.md 扫描
- standalone agent 暴露 `/approvals` 审批端点，消除死锁

**Non-Goals:**
- 不修改 permission gate 的风险分级策略
- 不变更 `allowed_tools` 的 fnmatch 匹配语义
- 不改变 approvals 表的其他列或业务逻辑

## Decisions

**Bug 1 — allowed_tools 空列表**
两处都用 `or None` 转换：
```python
# normalizer.py
allowed_tools = agent.allowed_tools or None
# agent_app.py
allowed_tools = (agent.allowed_tools + expand_plugin_patterns(agent.plugins)) or None
kwargs["allowed_tools"] = allowed_tools
```
理由：最小改动，保持 None=全部允许、非空列表=按模式过滤的语义不变。

**Bug 2 — approvals.id 类型**
新增 migration `060_fix_approvals_id_to_text.py`，用 `batch_alter_table` 把 `id` 列从 `Integer` 改为 `String(8)`，保持 primary key。
理由：Alembic 管理 schema 生命周期，不手动 DDL；`batch_alter_table` 兼容 SQLite 的 ALTER 限制。

**Bug 3 — rglob + symlink**
```python
for skill_md in base.rglob("SKILL.md", follow_symlinks=True):
```
Python 3.13 已支持此参数。

**Bug 4 — standalone agent 缺少 approval 端点**
在 `agent_app.py` 的 `build_app()` 里复用 `_default_gate`，添加与 `server.py` 相同的两条路由（无需 Bearer 认证，因 standalone 已在 IM/WebSocket 层做访问控制）。

## Risks / Trade-offs

- **Bug 2 migration**：SQLite `batch_alter_table` 实际上重建整张表，执行时需短暂锁表；但 `approvals` 表在 standalone 模式下通常为空，生产环境影响极小。
- **Bug 4 无认证**：standalone agent 的 `/approvals` 端点不加 Bearer 认证（与 `/health` 同级），依赖网络层隔离。如果需要认证，后续可独立加固。
