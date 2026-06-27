> 依赖 [[node-container-backend]]：除 §6 端到端冒烟外均可独立开发/测试；冒烟待上游合并后补跑。

## 1. 统一 platform 默认端口为 8765

- [x] 1.1 写测试：`platform serve` 不带 `--port` 绑 8765；显式 `--port` 优先（unit）
- [x] 1.2 改 `platform_cli/serve.py` 默认 `_DEFAULT_PORT` `8770 → 8765`；grep 全仓核对无其它 8770 残留（docs/TUI 已 8765）
- [x] 1.3 跑 unit 见绿

## 2. build commit 可见（version 暴露）

- [x] 2.1 写测试：`fleetent version` 在 `FLEETENT_BUILD_COMMIT` 已设时输出短 SHA、未设输出 `unknown`（unit）
- [x] 2.2 写测试：服务启动把 build commit 记入结构化日志（unit）
- [x] 2.3 实现 `fleetent version` 子命令（`__main__.py`，只读 env）+ 启动日志记录
- [x] 2.4 跑 unit 见绿

## 3. 陈旧检测 + 一键重部署逻辑

- [x] 3.1 写测试：陈旧检测纯函数——deployed_commit 落后 head 报陈旧并输出两 commit；一致报最新（unit）
- [x] 3.2 写测试：重部署「构建失败不重启在运行服务」编排判据（unit，mock 构建 fail → 不触发重启）
- [x] 3.3 实现陈旧检测逻辑 + 重部署编排辅助
- [x] 3.4 跑 unit 见绿

## 4. Dockerfile 多角色镜像 + entrypoint 分派

- [x] 4.1 改 `Dockerfile`：`ARG GIT_COMMIT`（后置）→ `ENV FLEETENT_BUILD_COMMIT` + OCI label `org.opencontainers.image.revision`；venv bin 入 `PATH`
- [x] 4.2 写测试：`docker_entrypoint.sh` 按首参分派 platform/node/kb-worker/agent；缺省 platform；未知角色非 0 退出（shell/integration）
- [x] 4.3 改 `scripts/docker_entrypoint.sh`：角色分派 + 仅 platform 触发 `FLEETENT_AUTO_UPGRADE`
- [x] 4.4 `docker build --build-arg GIT_COMMIT=$(git rev-parse --short HEAD)` 成功；`docker run ... fleetent version` 回显该 commit；entrypoint 测试见绿

## 5. docker-compose 全栈 + 卷布局

- [x] 5.1 改 `docker-compose.yml`：`platform`(8765)/`node`(8786)/`kb-worker` 三长驻服务，单镜像 build、角色命令区分；三服务 `restart: unless-stopped`
- [x] 5.2 node 服务挂宿主 `/var/run/docker.sock` + 设 `node.backend=container`；platform/kb-worker 不挂 socket
- [x] 5.3 path-parity：`FLEETENT_HOME` 宿主 bind mount + 容器内同路径
- [x] 5.4 agent 容器按 agent 精确挂（自身 `tenants/<t>/agents/<id>/` rw + 租户 `kb.db`/`kb_vectors.db` ro，不挂 management.db/他 agent）；定夺租户 KB ro 挂载机制（文件级 vs KB 子目录，与 [[node-container-backend]] 的 ContainerBackend 挂载逻辑对齐）
- [x] 5.5 仅 platform 设 `FLEETENT_AUTO_UPGRADE`；compose 网络内 platform 经服务名寻址 node forwarder，node 拉起的 agent 容器接入同网络

## 6. 端到端冒烟（gate 在 [[node-container-backend]] 合并后）

- [x] 6.1 `make up` 起栈：platform 8765 / node 8786 可达；node 拉起 agent 兄弟容器；forwarder 经容器名转发 `/chat`+`/ws` 通
- [x] 6.2 `docker stop node` 后 agent 容器续活、新 node 经 label 认领；sandbox 在 path-parity 下挂载成功
- [x] 6.3 验证基线：「无 platform、platform DB 表不存在」环境 `fleetent agent run` 对话仍可完成（解耦契约未被破坏）

## 7. Makefile 运维 target

- [x] 7.1 新增 `up`/`down`（不带 `-v`）/`logs`/`deploy`/`redeploy`/`deploy-status`/`upgrade`，封装 compose
- [x] 7.2 `redeploy` = build（传 GIT_COMMIT）成功后 `up -d`；裸机环境降级为 `uv tool install --force` + 重启提示
- [x] 7.3 `deploy-status` 对照镜像/容器 build commit 与 `git rev-parse --short HEAD`，陈旧时明确提示
- [x] 7.4 `upgrade` = `docker compose run --rm platform fleetent platform upgrade`
- [x] 7.5 `make help` 列出生产运维 target，不复用 dev-only `.fleetent-dev` home

## 8. 文档与收尾

- [x] 8.1 `docs/deployment/` 增补 Compose 部署 / 兄弟容器拓扑 / 重部署 / 陈旧检测 / 升级 / 回滚 runbook；标注 docker.sock 信任边界 + rootless（non-goal）
- [x] 8.2 README 部署章节指向 Compose 为推荐路径，裸机 install + `node.backend=process` 保留说明
- [x] 8.3 `make test-pr` + `make test-integration-ci` 全绿（无新增失败）
- [x] 8.4 端到端：`make redeploy` 后 `make deploy-status` 报最新；构造源码领先场景验证报告陈旧
- [x] 8.5 更新 specs（opsx:archive 前）
