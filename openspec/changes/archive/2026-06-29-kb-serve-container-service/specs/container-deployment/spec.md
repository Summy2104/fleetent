## MODIFIED Requirements

### Requirement: 单镜像多角色构建
项目 SHALL 提供单个 Docker 镜像，通过 entrypoint 命令区分运行角色（`platform` / `node` / `kb-worker` / `kb-serve` / `agent`），不为每个角色维护独立 Dockerfile。镜像 SHALL 包含运行各类角色所需的全部依赖与源码。

#### Scenario: 同一镜像按角色启动不同服务
- **WHEN** 以 `platform serve` 命令运行该镜像
- **THEN** 容器启动 platform 控制面并监听 8765
- **WHEN** 以 `node start` 命令运行同一镜像
- **THEN** 容器启动 node supervisor
- **WHEN** 以 `kb serve --config <kb-service.yaml>` 命令运行同一镜像
- **THEN** 容器启动 KB 读 API 服务
- **WHEN** 以 `agent run <name>` 命令运行同一镜像
- **THEN** 容器以 agent 运行时启动（node 经此拉起 agent 兄弟容器）

#### Scenario: entrypoint 拒绝未知角色
- **WHEN** entrypoint 收到未识别的角色命令
- **THEN** 容器以非 0 exit code 退出
- **AND** 输出可识别的错误信息说明支持的角色

### Requirement: Compose 编排长驻服务全栈
项目 SHALL 提供 `docker-compose.yml`，编排 `platform`、`node`、`kb-worker`、`kb-serve` 四个长驻服务，使单条 compose 命令即可拉起完整 managed 栈。`platform` SHALL 暴露 8765，`node` SHALL 暴露 forwarder 端口 8786。`kb-serve` SHALL 接入同一 compose 网络供 agent 经服务名寻址读 KB，并与 `kb-worker` 共享同一 `FLEETENT_HOME` 卷（worker 写 `tenants/<tenant>/kb/`、kb-serve 读同一 kb/）。agent 容器不在 compose 静态声明，而由 node 运行时按 desired state 动态拉起。

#### Scenario: 一条命令拉起长驻栈
- **WHEN** operator 运行 compose up
- **THEN** `platform`、`node`、`kb-worker`、`kb-serve` 四个长驻服务全部启动
- **AND** platform 在 8765 可达、node forwarder 在 8786 可达

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

### Requirement: node 容器接入宿主 Docker socket
`node` 服务 SHALL 挂载宿主 Docker socket，用于拉起 agent 兄弟容器，并支撑 agent 的 sandbox 工具执行（Docker 后端）。platform / kb-worker / kb-serve SHALL NOT 挂载该 socket。

#### Scenario: node 经 socket 拉起 agent 与 sandbox 容器
- **WHEN** node 容器挂载了宿主 docker.sock
- **THEN** node 可拉起 agent 兄弟容器
- **AND** agent 的 Docker sandbox 后端探测为可用

#### Scenario: 非 node 服务不挂 socket
- **WHEN** 检视 platform / kb-worker / kb-serve 服务定义
- **THEN** 均不挂载宿主 Docker socket
