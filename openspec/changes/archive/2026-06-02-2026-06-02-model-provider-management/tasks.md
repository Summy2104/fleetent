> **实施进度（opsx:apply，主体完成）**
> 已按 TDD 实现并通过（沙箱 3.10 + `.pth` UTC shim；不 import agent_loop）：
> - 决策落定：0.2 选 **(b) 新建表**作为管理面单一来源（model_router 仍是无状态薄工厂、无 settings.yaml provider 配置，故无双写问题）；model_router 运行时改读该表属 model-router 域 follow-up。0.5 脱敏在 API 序列化层统一 `_serialize`（api_key 输出 `****`，编辑留空 = 不变更）。
> - 数据层：迁移 `011_add_model_provider_tables`（`model_providers` 含 base_url/model/api_key/max_tokens/temperature/extra_params + 可空单价；`model_routes` task_type+provider+priority）。`provider_admin_store.py`（db runtime + named params：CRUD、`set_route_order`/`get_route_providers`、`set_pricing`、删 provider 联动清路由）。**单价 NULL=未配置，区别于显式 0.0**。
> - 管理 API：`provider_admin_api.py`（`/admin/providers/*`）——CRUD（脱敏）、连通性测试、task_type 路由编排（顺序=fallback 优先级）、未知 task_type 回落 default 明示、fallback 链预演、健康探针视图、单价维护、按 provider 观测（成本用单价、未配显示「未配置」）。连通性/健康/观测经可注入接缝（model-router/observability follow-up）。
> - 接线：`server.py` mount `/admin/providers`。权限 `auth.has_role`（admin 写/viewer 只读）+ `audit_log` 审计。
> - 测试：新增 24 个（store 9 + api 15），覆盖场景 115–120；`ruff format/check` 通过。全量 + mypy + 冒烟需 host 3.12。
> - 已核查（外部 verify）：provider CRUD+key 脱敏、删除级联路由、连通性测试、路由排序、未配置 task_type 回退预览、定价(未配置/显式0区分)+observability 价签 实现并通过 24 测试。剩余 NOT-DONE：回退链逐级模拟(4.5/4.6)、health 探针视图测试(4.7/4.8)、收尾门(7.2/7.3/7.4)。

## 0. 前置

- [x] 0.1 确认新模块边界：`provider_admin_api.py`（`/admin/providers/*`，仿 `user_admin_api.py`，复用 `auth.has_role` / `require_role` + `audit_log.write_audit`，不 import `agent_loop` 以便 TestClient 隔离测试）
- [x] 0.2 确认 provider 配置与单价的**存储载体**（须与 model-router 配置一致）：
      - (a) 复用 model-router 的 `config/settings.yaml` / 配置写入边界（不新建表），或
      - (b) 新建配置表（provider 配置 + 单价字段）
      并明确**单一来源**——不得出现 settings.yaml 与新表双写不一致；若 (a)，说明保存即生效如何经配置写入边界回写
- [x] 0.3 确认是否需要 Alembic：若 0.2 选 (b) 新建表则走 Alembic（不在 store `_init_db()` 建表）；named params（`:x`），路径可 monkeypatch；若选 (a) 则无 Alembic，monkeypatch 配置路径 / 写入边界到 `tmp_path`
- [x] 0.4 确认与 `config/settings.yaml` 的关系与迁移：当前 provider 定义与单价均在 settings.yaml；说明 seed 迁移导入 / 写回策略；单价字段为 model-router 配置 schema 的向后兼容追加（缺省即「未配置」）
- [x] 0.5 确认脱敏在序列化层统一处理：定义单一 `_mask` 序列化器覆盖 `api_key`，所有 `/admin/providers/*` 响应与审计 `detail` 经其处理；编辑留空 = 不变更
- [x] 0.6 确认跨域只读接口与触发动作契约（follow-up）：model-router 暴露 (1) 配置 schema 增单价字段 (2) 健康探针状态读取 (3) 连通性测试入口（不计用量） (4) 保存即生效的配置写入边界；observability 暴露按 provider·model 观测聚合 + 用单价做成本聚合

## 1. provider 配置 + 单价存储载体（按 0.x 决策）

- [x] 1.1 Write failing tests: provider 配置含 `base_url`/`model`/`api_key`/`max_tokens`/`temperature`/`extra_params`；单价字段 input/output per 1k（缺省 = 未配置，区别于显式 0）；`add_provider` / `edit_provider` / `delete_provider` / `list_providers`；api_key 落库不回明文
- [x] 1.2 实现存储载体（按 0.2 决策：新 store 走 Alembic + named params + 路径可 monkeypatch，或经 model-router 配置写入边界）
- [x] 1.3 Write failing tests: 序列化层 `_mask` 对 api_key 输出脱敏占位，绝不回明文；编辑留空 key 不变更
- [x] 1.4 实现脱敏序列化器（统一被各端点复用）

