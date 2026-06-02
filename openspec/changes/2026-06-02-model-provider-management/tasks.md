## 0. 前置

- [ ] 0.1 确认新模块边界：`provider_admin_api.py`（`/admin/providers/*`，仿 `user_admin_api.py`，复用 `auth.has_role` / `require_role` + `audit_log.write_audit`，不 import `agent_loop` 以便 TestClient 隔离测试）
- [ ] 0.2 确认 provider 配置与单价的**存储载体**（须与 model-router 配置一致）：
      - (a) 复用 model-router 的 `config/settings.yaml` / 配置写入边界（不新建表），或
      - (b) 新建配置表（provider 配置 + 单价字段）
      并明确**单一来源**——不得出现 settings.yaml 与新表双写不一致；若 (a)，说明保存即生效如何经配置写入边界回写
- [ ] 0.3 确认是否需要 Alembic：若 0.2 选 (b) 新建表则走 Alembic（不在 store `_init_db()` 建表）；named params（`:x`），路径可 monkeypatch；若选 (a) 则无 Alembic，monkeypatch 配置路径 / 写入边界到 `tmp_path`
- [ ] 0.4 确认与 `config/settings.yaml` 的关系与迁移：当前 provider 定义与单价均在 settings.yaml；说明 seed 迁移导入 / 写回策略；单价字段为 model-router 配置 schema 的向后兼容追加（缺省即「未配置」）
- [ ] 0.5 确认脱敏在序列化层统一处理：定义单一 `_mask` 序列化器覆盖 `api_key`，所有 `/admin/providers/*` 响应与审计 `detail` 经其处理；编辑留空 = 不变更
- [ ] 0.6 确认跨域只读接口与触发动作契约（follow-up）：model-router 暴露 (1) 配置 schema 增单价字段 (2) 健康探针状态读取 (3) 连通性测试入口（不计用量） (4) 保存即生效的配置写入边界；observability 暴露按 provider·model 观测聚合 + 用单价做成本聚合

## 1. provider 配置 + 单价存储载体（按 0.x 决策）

- [ ] 1.1 Write failing tests: provider 配置含 `base_url`/`model`/`api_key`/`max_tokens`/`temperature`/`extra_params`；单价字段 input/output per 1k（缺省 = 未配置，区别于显式 0）；`add_provider` / `edit_provider` / `delete_provider` / `list_providers`；api_key 落库不回明文
- [ ] 1.2 实现存储载体（按 0.2 决策：新 store 走 Alembic + named params + 路径可 monkeypatch，或经 model-router 配置写入边界）
- [ ] 1.3 Write failing tests: 序列化层 `_mask` 对 api_key 输出脱敏占位，绝不回明文；编辑留空 key 不变更
- [ ] 1.4 实现脱敏序列化器（统一被各端点复用）

## 2. provider 目录 + CRUD（api_key 脱敏）

- [ ] 2.1 Write failing tests（TestClient）: 无 session 401；viewer 可 GET 列表（key 脱敏 + 路由优先级位 + 最近连通状态）、写 403（场景 120）；admin 可新增 / 编辑 / 删除 provider
- [ ] 2.2 实现 `provider_admin_api` 的 `/admin/providers` 列表 GET + POST/PUT/DELETE（复用 `auth.has_role` / `require_role`，经配置写入边界保存即生效）
- [ ] 2.3 Write failing tests: 删除 provider 从配置与所有 task_type 路由移除 + 写审计（场景 119）；编辑留空 key 不变、响应不含明文
- [ ] 2.4 实现删除联动（从所有 task_type 路由移除）+ 增删改写审计

## 3. 连通性测试（不计对外用量）

- [ ] 3.1 Write failing tests: mock model-router 探测入口，admin 对单 provider 触发 → 返回 可达 / 握手延迟 / 模型标识（场景 115）；不可达报握手失败、不挂路由；探测不写 observability 用量 / 成本
- [ ] 3.2 实现 `/admin/providers/{id}/connectivity-test`（消费 model-router 探测入口，结果经 `_mask`，写审计可选）
- [ ] 3.3 Write failing tests: viewer 触发测试 403、仅可读最近结果

## 4. task_type 路由编排 + fallback 预演 + 健康探针

- [ ] 4.1 Write failing tests: task_type 列表顺序 = fallback 优先级；admin 调序 [A,B]→[B,A] 保存 + 写审计（场景 116）；viewer 调序 403
- [ ] 4.2 实现 `/admin/providers/routes` 编排端点（增删 / 调序某 task_type 的 provider 列表，经配置写入边界，写审计；运行语义以 model-router 为准，不重算）
- [ ] 4.3 Write failing tests: 未为某 task_type 配 provider 时 UI 明示运行时回落 `default`、不报错（场景 117）
- [ ] 4.4 实现未知 task_type 回落明示（只呈现回落规则，不重算路由）
- [ ] 4.5 Write failing tests: fallback 链预演返回 `[primary, ...fallbacks]` 顺序 + 模拟逐级回退；不发真实模型调用
- [ ] 4.6 实现 `/admin/providers/routes/{task_type}/preview`（只读演示）
- [ ] 4.7 Write failing tests: mock model-router 健康探针缓存，展示某 provider 暂不可用 / fallback 跳过 / 恢复时间
- [ ] 4.8 实现健康探针状态视图（消费 model-router 缓存，状态不在本面重算）

## 5. 模型单价表（未配显示「未配置」）

- [ ] 5.1 Write failing tests: admin 维护某模型 input/output per 1k 单价 + 写审计；viewer 改单价 403
- [ ] 5.2 实现 `/admin/providers/pricing`（维护单价，落 model_router 配置，写审计）
- [ ] 5.3 Write failing tests: 未配单价模型成本视图显示「未配置」而非 0（场景 118）；管理页高亮未配置项；显式 0 与缺省可区分
- [ ] 5.4 实现单价缺省「未配置」语义（缺省不当 0 聚合）+ 高亮标记

## 6. 按 provider·model 观测（消费 observability）

- [ ] 6.1 Write failing tests: mock observability 聚合，按 provider·model 展示调用次数 / token / 错误率 / 时延 / 被哪些 task_type·Agent 使用；成本仅单价已配时显示
- [ ] 6.2 实现 `/admin/providers/{id}/observability`（按 provider·model 聚合 + 成本用单价表，不重复采集）

## 7. server 接线 + 收尾

- [ ] 7.1 改 `server.py`：mount `provider_admin_api.router`
- [ ] 7.2 全量 `uv run pytest -x -q` 绿
- [ ] 7.3 `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src` 通过
- [ ] 7.4 手动冒烟：新增 provider(key 脱敏)→ 连通性测试(可达/延迟/模型标识, 不计用量)→ 挂到 task_type 路由调 fallback 顺序写审计 → 未知 task_type 回落明示 → fallback 链预演 → 健康探针状态可见 → 维护单价(未配显示「未配置」)→ 按 provider·model 观测 → 删除 provider 写审计 → viewer 全程只读 403
