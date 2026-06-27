## Why

当前生产部署是「`git pull` + 手动 `uv tool install --force` 重建 + 手动重启进程」的裸机流程，无自动化或校验。prod-1 因此踩坑：代码 `git pull` 到了最新 `5dc87584`，但部署副本仍是 09:36 从旧 commit 构建的 uv tool，落后两个 commit（含 memory migration 修复 PR #314），运行时报 `agent_memory vector backend not initialized`。根因有三：(1) `git pull` ≠ 重部署，二者解耦但无人串联；(2) 无「重建+重启」一键入口；(3) 运行中进程不暴露所基于的 commit，操作者无从发现部署已陈旧。

同时现有 `Dockerfile` / `docker-compose.yml` 只跑 `platform serve` 单服务，缺 node / kb-worker，**跑不起完整 managed 栈**，导致生产只能走裸机。

本 change 提供 Docker Compose 全栈部署 + 重部署/陈旧检测自动化，消费上游 change [[node-container-backend]] 的容器后端（agent 跑成 node 拉起的兄弟容器）。

> **依赖**：本 change 的 compose 设 `node.backend=container`，需 [[node-container-backend]] 先落地。除「`make up` 端到端冒烟」外，本 change 其余产物（镜像、entrypoint、version、redeploy、docs）均可独立开发与测试；端到端冒烟 gate 在上游合并后补跑。

## What Changes

- **单镜像多角色**：entrypoint 按 `platform serve` / `node start` / `kb-worker` / `agent run` 区分角色，单镜像复用。
- **Docker Compose 全栈**：编排长驻服务 `platform`(8765) / `node`(8786) / `kb-worker`；node 经 docker.sock 动态拉起 agent 兄弟容器（后端能力来自 [[node-container-backend]]）。
- **node 容器接入宿主 docker.sock**：供拉起 agent 容器 + agent sandbox 工具执行；platform / kb-worker 不挂。
- **path-parity 数据卷 + 按 agent 精确挂**：`FLEETENT_HOME` 宿主 bind mount 且容器内外同路径；agent 容器仅挂自身 `tenants/<t>/agents/<id>/`（rw）+ 租户 `kb.db`/`kb_vectors.db`（ro），不挂 management.db / 他 agent。一并使 sandbox workspace bind source 宿主可解析。
- **部署版本可见 + 陈旧检测 + 一键重部署**：运行中服务暴露 build commit（build ARG 注入 + OCI label）；`make deploy-status` 对照源码 HEAD；`make redeploy` 重建+滚动重启，构建失败不重启在运行服务。
- **Makefile 运维 target**：`up`/`down`/`logs`/`deploy`/`redeploy`/`deploy-status`/`upgrade`，区别于 dev-only target。
- **升级流程对齐**：仅 platform 服务跑 alembic + 全库备份（复用 `fleetent platform upgrade`）。
- **统一 platform 默认端口为 8765**：`platform_cli/serve.py` 现默认 `8770` 与 TUI 默认（`ws://127.0.0.1:8765/ws`）/ docs 的 `8765` 不一致——不带 `--port` 启动即与客户端默认连不上。本 change 统一为 `8765`（serve.py 默认 + 全链路对齐）。
- **文档**：`docs/deployment/` 增补 Compose 部署、兄弟容器拓扑、重部署、陈旧检测、升级、回滚 runbook。

裸机 `scripts/install-*.sh` 与 `node.backend=process` 路径保留不动（无 **BREAKING**）；Docker Compose 为推荐生产路径。

## Capabilities

### New Capabilities
- `container-deployment`: Docker 单镜像多角色构建 + Compose 全栈（platform/node/kb-worker）编排、agent 兄弟容器拓扑接线、docker.sock 接入、path-parity + 按 agent 精确挂的数据卷布局、重启与优雅关停策略，以及 Makefile 运维 target。

### Modified Capabilities
- `deployment`: 在既有 upgrade/backup 能力上，新增「运行中部署的 build commit 可见」「部署版本 vs 源码 HEAD 陈旧检测」「一键重部署（重建+重启）入口」「platform serve 默认端口与客户端默认一致（8765）」四项要求。

## Impact

**受影响代码 / 文件**：
- 仓库根：`Dockerfile`（多角色 + build commit + venv PATH）、`docker-compose.yml`（多服务 + docker.sock + path-parity 卷 + 按 agent 挂）、`Makefile`（运维 target）。
- `scripts/docker_entrypoint.sh`（按角色分派）；轻量 CLI `fleetent version`（`__main__.py`，只读 env）。
- `src/fleetent/platform/platform_cli/serve.py`：默认端口 `8770 → 8765`（+ 全链路核对 docs/TUI 已是 8765）。
- `docs/deployment/`：runbook。

**模块边界影响声明**（AGENTS.md 要求）：
- **owning package**：无新增业务包；改动在仓库根 infra + `scripts/` + `docs/`；`fleetent version` 落 `__main__.py`；端口默认值改 `platform_cli`（platform 包内）。
- **public API surface**：新增只读 `fleetent version`；platform serve 默认端口变更（对外行为：不带 `--port` 时绑 8765）。不改业务 API。
- **owned tables**：无 schema 变更。
- **config namespace**：新增运行期 env `FLEETENT_BUILD_COMMIT`（构建注入）；compose 设 `node.backend=container`（键由 [[node-container-backend]] 定义）；复用 `FLEETENT_HOME`/`DATABASE_URL`/`FLEETENT_AUTO_UPGRADE`。
- **cross-module dependencies**：维持 platform→node→agent 单向；compose 网络寻址符合既有 forwarder 契约。
- **migration / shim plan**：无 schema 迁移；裸机 install 脚本与 `node.backend=process` 保留为并行路径，无 shim。

**A↔B 契约**（与 [[node-container-backend]] 对齐）：单镜像 + entrypoint `agent run` 角色（B 提供，A 调用）、compose 网络名（B 定，A 接入）、path-parity 挂载约定（共用）、`node.backend=container`（A 定义键，B 设值）、label 规约（A 定义，运维/B inspect）。agent 内部端口为 A 内部事、不发布、B 不引用。

**依赖**：构建期需 Docker（compose）；node 容器运行期需宿主 docker.sock。不引入任何云托管/外部专有服务（当前栈零 qdrant/redis/rabbitmq/postgres 依赖，全 SQLite + 嵌入式向量库）。
