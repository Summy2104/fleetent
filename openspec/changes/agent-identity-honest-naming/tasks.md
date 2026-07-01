# Tasks: agent-identity-honest-naming

> 纯内部重命名 + 一处 store 键 name→id，无迁移/无 wire/无行为变更。
> TDD Hard Gate 主要作用于 §5（set_im_capabilities 的键变更，有可断言的行为）：先改测试断言按 id → 见红 → 实现 → 见绿。
> §1–§4 是机械重命名（含全部引用与测试的原子改名），无可断言的"红"，判据 = 改完受影响模块单测见绿 + grep 无旧名残留。
> 每个符号：先 `grep -rn <symbol> src tests` 定位全部引用（含测试），再逐一改，最后 grep 确认零残留旧名。

## 1. 路径 / scope 参数 `agent_id` → `agent_name`（实装 name 作路径键）

- [ ] 1.1 `paths.py`：`tenant_agent_home_dir` / `tenant_agent_data_dir`（及 `agent_home_dir` / `agent_data_dir` 若同样实收 name）的参数 `agent_id: str` → `agent_name: str`；`tenant_router.py` 的 `agent_scope(self, tenant_id, agent_id: str)` → `agent_name: str`。改所有调用点关键字实参（agent_app.py、node/backend.py、forwarder.py、backflow_store.py、materialize.py、read_projection.py 等）。
- [ ] 1.2 跑受影响单测见绿：`uv run pytest tests/unit -k "paths or tenant_router or agent_app or backend or materialize" -q`（按实际测试名收窄）。grep 确认这些函数签名与调用无残留 `agent_id`（真装 name 的位置）。

## 2. `AgentSnapshot.agent_id` → `agent_name`

- [ ] 2.1 `runtime/snapshot.py`：`AgentSnapshot` 字段 `agent_id` → `agent_name`；两个构造 `_snapshot_from_file`（装 `agent.name`）与 `_snapshot_from_agent`（装 `str(agent.id)`——注：此处历来填 str(id)，改名后字段名为 `agent_name` 仍承载"运行时 handle"，与 file 路径统一为 name 语义；如 DB 路径应改填 `agent.name` 以彻底统一，在本 task 一并校正并在 commit message 记明）。更新 `connector_scope` 等消费点（line 179）。
- [ ] 2.2 grep 全库 `AgentSnapshot`/`.agent_id`（限 snapshot 相关）改净；跑 `uv run pytest tests/unit -k snapshot -q` 见绿。

## 3. `CommandContext.agent_id` → `agent_name`

- [ ] 3.1 `runtime/commands.py` 的 `CommandContext` 字段 `agent_id` → `agent_name`；改所有消费点（commands.py:81/83/100/113/124——注意 100/124 本就把它当 `agent_name=` 传下游，改后更自洽）；改构造点 `im_gateway/normalizer.py:577`（`agent_id=agent.name`→`agent_name=agent.name`）。
- [ ] 3.2 grep `CommandContext` 引用改净；跑 `uv run pytest tests/unit -k "commands or normalizer" -q` 见绿。

## 4. `ModelPolicySnapshot.agent_id` → `agent_name`

- [ ] 4.1 `model/resolver.py`：`ModelPolicySnapshot` 字段 `agent_id` → `agent_name`；`from_models(*, agent_id=...)` 关键字参数、`from_agent`（装 `agent.name`）、消费点 `_merge(self.agent_id, ...)`（line 139）；调用点 `runtime/snapshot.py:135`（`from_models(agent_id=name,...)`）。
- [ ] 4.2 grep `ModelPolicySnapshot`/`from_models` 引用改净；跑 `uv run pytest tests/unit -k "resolver or model" -q` 见绿。

## 5. 平台 store 按 id：`set_im_capabilities(name)` → `set_im_capabilities(agent_id: int)`

- [ ] 5.1 [test-red] 改 `set_im_capabilities` 的单测：断言按 `agent.id` 调用并以 id 作 WHERE 键（构造 agent 后传 `agent.id`）。跑该测试 → **见红**（现签名收 name）。
- [ ] 5.2 [impl] `agent_store.set_im_capabilities`：参数 `name: str` → `agent_id: int`，SQL `WHERE name=:name` → `WHERE id=:agent_id`；调用点 `agent_admin_api`（IM capabilities 端点）改为先 `agent = _require_agent(name)` 再传 `agent.id`。跑同测 → **见绿**。
- [ ] 5.3 grep 确认 `set_im_capabilities` 无 name-keyed 残留、无其它调用点漏改。

## 6. `read_projection.py:124` 语义错位

- [ ] 6.1 该处已由 `get_agent_name_by_id(agent_id)` 拿到 name 再传 `agent_scope`；配合 §1 的参数改名（`agent_scope(tenant_id, agent_name=...)`），确认此处传的是 name 且关键字实参名与新签名一致，消除"参数叫 id 实传 name"错位。跑 `uv run pytest tests/unit -k read_projection -q`（或相应集成）见绿。

## 7. 文档对齐

- [ ] 7.1 `docs/architecture/agent-home-layout.md`：把 25-28 行的 `tenant_agent_home_dir(tenant, id)` / `(tenant, id)` 等函数签名示意改为与 ledger F 一致的 `(tenant, name)` / `<name>`，并在函数名说明处点明"路径键 = agent name（不可变 handle）"，消除文档内自相矛盾。

## 8. 收尾门禁（全绿才算完）

- [ ] 8.1 全库 grep 防残留：`grep -rn "agent_id" src` 命中项**逐一确认**——凡"实装/应装 name"的位置均已改为 `agent_name`；平台关系层真 int id 的 `agent_id` 保留（不误改）。
- [ ] 8.2 `openspec validate agent-identity-honest-naming --strict`
- [ ] 8.3 `uv run mypy src`（strict；改名后类型一致）
- [ ] 8.4 `make test-pr` + `make test-integration-ci`，判据"对照 main 基线无新增失败"
- [ ] 8.5 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`（无新增跨包/反向依赖——本 change 仅内部改名，不应触动边界）
- [ ] 8.6 tasks.md 全 `[x]`；功能分支 `openspec archive agent-identity-honest-naming`（同步 `agent-definition` spec）；commit（含 Co-Authored-By 签名）+ 推分支；**不 merge main，等 Randy 定夺**。
