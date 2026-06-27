## Why

node 当前只有一种进程后端 `LocalProcessBackend`：用 `subprocess.Popen` 在本机把 agent 拉成子进程。容器化部署（见 change [[dockerize-deploy-stack]]）若把 node 与 agent 塞进同一容器，会**退化现状**：裸机上 node 退出并不回收 agent（`node/app.py` 的 finally 不停 agent），新 node 经 `.fleetent.pid` + `os.kill` 认领仍在跑的 agent——即「node 重启 ≠ agent 重启」。同容器下容器重启会连同 PID namespace 杀光所有 agent，且 PID 认领失效。

本 change 给 node 新增一种**容器进程后端**：agent 跑成 node 经 docker.sock 拉起的**独立兄弟容器**，生命周期与 node 解耦、互相隔离，node 重启可经 label 认领存活 agent。这是既有 `node-process-backend`「可插拔进程后端接口」预留的扩展点，与 `LocalProcessBackend`（dev/裸机）并存、按配置选型。本 change **不含** Docker 镜像/Compose/部署机制——那些在 [[dockerize-deploy-stack]] 消费本 change 的产物。

## What Changes

- **新增 `ContainerBackend`**：实现既有 `BaseProcessBackend` 接口，以 `docker run` 拉起独立 agent 容器（`spawn`/`stop`/`is_alive`/`gateway_port`），打 agent name/tenant label，接入与 node 同一网络，挂 per-agent home。
- **生命周期解耦 + label 认领**：node 重启不杀 agent 容器；新 node 经容器 label/`docker inspect` 认领仍运行的 agent 容器，替代跨 PID namespace 失效的 PID 文件认领。
- **优雅停止**：`stop` 经 `docker exec <c> fleetent agent stop`（复用既有 SIGUSR1 drain 链），不在 node 侧重写信号序列；不强依赖容器 `STOPSIGNAL`。
- **后端按配置选型**：node 配置新增 `node.backend: process | container`（缺省 `process`），`app.py:main()` 经工厂注入对应后端；旧部署行为不变。
- **forwarder 寻址改造**：forwarder 当前写死 `http://127.0.0.1:{port}` / `ws://127.0.0.1:{port}`，改为经 backend 取 `agent_endpoint(name, tenant) -> (host, port)`；local 后端返回 loopback（行为不变），container 后端返回容器网络名+端口。

## Capabilities

### New Capabilities
<!-- 无新建 capability，全部落在既有 node-process-backend 上 -->

### Modified Capabilities
- `node-process-backend`: 在既有「可插拔进程后端接口 + local 进程后端」上，新增「容器进程后端（agent 作为独立容器，docker run/inspect/stop + label 认领 + 生命周期解耦）」「进程后端按配置选型」「agent 端点解析与后端解耦（供 forwarder）」三项要求。

## Impact

**受影响代码 / 文件**：
- `src/fleetent/node/`：新增 `ContainerBackend`（同 `backend.py` 接口）+ 后端选型工厂；`config` 增 `backend` 字段；`forwarder.py` 的 `forward_chat`/`forward_ws` 改用 `agent_endpoint`；`app.py:main()` 注入点；`backend.py` 接口增 `agent_endpoint`，`LocalProcessBackend` 实现 loopback 端点。
- 测试：`tests/unit/` 覆盖两后端选型、端点解析、forwarder 寻址、ContainerBackend（mock docker 调用，不起真容器）。

**模块边界影响声明**（AGENTS.md 要求）：
- **owning package**：`node`（ContainerBackend / 选型工厂 / forwarder 寻址 / `node.backend` config，均在 node 包内）。
- **public API surface**：node backend 接口新增 `agent_endpoint(name, tenant) -> (host, port)`；agent 对外 `/chat` `/ws` 契约不变。
- **owned tables**：无 schema 变更。
- **config namespace**：新增 `node.backend`（process|container）。
- **cross-module dependencies**：维持 platform→node→agent 单向；ContainerBackend 经 docker.sock 起 agent 容器 = 既有 sandbox 同款 docker-out-of-docker，不引入新反向依赖。
- **migration / shim plan**：无 schema 迁移；`LocalProcessBackend` 保留为缺省后端，`node.backend` 缺省 `process` 保旧部署零变化，无 shim。

**依赖**：`container` 后端运行期需宿主 docker.sock（与 sandbox 共用）；`process` 后端无 docker 依赖。本 change 不引入外部专有服务。容器镜像与 Compose 编排由下游 [[dockerize-deploy-stack]] 提供（A↔B 契约：单镜像 + entrypoint `agent run` 角色、compose 网络名、path-parity 挂载约定、label 规约）。
