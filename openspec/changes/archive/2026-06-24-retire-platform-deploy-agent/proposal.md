## Why

`agent_admin_api.py` 的 `POST /admin/agents/{name}/deploy`（`deploy_agent`）是 tenant-first 布局重构漏删的死代码：

- **路径已失效**：它用 `paths.agent_home_dir(name)` 写 `<home>/agents/<name>/agent.yaml`——这是**旧布局**路径；tenant-first 后 runtime 从 `tenants/<tenant>/agents/<name>/` 读，所以这个端点写出来的文件**根本不会被加载**，纯误导。
- **违反架构决策**：它是 platform **写 agent home** 的口子，违反 agent-home-layout 重构决策 A（平台不再写 home；managed 下 node reconcile 是唯一 home writer，standalone 下 CLI `agent init` 写）。
- **无背书、无消费者**：没有任何 spec 定义该端点（spec 孤儿）；前端无调用，仅 3 处测试在调（`tests/unit/test_coverage_admin_connector_handlers.py`、`tests/integration/test_agent_admin_api.py`）。

顺带：决策 A（"平台不写 agent home"）目前只在架构文档（`docs/architecture/agent-home-layout.md` ledger A）里，**spec 层没有断言**——所以才会有 `deploy_agent` 这种端点长出来没人拦。本 change 一并把它固化到 spec。

## What Changes

- **删除** `deploy_agent` 端点（`POST /admin/agents/{name}/deploy`）及其 3 处测试调用。**BREAKING**（移除一个 HTTP 端点，但无产品消费者）。
- **保留** `_build_agent_yaml` 与 `GET /admin/agents/{name}/agent-yaml`（`export_agent_yaml`）——后者只**回显** yaml、不写盘，不违反决策 A。
- **spec 固化**：在 `platform-control-plane` 新增一条 requirement，断言 platform MUST NOT 提供写 agent home（`agent.yaml`/`.env`/`skills/`）的 HTTP 或 CLI 端点；agent home 物化的唯一 owner 是 managed=node reconcile / standalone=CLI `agent init`。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `platform-control-plane`: 新增"platform 不写 agent home"的负向断言（把布局重构决策 A 固化到 spec 层，与既有"agent execution endpoints not on the platform"同精神）。

## Impact

- **owning package**: `platform/agent_management_console`（`agent_admin_api.py` 删 `deploy_agent`）。
- **public API surface**: 移除 `POST /admin/agents/{name}/deploy`；`GET /admin/agents/{name}/agent-yaml` 与 `_build_agent_yaml` 不变。
- **owned tables / config namespace**: 无。
- **cross-module dependencies**: 无新增；纯删除 + spec 断言。
- **migration / shim plan**: 无需迁移、不留 shim（端点无产品消费者）。
- **与 `rename-admin-cli-to-platform` 不重叠**：那个 change 明确排除 HTTP `/admin/*` 路径（只做 CLI 改名）；本 change 只动这一个 HTTP 端点，两者无冲突。
- 受影响代码：`src/fleetent/platform/agent_management_console/agent_admin_api.py`、`tests/unit/test_coverage_admin_connector_handlers.py`、`tests/integration/test_agent_admin_api.py`。
