## MODIFIED Requirements

### Requirement: Compose 编排长驻服务全栈
项目 SHALL 提供 `docker-compose.yml`，编排 `platform`、`node`、`kb-worker`、`kb-serve` 四个长驻服务，使单条 compose 命令即可拉起完整 managed 栈。`platform` SHALL 暴露 8765，`node` SHALL 暴露 forwarder 端口 8767。`kb-worker` 与 `kb-serve` SHALL 均以**本机服务级配置** `--config $FLEETENT_HOME/kb-service.yaml` 运行（单机多租户，服务本机所有在册租户，按 `principal.tenant_id` / job.tenant_id 路由），SHALL NOT 使用 per-tenant `env_file`——各租户 connector secret 由 worker 经 `tenants/<tenant>/kb/.env` **按需加载**（整个 `FLEETENT_HOME` 作卷挂载，无需 boot 预载）。`kb-serve` SHALL 接入同一 compose 网络供 agent 经服务名寻址读 KB，并与 `kb-worker` 共享同一 `FLEETENT_HOME` 卷（worker 写各租户 `tenants/<tenant>/kb/data/`、kb-serve 读同一 `data/`）。agent 容器不在 compose 静态声明，而由 node 运行时按 desired state 动态拉起。

#### Scenario: 一条命令拉起长驻栈
- **WHEN** operator 运行 compose up
- **THEN** `platform`、`node`、`kb-worker`、`kb-serve` 四个长驻服务全部启动
- **AND** platform 在 8765 可达、node forwarder 在 8767 可达

#### Scenario: kb-worker 与 kb-serve 用本机 config、无 per-tenant env_file
- **WHEN** 检视 compose 的 kb-worker / kb-serve 服务定义
- **THEN** 二者 `--config` 指向本机 `$FLEETENT_HOME/kb-service.yaml`（多租户）
- **AND** 二者 SHALL NOT 声明指向 `tenants/<tenant>/kb/.env` 的 per-tenant `env_file`；各租户 secret 由 worker 按需从 `tenants/<tenant>/kb/.env` 加载
- **AND** compose 在无 `default` 租户目录时仍能起栈（不因缺 per-tenant `.env` 文件失败）

#### Scenario: agent 经 compose 网络读 kb-serve
- **WHEN** node 拉起的 agent 兄弟容器配置为 `knowledge.provider=http`
- **THEN** agent 经 compose 网络以服务名寻址 `kb-serve` 完成 KB 检索
- **AND** 该依赖是 agent→KB 基础设施，不引入 agent→platform 反向依赖

#### Scenario: kb-serve 与 kb-worker 共享 kb 数据卷
- **WHEN** kb-worker 写入某租户 `tenants/<tenant>/kb/data/`
- **THEN** kb-serve 经同一 `FLEETENT_HOME` 卷读到该 `data/` 数据
