# retire-node-kb-coupling — Tasks

> 全减法 change。TDD 以"守卫测试"表达：先写新行为守卫（见红——旧代码仍注入/挂载），删代码见绿（最窄命令 `uv run pytest <file>::<test> -x -q`）。测试任务在实现任务之前。

## 1. 退役 reconcile 的 provider fallback 注入

- [ ] 1.1 测试：改写 `tests/unit/node/test_reconcile.py::test_reconcile_injects_managed_kb_http_provider_from_host_service_config` 为守卫 `test_write_home_does_not_inject_knowledge_provider`——同机存在 kb-service.yaml、配置含绑定且 provider 非 http 时，`_write_home` 落盘的 agent.yaml knowledge 段与输入逐字一致、`.env` 无 knowledge secret（先红：旧代码会注入）
- [ ] 1.2 实现：删 `reconcile.py` 的 `_inject_managed_knowledge_provider` / `_managed_kb_auth_ref` / `_managed_kb_url`、`_write_home` 调用点、`load_host_service_config` import（及随之未用的 import）；见绿

## 2. 退役容器后端的 KB 挂载与垫底

- [ ] 2.1 测试：改写 `tests/unit/node/test_backend.py` ——`test_container_backend_spawn_runs_agent_container_with_labels_network_and_mounts` 断言 docker run 参数**只含 home 卷挂载、不含租户 KB 目录挂载**；删除 `test_container_backend_spawn_migrates_tenant_kb_before_readonly_mount`，新增守卫 `test_container_backend_spawn_does_not_touch_tenant_kb`（spawn 后 `tenants/<t>/kb/` 不被创建/写入）（先红）
- [ ] 2.2 实现：删 `backend.py` ContainerBackend 的 KB 目录 mount、`_prepare_tenant_kb` 及 `KB_MIGRATIONS` / `create_substrate` / `migrate` / `ensure_tenant_kb_dir` 等随之未用的 import；见绿
- [ ] 2.3 验证：node 包对 `knowledge_base` 的 import 清零——`grep -rn "knowledge_base" src/fleetent/node/` 为空（写进 task 验收，不加护栏测试）

## 3. 层收尾

- [ ] 3.1 跑受影响层：`uv run pytest tests/unit/node -q` 与 `uv run pytest tests/integration -q -k "node or reconcile"` 无新增失败（存量 e2e/integration 若有断言 fallback 注入的用例随改）
- [ ] 3.2 docs：`docs/capabilities/knowledge-base.md` 部署前提段明确"managed 的 KB 接线唯一来自 platform 物化（kb_serve 必配），node 不再兜底注入、agent 容器无 KB 挂载"；人工确认后提交
- [ ] 3.3 change/PR 收尾：`make test-pr` + `make test-integration-ci` 全绿（对照 main 基线无新增失败）