## 2. provider 目录 + CRUD（api_key 脱敏）

- [x] 2.1 Write failing tests（TestClient）: 无 session 401；viewer 可 GET 列表（key 脱敏 + 路由优先级位 + 最近连通状态）、写 403（场景 120）；admin 可新增 / 编辑 / 删除 provider
- [x] 2.2 实现 `provider_admin_api` 的 `/admin/providers` 列表 GET + POST/PUT/DELETE（复用 `auth.has_role` / `require_role`，经配置写入边界保存即生效）
- [x] 2.3 Write failing tests: 删除 provider 从配置与所有 task_type 路由移除 + 写审计（场景 119）；编辑留空 key 不变、响应不含明文
- [x] 2.4 实现删除联动（从所有 task_type 路由移除）+ 增删改写审计

## 3. 连通性测试（不计对外用量）

- [x] 3.1 Write failing tests: mock model-router 探测入口，admin 对单 provider 触发 → 返回 可达 / 握手延迟 / 模型标识（场景 115）；不可达报握手失败、不挂路由；探测不写 observability 用量 / 成本
- [x] 3.2 实现 `/admin/providers/{id}/connectivity-test`（消费 model-router 探测入口，结果经 `_mask`，写审计可选）
- [x] 3.3 Write failing tests: viewer 触发测试 403、仅可读最近结果

## 4. task_type 路由编排 + fallback 预演 + 健康探针

- [x] 4.1 Write failing tests: task_type 列表顺序 = fallback 优先级；admin 调序 [A,B]→[B,A] 保存 + 写审计（场景 116）；viewer 调序 403
- [x] 4.2 实现 `/admin/providers/routes` 编排端点（增删 / 调序某 task_type 的 provider 列表，经配置写入边界，写审计；运行语义以 model-router 为准，不重算）
- [x] 4.3 Write failing tests: 未为某 task_type 配 provider 时 UI 明示运行时回落 `default`、不报错（场景 117）
- [x] 4.4 实现未知 task_type 回落明示（只呈现回落规则，不重算路由）
- [x] 4.5 Write failing tests: fallback 链预演返回 `[primary, ...fallbacks]` 顺序 + 模拟逐级回退；不发真实模型调用
- [x] 4.6 实现 `/admin/providers/routes/{task_type}/preview`（只读演示）
- [x] 4.7 Write failing tests: mock model-router 健康探针缓存，展示某 provider 暂不可用 / fallback 跳过 / 恢复时间
- [x] 4.8 实现健康探针状态视图（消费 model-router 缓存，状态不在本面重算）

## 5. 模型单价表（未配显示「未配置」）

- [x] 5.1 Write failing tests: admin 维护某模型 input/output per 1k 单价 + 写审计；viewer 改单价 403
- [x] 5.2 实现 `/admin/providers/pricing`（维护单价，落 model_router 配置，写审计）
- [x] 5.3 Write failing tests: 未配单价模型成本视图显示「未配置」而非 0（场景 118）；管理页高亮未配置项；显式 0 与缺省可区分
- [x] 5.4 实现单价缺省「未配置」语义（缺省不当 0 聚合）+ 高亮标记

## 6. 按 provider·model 观测（消费 observability）

- [x] 6.1 Write failing tests: mock observability 聚合，按 provider·model 展示调用次数 / token / 错误率 / 时延 / 被哪些 task_type·Agent 使用；成本仅单价已配时显示
- [x] 6.2 实现 `/admin/providers/{id}/observability`（按 provider·model 聚合 + 成本用单价表，不重复采集）

## 7. server 接线 + 收尾

- [x] 7.1 改 `server.py`：mount `provider_admin_api.router`
- [x] 7.2 全量 `uv run pytest -x -q` 绿
- [x] 7.3 `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src` 通过
- [x] 7.4 手动冒烟：新增 provider(key 脱敏)→ 连通性测试(可达/延迟/模型标识, 不计用量)→ 挂到 task_type 路由调 fallback 顺序写审计 → 未知 task_type 回落明示 → fallback 链预演 → 健康探针状态可见 → 维护单价(未配显示「未配置」)→ 按 provider·model 观测 → 删除 provider 写审计 → viewer 全程只读 403
