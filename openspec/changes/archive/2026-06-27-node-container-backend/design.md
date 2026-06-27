## Context

node 用 `subprocess.Popen` 拉 agent（`LocalProcessBackend`）。生命周期现状（关键）：
- `node/app.py` main 的 `finally` 只关 im_edge_host + forwarder，**不停 agent**。
- `backend.py:is_alive` 先看内存 Popen 句柄，再回落读 `home/.fleetent.pid` + `os.kill(pid,0)`。
- reconcile：`if pid is None: spawn()`——新 node 经 PID 文件认领仍在跑的 agent，**不重启它**。

即裸机刻意解耦：`node 重启 → agent 孤儿存活 → 新 node 认领`。容器化若 node+agent 同容器，容器重启会杀光 PID namespace 并使 PID 认领失效。故引入容器后端，让 agent 跑成兄弟容器。

既有扩展点：`node-process-backend` spec 已定义可插拔进程后端接口（reconcile 走接口，`LocalProcessBackend` 是其一）；新增容器后端是自然扩展。`agent run` 优雅 drain 链是 SIGUSR1 → SIGTERM → SIGKILL（`agent_app._stop_running`）。

## Goals / Non-Goals

**Goals:**
- agent 跑成独立兄弟容器，生命周期与 node 解耦、互相隔离，node 重启可认领存活 agent。
- 后端按配置选型，缺省 `process`，旧部署零行为变化。
- forwarder 用端点抽象隔离两后端差异，进程路径零回归。

**Non-Goals:**
- Docker 镜像 / Compose / Makefile / 部署机制（→ [[dockerize-deploy-stack]]）。
- 多 node 跨主机调度。
- 改 agent 对外 HTTP 契约（`/chat` `/ws` 不变）。

## Decisions

### D1：ContainerBackend 实现既有 BaseProcessBackend 接口
- `spawn` = `docker run -d` 起 agent 容器（同镜像、命令 `agent run <name> --no-im --port <内部固定端口>`，打 label `fleetent.agent.name=<name>`/`fleetent.agent.tenant=<t>`/`fleetent.role=agent`，接入 node 同一网络，挂 per-agent home 卷）。
- `is_alive` / 认领 = 经 `docker inspect`/label 查容器运行态（替代跨 namespace 失效的 PID 文件）；新 node 启动按 label 列出存活 agent 容器即完成认领，不重 spawn。
- `stop` = `docker exec <c> fleetent agent stop`（复用既有 SIGUSR1 drain 链），失败回落 `docker stop`；**不依赖容器 STOPSIGNAL**（让 stop 完全自洽于本 change，减少 A↔B 耦合）。
- **备选**：node+agent 同容器 —— 否决（退化生命周期解耦、PID 认领失效）。

### D2：agent 内部端口是后端内部事
agent 容器各自独立 netns，可用同一固定内部端口（值由 ContainerBackend 持有，避开已发布的 8765/8786；**不发布到宿主**）。forwarder 经容器名寻址，故该端口不进 A↔B 契约、不被 compose 引用。
- **理由**：消除 loopback 动态分配的 TOCTOU 竞态；端口纯内部，B 无需感知。

### D3：后端按配置选型（工厂）
node config 新增 `node.backend: process | container`（缺省 `process`）。`app.py:main()` 经工厂按配置注入。
- **理由**：dev/裸机零依赖直跑、生产走容器；缺省 process 保旧部署零变化（亦满足 AGENTS.md「无 platform、无 DB 表」验证基线仍走 process 路径）。

### D4：forwarder 寻址改造（loopback → 端点解析）
forwarder 现写死 `http://127.0.0.1:{port}` / `ws://127.0.0.1:{port}`。改为经 backend 取 `agent_endpoint(name, tenant) -> (host, port)`：local 返 `("127.0.0.1", loopback)`（行为不变），container 返 `("<agent 容器名>", 内部端口)`。
- **理由**：唯一跨切面改动；端点抽象隔离两后端，进程路径零回归。

## Risks / Trade-offs

- **docker.sock 暴露** → 仅 `container` 后端需要；信任边界与 rootless 由下游部署 change 处理。
- **agent 容器认领竞态**（新 node 启动 vs 旧 agent 退出中）→ label + `docker inspect` 状态判定，reconcile 幂等（已存活不重 spawn）。
- **容器后端逻辑测试** → mock docker 调用做 unit 测，不起真容器；真容器端到端在 [[dockerize-deploy-stack]] 的 `make up` 冒烟覆盖。
- **两后端分叉** → 容器独有行为（label 认领、stop via exec）留在 ContainerBackend，不漏进共享 reconcile；forwarder 经统一 `agent_endpoint` 收口。

## Migration Plan

1. 落 ContainerBackend + `agent_endpoint` + 选型工厂 + forwarder 改造，全程 unit 测（mock docker），`node.backend=process` 下全回归绿。
2. 容器后端的真实端到端验证延到 [[dockerize-deploy-stack]]（需镜像+compose 网络）。
3. 合并风险低：缺省 `process` 不激活容器路径。

## 模块边界影响（AGENTS.md 要求）

- **owning package**：`node`（ContainerBackend / 选型工厂 / forwarder 端点解析 / `node.backend` config）。
- **public API surface**：backend 接口新增 `agent_endpoint(name, tenant) -> (host, port)`；agent `/chat` `/ws` 不变。
- **owned tables**：无。
- **config namespace**：新增 `node.backend`。
- **cross-module dependencies**：维持 platform→node→agent 单向；docker-out-of-docker 与 sandbox 同款，无新反向依赖。
- **migration / shim plan**：无 schema 迁移；`LocalProcessBackend` 保留为缺省，无 shim。

## Open Questions

- agent 容器命名/label 最终规约（`fleetent-agent-<tenant>-<name>` + 上述 label）——apply 阶段定稿；需与 [[dockerize-deploy-stack]] 对齐为 A↔B 契约。
- 孤儿 agent 容器 GC（是否复用 sandbox orphan-cleanup 思路）——apply 阶段定。
