## Context

生产部署当前是裸机 uv tool 流程，三处缺口导致 prod-1 部署陈旧两个 commit 而无人察觉（详见 proposal）。现有 `Dockerfile` / `docker-compose.yml` 只跑 `platform serve`，无法拉起完整 managed 栈。

本 change 是部署/编排层，消费 [[node-container-backend]] 提供的容器后端（agent = node 经 docker.sock 拉起的兄弟容器）。约束：
- **架构契约**：platform → node → agent 单向不可逆。
- **数据主权**：组件可自托管；当前栈零外部 infra，全 SQLite + 嵌入式向量库。
- **sandbox / docker.sock**：agent 工具执行的 Docker 后端经 `--mount type=bind,source=<FLEETENT_HOME 下路径>` 挂 workspace，source 由**宿主 dockerd** 解释，必须宿主可解析。
- **权威落盘布局**（`tenant_router.py`）：`tenants/<t>/kb.db`·`kb_vectors.db`（租户级 KB）；`tenants/<t>/agents/<id>/data/`（per-agent，`agent_app._redirect_agent_data_paths` 使 agent 全部 sink 自包含于此）。
- **端口现状**：`platform_cli/serve.py` 默认 `_DEFAULT_PORT=8770`，而 TUI 默认连 `ws://127.0.0.1:8765/ws`、docs 写 8765 —— 不带 `--port` 启动即与客户端默认错配。

## Goals / Non-Goals

**Goals:**
- 单镜像多角色 + Compose 三服务，一条命令拉起完整 managed 栈（agent 由 node 按 [[node-container-backend]] 拉起）。
- build commit 可见 + 陈旧检测 + 一键重部署，闭合 prod-1 根因。
- path-parity + 按 agent 精确挂，使 node 写/agent 读/sandbox 挂路径对齐且 agent 隔离。
- 统一 platform 默认端口为 8765。
- 裸机 install + `node.backend=process` 路径保留可用（无 BREAKING）。

**Non-Goals:**
- ContainerBackend / forwarder 寻址 / 后端选型（→ [[node-container-backend]]）。
- 多 node 跨主机扩展、替换 SQLite、rootless Docker / K8s。

## Decisions

### D1：单镜像，角色由 entrypoint 命令分派
`docker_entrypoint.sh` 按首参分派 `platform` / `node` / `kb-worker` / `agent`（缺省 `platform` 向后兼容），未知角色非 0 退出。agent 容器也用同镜像（命令 `agent run`），由 node 的 ContainerBackend 拉起。
- **备选**：每角色独立 Dockerfile —— 否决（多份构建、依赖漂移）。

### D2：path-parity 数据卷 + 按 agent 精确挂载
`FLEETENT_HOME` 用**宿主 bind mount 且容器内外同路径**（如宿主 `/srv/fleetent` → 各容器同 `/srv/fleetent`），且**按角色精确挂子树**：

| 容器 | 挂载 | 模式 |
|------|------|------|
| platform | `/srv/fleetent`（整棵） | rw |
| node | `/srv/fleetent`（整棵）+ `/var/run/docker.sock` | rw |
| kb-worker | `/srv/fleetent`（或 KB+队列子集） | rw |
| agent `<id>` | `tenants/<t>/agents/<id>/`（自己） | rw |
| agent `<id>` | `tenants/<t>/kb.db` + `kb_vectors.db`（含 `-wal`/`-shm`） | ro |
| sandbox | `…/agents/<id>/data/workspaces/<scope>` → `/workspace` | rw |

- **理由**：path parity 让 node 写/agent 读/sandbox 挂路径全对齐且宿主可解析；按 agent 精确挂使 agent 容器**看不到 management.db、看不到别的 agent**，FS 层强制隔离与解耦契约。agent 经 `tenant_scope` 直接读盘租户 KB，故须额外挂租户 KB（ro）。
- **备选**：纯 named volume（sandbox bind source 宿主不可解析）/ 整棵 home 挂进每个 agent（over-share）—— 均否决。
- **取舍**：放弃 named volume 可移植性换路径可解析 + 隔离；`down` 不带 `-v`，宿主目录天然留存。

