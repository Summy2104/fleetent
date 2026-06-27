## Purpose

定义 fleetent 的容器化 managed 栈部署能力：单镜像多角色、Compose 长驻服务、node 拉起 agent 兄弟容器、path-parity 挂载、docker.sock 边界与生产运维入口。

## Requirements

### Requirement: 单镜像多角色构建
项目 SHALL 提供单个 Docker 镜像，通过 entrypoint 命令区分运行角色（`platform` / `node` / `kb-worker` / `agent`），不为每个角色维护独立 Dockerfile。镜像 SHALL 包含运行各类角色所需的全部依赖与源码。

#### Scenario: 同一镜像按角色启动不同服务
- **WHEN** 以 `platform serve` 命令运行该镜像
- **THEN** 容器启动 platform 控制面并监听 8765
- **WHEN** 以 `node start` 命令运行同一镜像
- **THEN** 容器启动 node supervisor
- **WHEN** 以 `agent run <name>` 命令运行同一镜像
- **THEN** 容器以 agent 运行时启动（node 经此拉起 agent 兄弟容器）

#### Scenario: entrypoint 拒绝未知角色
- **WHEN** entrypoint 收到未识别的角色命令
- **THEN** 容器以非 0 exit code 退出
- **AND** 输出可识别的错误信息说明支持的角色

### Requirement: Compose 编排长驻服务全栈
项目 SHALL 提供 `docker-compose.yml`，编排 `platform`、`node`、`kb-worker` 三个长驻服务，使单条 compose 命令即可拉起完整 managed 栈。`platform` SHALL 暴露 8765，`node` SHALL 暴露 forwarder 端口 8786。agent 容器不在 compose 静态声明，而由 node 运行时按 desired state 动态拉起。

#### Scenario: 一条命令拉起长驻栈
- **WHEN** operator 运行 compose up
- **THEN** `platform`、`node`、`kb-worker` 三个长驻服务全部启动
- **AND** platform 在 8765 可达、node forwarder 在 8786 可达

#### Scenario: platform 与 node 经 compose 网络通信
- **WHEN** 三服务运行于同一 compose 网络
- **THEN** platform 经 compose 服务名寻址 node forwarder，符合既有 forwarder 寻址契约
- **AND** 编排不引入 node/agent 对 platform 的反向网络依赖（platform→node 单向）

### Requirement: agent 作为 node 拉起的兄弟容器
node 服务 SHALL 经 docker socket 将 agent 拉起为独立兄弟容器（`node.backend=container`，见 `node-process-backend`），而非 node 容器内子进程。agent 容器 SHALL 与 node 接入同一网络，使 forwarder 经容器网络寻址转发 `/chat` 与 `/ws`。

#### Scenario: node 拉起 agent 兄弟容器
- **WHEN** node reconcile 决定拉起某 agent
- **THEN** 该 agent 作为独立容器运行（非 node 子进程）
- **AND** forwarder 经容器网络名转发该 agent 的 `/chat` 与 `/ws`

#### Scenario: node 容器重启不连带杀 agent
- **WHEN** node 容器被重启（如重部署）
- **THEN** 仍在运行的 agent 容器不被连带终止
- **AND** 新 node 经 label 认领这些 agent 容器，不重复拉起

### Requirement: node 容器接入宿主 Docker socket
`node` 服务 SHALL 挂载宿主 Docker socket，用于拉起 agent 兄弟容器，并支撑 agent 的 sandbox 工具执行（Docker 后端）。platform / kb-worker SHALL NOT 挂载该 socket。

#### Scenario: node 经 socket 拉起 agent 与 sandbox 容器
- **WHEN** node 容器挂载了宿主 docker.sock
- **THEN** node 可拉起 agent 兄弟容器
- **AND** agent 的 Docker sandbox 后端探测为可用

### Requirement: path-parity 数据卷布局与按 agent 精确挂载
Compose SHALL 以宿主 bind mount 方式持久化 `FLEETENT_HOME`，且**容器内挂载路径与宿主路径一致**（path parity），使：(1) node 写入的 per-agent `.env`/home 被 agent 容器在同路径读到；(2) agent 的 sandbox workspace bind-mount 的 source 在宿主可解析。卷布局 SHALL 保持 `FLEETENT_HOME` 下既有目录结构（`tenants/<tenant>/agents/<agent_id>/`）。

agent 容器 SHALL **按 agent 精确挂载**，仅获得：其自身 `tenants/<t>/agents/<id>/` 子树（rw）+ 该租户共享 KB 库 `tenants/<t>/kb.db`·`kb_vectors.db`（ro）。agent 容器 SHALL NOT 挂载 `management.db` 或其它 agent 的子树（在文件系统层强制 agent 隔离与 platform 解耦契约）。

#### Scenario: node 写入的 home 被 agent 容器读到
- **WHEN** node 在 `FLEETENT_HOME/tenants/<t>/agents/<id>/` 写入 `.env` 并拉起该 agent 容器
- **THEN** agent 容器在相同路径读到该 home 与 `.env`

#### Scenario: agent 容器只见自己的子树与租户 KB
- **WHEN** agentA 容器启动
- **THEN** 它挂到自身 `tenants/<t>/agents/agentA/`（rw）与租户 `kb.db`/`kb_vectors.db`（ro）
- **AND** 它不挂载 `management.db`，也不挂载其它 agent 的子树

#### Scenario: sandbox workspace 在宿主可解析
- **WHEN** agent 容器经宿主 dockerd 拉起 sandbox 容器并 bind-mount workspace
- **THEN** workspace 的 host source 路径在宿主真实存在（因 path parity），sandbox 正常挂载

#### Scenario: 容器重建后数据保留
- **WHEN** operator 重建并重启容器（不删除 bind mount 目录）
- **THEN** 管理库与 agent 侧库的数据在重建后仍存在

### Requirement: 服务重启策略与优雅关停
Compose 中长驻服务 SHALL 配置 `restart: unless-stopped`；agent 容器 SHALL 配置 `STOPSIGNAL SIGUSR1`（或等效方式）以使停止时触发既有优雅 drain 链，并给足 stop grace period。

#### Scenario: 进程崩溃后自动重启
- **WHEN** 某长驻服务进程异常退出
- **THEN** Docker 依据 restart 策略自动重启该服务

#### Scenario: agent 容器停止走优雅 drain
- **WHEN** agent 容器被停止
- **THEN** 触发 SIGUSR1 起的 drain 链，in-flight run 排水后退出，超时再升级

### Requirement: Makefile 运维入口
Makefile SHALL 提供面向生产 Compose 的运维 target（如 `up` / `down` / `logs` / `deploy` / `redeploy` / `deploy-status` / `upgrade`），与现有 dev-only target（打 `.fleetent-dev`）区分。这些 target SHALL 封装 compose 调用，使 operator 无需记忆原始 compose 命令。

#### Scenario: Makefile 暴露 Compose 运维 target
- **WHEN** operator 运行 `make help`
- **THEN** 列出面向生产 Compose 的运维 target
- **AND** 这些 target 不复用 dev-only target 的 `.fleetent-dev` home
