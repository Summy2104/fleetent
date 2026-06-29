## Why

KB 独立部署线已收敛成单一模型:`kb-serve`(读 API)+ `kb-worker`(本地队列 ingest)。`kb-worker` 已在 `docker-compose.yml`,但 **`kb-serve` 还没进 compose**——意味着 managed 栈起来后,agent 无法经 HTTP 读 KB 服务(provider=http 指向的端点不存在)。本 change(#3,折进 container-deployment / dockerize 线)把 `kb-serve` 补成 compose 的第四个长驻服务,让"agent 经 HttpKnowledgeProvider 远程读 KB"在 compose 栈里端到端可达。

`fleetent kb-serve` CLI 入口已存在(`__main__.py`),无需新代码;本 change 是**部署接线 + spec**,不碰 KB 业务代码。

## What Changes

- **compose 加 `kb-serve` 服务**:照 `kb-worker` 块(同镜像、`command: ["kb-serve", "--config", "$FLEETENT_HOME/kb-service.yaml"]`、env_file、FLEETENT_HOME、restart),并:
  - 接入 `fleetent` 网络,使 node 拉起的 agent 兄弟容器经服务名 `kb-serve:<port>` 可达;
  - 与 `kb-worker` **共享同一 `FLEETENT_HOME` 卷**(worker 写 `tenants/<t>/kb/`、serve 读同一 kb/,单机 WAL 一写多读);
  - **不挂** Docker socket(同 platform/kb-worker)。
- **agent 指向 kb-serve**:agent 的 `knowledge.provider`(http)`url` 在 compose 内指向 `http://kb-serve:<port>`(node materialize / 配置接线)。
- **docs**:compose 文档加 kb-serve 角色、agent→kb-serve 寻址、kb-service.yaml/.env provisioning。

不改变:KB 业务代码(serve/worker/standalone ingest 已落地);platform/node/kb-worker 既有服务;path-parity 卷布局;forwarder 寻址。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `container-deployment`: entrypoint 多角色加 `kb-serve`;compose 长驻服务由三个(platform/node/kb-worker)变四个(+kb-serve),并约束 kb-serve 接入网络、共享 kb/ 卷、不挂 socket。

## Impact

- **owning area**:`docker-compose.yml` + `container-deployment` spec + 部署文档。不碰 `src/fleetent`(CLI 入口 `kb-serve` 已存在)。
- **public API surface**:compose 新增 kb-serve 服务;无代码 API 变更。
- **owned tables**:无。
- **config namespace**:kb-serve 经 `kb-service.yaml` + `.env`(已由 kb-standalone-ingest 定义);compose 复用既有 FLEETENT_HOME 卷与 .env。
- **cross-module 依赖**:无;保持 agent→kb-serve(基础设施,HTTP)、agent ✗→ platform。
- **网络**:agent 兄弟容器需与 kb-serve 同网络可达(沿用 agent↔node 同网络的既有接线)。
- **多租户**:per-tenant 进程——compose 默认起单租户 `kb-serve --tenant default`(配置文件指定);多租户为每租户加一个 kb-serve 服务。
- **测试/验证**:compose 栈烟测(stack boot,kb-serve 在网络内可达,agent 经 http provider 读到 kb/);沿用现有 managed-stack e2e harness。
