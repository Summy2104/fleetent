## MODIFIED Requirements

### Requirement: Compose 编排长驻服务全栈
项目 SHALL 提供 `docker-compose.yml`，编排 `platform`、`node`、`kb-worker`、`kb-serve` 四个长驻服务，使单条 compose 命令即可拉起完整 managed 栈。`platform` SHALL 暴露 8765，`node` SHALL 暴露 forwarder 端口 8786。`kb-worker` 与 `kb-serve` SHALL 均以 `--config $FLEETENT_HOME/kb-service/kb-service.yaml` 运行、并以 `$FLEETENT_HOME/kb-service/.env` 为 `env_file`（KB 服务配置/secrets 收于 `kb-service/` 目录，与 platform `.env` 分开）。`kb-serve` SHALL 接入同一 compose 网络供 agent 经服务名寻址读 KB，并与 `kb-worker` 共享同一 `FLEETENT_HOME` 卷（worker 写 `tenants/<tenant>/kb/`、kb-serve 读同一 kb/）。agent 容器不在 compose 静态声明，而由 node 运行时按 desired state 动态拉起。

#### Scenario: 一条命令拉起长驻栈
- **WHEN** operator 运行 compose up
- **THEN** `platform`、`node`、`kb-worker`、`kb-serve` 四个长驻服务全部启动
- **AND** platform 在 8765 可达、node forwarder 在 8786 可达

#### Scenario: kb-worker 与 kb-serve 经 kb-service 目录配置
- **WHEN** 检视 compose 的 kb-worker / kb-serve 服务定义
- **THEN** 二者 `--config` 指向 `$FLEETENT_HOME/kb-service/kb-service.yaml`、`env_file` 指向 `$FLEETENT_HOME/kb-service/.env`

#### Scenario: agent 经 compose 网络读 kb-serve
- **WHEN** node 拉起的 agent 兄弟容器配置为 `knowledge.provider=http`
- **THEN** agent 经 compose 网络以服务名寻址 `kb-serve` 完成 KB 检索
- **AND** 该依赖是 agent→KB 基础设施，不引入 agent→platform 反向依赖

#### Scenario: kb-serve 与 kb-worker 共享 kb 数据卷
- **WHEN** kb-worker 写入某租户 `tenants/<tenant>/kb/`
- **THEN** kb-serve 经同一 `FLEETENT_HOME` 卷读到该 kb/ 数据

#### Scenario: platform 与 node 经 compose 网络通信
- **WHEN** 四服务运行于同一 compose 网络
- **THEN** platform 经 compose 服务名寻址 node forwarder，符合既有 forwarder 寻址契约
- **AND** 编排不引入 node/agent 对 platform 的反向网络依赖（platform→node 单向）
