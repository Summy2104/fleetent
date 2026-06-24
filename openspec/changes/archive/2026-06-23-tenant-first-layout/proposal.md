## Why

当前 agent home 与运行时数据仍分散在 `FLEETENT_HOME/agents/<name>/`、`FLEETENT_HOME/data/<tenant>/<agent>/` 与 `FLEETENT_HOME/data/management.db` 三套语义里；managed 模式下 platform 与 node 也都可能写 agent home。随着多租户、node 托管、skill drift/backflow 与 KB worker 接入，这个布局会造成双写、路径权威不清和多机下 platform 读取假 home 的问题。

本 change 在 `agent-memory-rescope` 已落地后，把剩余布局重构收敛为 tenant-first 目标态：租户的一切落在 `tenants/<tenant>/`，managed agent home 由 node 单一拥有，platform 只维护管理库、公共 skill 池和 desired-state。

## What Changes

- **BREAKING**: canonical 管理库路径从 `FLEETENT_HOME/data/management.db` 改为 `FLEETENT_HOME/management.db`；本 change 不提供旧布局自动迁移，内测/dev/pilot home 需重建或由后续 migration change 处理。
- **BREAKING**: canonical agent home 从 `FLEETENT_HOME/agents/<name>/` 改为 `FLEETENT_HOME/tenants/<tenant>/agents/<name>/`；`paths.agent_home_dir(name)` 仅作为 default-tenant 兼容 shim 保留。
- **BREAKING**: canonical agent-side DB 布局从 `<data_dir>/<tenant>/<agent>/...` 改为 agent home 内拍平的 `tenants/<tenant>/agents/<name>/data/...`；KB 保持 tenant-level，但落点改为 `tenants/<tenant>/kb.db` 与 `kb_vectors.db`。
- managed 模式下 platform 不再写真实 agent home；platform 只生成 desired-state payload，node reconcile 是 agent home 的唯一 writer。
- node reconcile 负责写 `agent.yaml`、`.env`、`skills/` 与本地 config hash/cache，并从 tenant-aware home 拉起 agent runtime。
- skill 公共池继续由 platform 管理；platform 通过 immutable bundle cache/API 暴露 skill bundle，node 根据 desired-state manifest 按版本下载并部署到 agent 本地副本。
- skill drift/backflow 改为基于 node 对真实 home 的观察：node 上报 skill 副本摘要，platform 存储治理态；backflow nomination 按需从 owning node 拉取真实 bundle。
- standalone `fleetent agent init/run` 默认使用 `tenants/default/agents/<name>/`；显式 `--home` 继续最高优先级。

## Capabilities

### New Capabilities
- `skill-bundle-distribution`: platform 从公共 skill 池生成按版本寻址的 immutable bundle，并通过 node 授权 API 供 node 下载部署。
- `node-skill-drift-observation`: node 扫描自己拥有的 agent home skill 副本，上报 drift/base/home hash 等观测状态，供 platform 治理与 backflow 使用。

### Modified Capabilities
- `runtime-paths`: 改为 tenant-first 路径解析，新增 tenant-aware home/data/KB/management path API，旧 default-tenant shim 仅兼容。
- `database-runtime`: 默认管理库路径从 `data/management.db` 改为根目录 `management.db`，旧路径自动迁移不在本 change 范围。
- `tenant-scoped-db-routing`: SQLite backend 映射到 `tenants/<tenant>/kb.db` 与 `tenants/<tenant>/agents/<agent>/data/*.db`，agent data 不再内嵌 `<tenant>/<agent>`。
- `platform-agent-lifecycle`: managed lifecycle 从“platform materialize 写 home”改为“platform 生成 desired-state payload；node 写 home”。
- `node-supervisor`: node reconcile 使用 tenant-aware home，完整部署 agent home（agent.yaml/.env/skills），并处理 skill bundle 下载、原子部署与 drift 保护。
- `node-desired-state-api`: desired-state 增加 skill manifest/bundle metadata 与 tenant-aware home 所需字段。
- `agent-runtime-cli`: agent run/init 默认解析 tenant-first home，仍支持显式 `--home`。
- `agent-skill-scoping`: agent 的 allowed/disabled skill 决策仍写入 agent.yaml，但 skill 文件部署职责从 platform materialize 移至 node。
- `platform-read-projection`: platform 对 agent-side DB 的只读投影改为读取 tenant-first 物理位置。

## Impact

- **owning package**: `paths`, `tenant_router`, `node`, `platform.agent_lifecycle`, `platform.skill_management`, `runtime.agent_app`, `agent_config` / `runtime.agent_init`。
- **public API surface**: tenant-aware path accessors；`SQLiteTenantBackend` 新布局映射；desired-state skill manifest schema；node skill bundle deployer；platform bundle download endpoint；node skill drift status payload；tenant-aware agent run/home resolution。
- **owned tables**: 管理库可能扩展 `agent_skills` 的 node observation 字段（如 `home_hash`、`changed_paths`、`last_seen_node_id`、`last_seen_at`）；agent-side DB schema 不变，仅物理位置改变。
- **config namespace**: 可新增 platform-side skill bundle cache 路径（默认 `FLEETENT_HOME/skill-bundles/`），不要求 node 配置 Git 凭据。
- **cross-module dependencies**: platform 可读公共 skill 池和管理库；node 只经 platform HTTP API 获取 desired-state/bundles，不直接访问 Git；agent runtime 仍不得 import `fleetent.platform.*`。
- **migration / shim plan**: 保留 default-tenant 兼容 shim 与必要的 legacy helper 名称，但 managed 路径不得再依赖旧 `agents/<name>` 或 `data/<tenant>/<agent>`；不实现旧布局数据自动迁移。
