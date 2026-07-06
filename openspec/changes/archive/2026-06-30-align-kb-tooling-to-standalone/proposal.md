## Why

KB 运行时已统一到 standalone 单一模型(`kb-service.yaml` + 本地队列 + 退役平台托管),但 **Makefile / CLI 工具链落后于该架构**,导致:
- **没有任何命令生成 `kb-service.yaml`**——compose 的 kb-worker/kb-serve 都 `--config kb-service.yaml`,却无 provisioning;`kb-worker init-config` 产的是**退役掉的** `kb-worker/.env`(旧平台托管模型)。
- **dev `make kb-worker` 跑 `fleetent kb worker` 不带 `--config`** → 走旧 management.db 队列模型(已退役),处于半坏状态;dev **完全没有 kb-serve**。
- dev(旧模型)与 compose(新 standalone 模型)**配置模型分裂**。

本 change 把工具链对齐到单一模型:KB 服务的配置 + secrets 收成一个 `kb-service/` 目录(yaml + .env,kb-worker 与 kb-serve **共用**),由统一的 ``kb-service` `init-config`` 生成;dev 与 compose 都用同一份、同一模型。

## What Changes

- **新 CLI `fleetent kb init-config`**:scaffold `$FLEETENT_HOME/kb-service/`(`kb-service.yaml` + `.env`),源自仓库根的 `kb-service.yaml.example` + `kb-service.env.example`(经打包资源读取,不依赖 cwd)。worker 与 serve 共用该目录。
- **退役 `fleetent kb worker init-config` + `kb-worker.env.example`**(旧平台托管 worker 配置模型)。
- **配置/secrets 布局**:`$FLEETENT_HOME/kb-service/kb-service.yaml`(非密)+ `$FLEETENT_HOME/kb-service/.env`(KB 服务 secrets:`KB_SERVICE_KEY`/`KB_CONN_*`/`KB_EMBEDDING_API_KEY` 等),**与 platform 的 `.env` 分开**(KB 独立主机只需这一份)。example 模板**平铺在仓库根**(`kb-service.yaml.example` + `kb-service.env.example`,守 `configuration` spec 的 flat-at-root 标准),并把现有 `examples/kb-service/*` 移到根、删 `examples/kb-service/` 目录。
- **Makefile dev 对齐**:`dev-bootstrap` 用 ``kb-service` `init-config``(替 `kb-worker init-config`);dev `kb-worker` target 加 `--config $(FLEETENT_HOME)/kb-service/kb-service.yaml`;**新增 dev `kb-serve` target**;`kb-serve` 进 `DEV_TARGETS`;`dev-reset` 起服务提示加 kb-serve。
- **docker-compose 路径对齐**:kb-worker/kb-serve 的 `--config` → `${FLEETENT_HOME}/kb-service/kb-service.yaml`;`env_file` → `${FLEETENT_HOME}/kb-service/.env`。

不改变:KB 业务代码(serve/worker/standalone ingest);`kb-serve`/`kb-worker` 运行命令名;platform/node 的配置与 .env;`kb-service.yaml` schema。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `kb-standalone-ingest`: 新增 ``kb-service` `init-config`` 命令 + `kb-service/` 目录布局(yaml + .env,worker/serve 共用、与 platform .env 分开)。
- `kb-ingest-worker`: worker 自身配置从旧 `kb-worker/.env` 模型改为 KB 服务共用的 `kb-service/`(yaml + .env);退役 `kb-worker init-config`。
- `container-deployment`: compose kb-worker/kb-serve 的 `--config` 与 `env_file` 指向 `kb-service/`。

## Impact

- **owning area**:`src/fleetent/knowledge_base`(新 ``kb-service` `init-config``、退旧 worker init-config)+ `__main__.py`(命令分派)+ `Makefile`(dev targets)+ `docker-compose.yml`(路径)+ 仓库根 example(`kb-service.yaml.example` + `kb-service.env.example`,从 `examples/kb-service/` 移来)+ pyproject(example 纳入 wheel package data)。
- **public API surface**:新增 `fleetent kb init-config`;退役 `fleetent kb worker init-config`;运行命令 `kb-serve`/`kb-worker` 不变。
- **owned tables**:无。
- **config namespace**:`kb-service/` 目录(yaml + .env);移除 `kb-worker/.env`。
- **cross-module 依赖**:无;`knowledge_base` ✗→ platform 保持。
- **dev/compose 一致性**:两者收敛到同一 `kb-service/` + 同一 standalone 模型;`make dev-reset` 后可完整起 platform/node/kb-worker/kb-serve。
- **测试**:unit(`kb-service` `init-config` scaffold 计划/幂等/force;退役 worker init-config)+ integration(dev kb-worker/kb-serve 经 kb-service/ 配置启动)。docs 更新部署/dev 指南。
