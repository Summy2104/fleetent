## MODIFIED Requirements

### Requirement: Compose 编排长驻服务全栈
项目 SHALL 提供 `docker-compose.yml`，编排 `platform`、`node`、`kb-worker`、`kb-serve` 四个长驻服务，使单条 compose 命令即可拉起完整 managed 栈。`platform` SHALL 暴露 8765，`node` SHALL 暴露 forwarder 端口 8767。`kb-worker` 与 `kb-serve` SHALL 均以 `--config $FLEETENT_HOME/kb-service/<tenant>/kb-service.yaml` 运行、并以 `$FLEETENT_HOME/kb-service/<tenant>/.env` 为 `env_file`（KB 服务配置/secrets 收于该租户的 service home，与 platform `.env` 分开；compose 默认单租户 `default`）。`kb-serve` SHALL 接入同一 compose 网络供 agent 经服务名寻址读 KB，并与 `kb-worker` 共享同一 `FLEETENT_HOME` 卷（worker 写该租户 `kb-service/<tenant>/data/`、kb-serve 读同一 `data/`）。agent 容器不在 compose 静态声明，而由 node 运行时按 desired state 动态拉起。

#### Scenario: 一条命令拉起长驻栈
- **WHEN** operator 运行 compose up
- **THEN** `platform`、`node`、`kb-worker`、`kb-serve` 四个长驻服务全部启动
- **AND** platform 在 8765 可达、node forwarder 在 8767 可达

#### Scenario: kb-worker 与 kb-serve 经 kb-service 目录配置
- **WHEN** 检视 compose 的 kb-worker / kb-serve 服务定义
- **THEN** 二者 `--config` 指向 `$FLEETENT_HOME/kb-service/<tenant>/kb-service.yaml`、`env_file` 指向 `$FLEETENT_HOME/kb-service/<tenant>/.env`（默认租户 `default`）

#### Scenario: agent 经 compose 网络读 kb-serve
- **WHEN** node 拉起的 agent 兄弟容器配置为 `knowledge.provider=http`
- **THEN** agent 经 compose 网络以服务名寻址 `kb-serve` 完成 KB 检索
- **AND** 该依赖是 agent→KB 基础设施，不引入 agent→platform 反向依赖

#### Scenario: kb-serve 与 kb-worker 共享 kb 数据卷
- **WHEN** kb-worker 写入某租户 `kb-service/<tenant>/data/`
- **THEN** kb-serve 经同一 `FLEETENT_HOME` 卷读到该 `data/` 数据

#### Scenario: platform 与 node 经 compose 网络通信
- **WHEN** 四服务运行于同一 compose 网络
- **THEN** platform 经 compose 服务名寻址 node forwarder，符合既有 forwarder 寻址契约
- **AND** 编排不引入 node/agent 对 platform 的反向网络依赖（platform→node 单向）

## ADDED Requirements

### Requirement: 规范服务端口约定
各长驻服务 SHALL 各使用一个**固定的规范默认端口**，连续编号便于记忆；多实例 SHALL 靠 IP / 容器服务名区分，SHALL NOT 靠端口号段。所有端口仍 SHALL 可经 env / CLI 覆盖；本约定只规定默认值。

规范端口表：

| 角色 | 默认端口 | 实例多重性 |
| --- | --- | --- |
| platform | 8765 | 1/部署 |
| agent（`/chat`+`/ws` 服务口） | 8766 | dev/standalone 发布到宿主；node-managed 容器内绑同口、由 node forwarder 代理；node-managed 进程后端因共享宿主网络栈而动态分配（回退） |
| node forwarder | 8767 | 1/机器；多机同口、不同 host/IP |
| kb-serve | 8768 | 1/租户；容器同口、不同服务名；裸机多租户 8768,8769… 顺延（回退） |

#### Scenario: 多实例靠名字而非号段扩展
- **WHEN** 同一部署有多个 node、或多个租户的 kb-serve
- **THEN** 各实例使用同一规范默认端口，靠 host/IP 或容器服务名区分
- **AND** 不为"留扩展"分配额外端口号段；端口顺延仅作裸机/进程后端共享网络栈时的回退

#### Scenario: agent 内部口与 dev serve 口一致
- **WHEN** node 以容器后端拉起 agent
- **THEN** agent 在容器内绑定 8766（与 dev `agent run` 的 serve 口一致），由 node forwarder 代理 `/chat`+`/ws`
- **AND** 不再使用孤立的内部端口魔数

#### Scenario: 端口可覆盖
- **WHEN** operator 经 env / CLI 指定非默认端口
- **THEN** 服务以指定端口运行；规范默认仅在未指定时生效