### D3：build commit 经 build ARG 注入，多处可见
Dockerfile `ARG GIT_COMMIT`（后置避免打穿依赖层缓存）→ `ENV FLEETENT_BUILD_COMMIT` + OCI label `org.opencontainers.image.revision`；Makefile/compose 传 `--build-arg GIT_COMMIT=$(git rev-parse --short HEAD)`；服务启动记日志；`fleetent version` 读 env（无值输出 `unknown`）；`make deploy-status` 经 OCI label/`docker inspect` 对照源码 HEAD。

### D4：一键重部署 + 迁移只由 platform 跑
`make redeploy` = `docker compose build --build-arg GIT_COMMIT=...` → 成功后 `docker compose up -d`（build 失败则不 up，旧容器续跑，满足 spec）。裸机环境降级为 `uv tool install --force` + 重启提示。
`FLEETENT_AUTO_UPGRADE` 仅设 platform 服务；node/kb-worker/agent 不跑管理库 alembic（agent 侧 embedded 迁移 migrate-on-open 自动）。`make upgrade` = `docker compose run --rm platform fleetent platform upgrade`。
- **理由**：避免多服务并发抢跑管理库迁移；尊重双权威。

### D5：venv bin 入 PATH
镜像 `ENV PATH=/app/.venv/bin:$PATH`，保证 entrypoint 与诊断都能解析裸 `fleetent`。

### D6：统一 platform 默认端口为 8765
`platform_cli/serve.py` 默认 `_DEFAULT_PORT` 由 `8770` 改 `8765`，与 TUI 默认 / docs / compose 发布端口一致；核对全链路无其它 8770 残留。
- **理由**：消除「不带 `--port` 启动即与客户端默认连不上」的 foot-gun。既然本 change 动部署默认值，顺手统一。

## Risks / Trade-offs

- **docker.sock 暴露 = 容器逃逸面** → on-prem 信任边界内可接受；文档标注；rootless docker 列 non-goal。
- **path-parity 牺牲卷可移植性** → 单主机 on-prem 可接受；多主机列 non-goal。
- **SQLite 多容器共享卷并发** → 即裸机单主机现状，WAL + `session-cross-process-safety` 已覆盖。
- **GIT_COMMIT ARG 打穿构建缓存** → ARG 后置，依赖层（`uv sync`）不受 commit 影响。
- **端到端冒烟依赖上游** → `make up` 真拉 agent 容器需 [[node-container-backend]] 合并；其余产物独立可测。
- **改默认端口影响既有脚本** → 核对：prod-1 等均显式 `--port 8765`，改默认与之一致、不破坏显式调用。

## Migration Plan

1. 待 [[node-container-backend]] 合并；本 change 镜像/compose/Makefile/version/redeploy/docs/端口统一可并行开发，仅 `make up` 端到端冒烟待上游就绪。
2. 构建当前 commit 镜像，本机 `make up`（`node.backend=container`）验证：三服务起、node 拉起 agent 兄弟容器、forwarder 经容器名转发、`docker stop node` 后 agent 容器续活、新 node 认领、sandbox 在 path-parity 下挂载成功。
3. prod-1 灰度：compose 栈与裸机并存验证后切流；保留裸机直至验收通过。
4. **回滚**：`make down`（不带 `-v`）+ 重启裸机服务；或 compose 指定上一个 commit 重建镜像回退。

## 模块边界影响（AGENTS.md 要求）

- **owning package**：无新增业务包；infra 在仓库根 + `scripts/` + `docs/`；`fleetent version` 落 `__main__.py`；端口默认值改 `platform_cli`。
- **public API surface**：新增只读 `fleetent version`；platform serve 默认端口 8765。agent `/chat` `/ws` 不变。
- **owned tables**：无 schema 变更。
- **config namespace**：新增 env `FLEETENT_BUILD_COMMIT`；compose 设 `node.backend=container`（键属 [[node-container-backend]]）。
- **cross-module dependencies**：维持 platform→node→agent 单向；compose 网络寻址符合既有 forwarder 契约。
- **migration / shim plan**：无 schema 迁移；裸机脚本 + `node.backend=process` 保留，无 shim。

## Open Questions

- `fleetent version` 形态（独立子命令 vs 健康端点字段）——倾向独立子命令 + 启动日志。
- 租户 KB ro 挂载机制——直接挂 `kb.db`/`kb_vectors.db`（含 sidecar，文件级较脆）vs 将 KB 收进 `tenants/<t>/kb/` 子目录整目录 ro 挂载（更稳但需小改 `tenant_router` 落盘路径）。倾向后者若改动可控；apply 阶段定。
