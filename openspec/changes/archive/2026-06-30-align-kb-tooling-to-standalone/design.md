## Context

KB 运行时已统一 standalone(`kb-service.yaml` + 本地队列 + 退役平台托管),工具链未跟上。现状:
- `worker_init_config.py`:产 `kb-worker/.env`(模板 `kb-worker.env.example`),且 `source_path = Path.cwd() / 模板`(**依赖 cwd**)。
- `__main__.py`:`kb-worker`(有 init-config)/`kb-serve`(无 init-config)。
- `worker.py main`:`--config` 才走 standalone(service_config),否则旧 `load_config()`。
- Makefile:dev `kb-worker` 不带 `--config`;无 dev `kb-serve`;`dev-bootstrap` 跑 `kb-worker init-config`。
- compose:扁平 `${FLEETENT_HOME}/kb-service.yaml` + `env_file: .env`(根)。
- example:现有 `examples/kb-service/kb-service.example.yaml` —— 本 change 移到仓库根 `kb-service.yaml.example`(守 `configuration` spec 的 flat-at-root),并加 `kb-service.env.example`。

## Goals / Non-Goals

**Goals:**
- 新 `fleetent kb init-config` scaffold `kb-service/`(yaml + .env),退役 `kb-worker init-config`。
- dev/compose 都用 `kb-service/`(worker+serve 共用)+ standalone 单一模型。
- 模板可靠寻址(打包,不依赖 cwd)。

**Non-Goals:**
- 不改 KB 业务代码(serve/worker/ingest)、不改 `kb-service.yaml` schema、不改 `kb-serve`/`kb-worker` 运行命令名。
- 不改 platform/node 配置与 .env。

## Decisions

### 决策:`kb-service/` 目录 = KB 服务的配置单元(yaml + .env)
- `$FLEETENT_HOME/kb-service/kb-service.yaml`(非密)+ `kb-service/.env`(secrets)。worker 与 serve 共用。与 platform `.env` 分开——独立主机只拎 `kb-service/`。镜像/node 的 secrets 各自独立(platform `.env`、`node/.env` 已有),`kb-service/.env` 平行。

### 决策:`fleetent kb init-config` 统一 provisioning
- scaffold `kb-service/`(yaml + .env)源自仓库根 canonical example(`kb-service.yaml.example` / `kb-service.env.example`)。幂等(skip / `--force`)。退役 `fleetent kb worker init-config` + `kb-worker.env.example` + `kb-worker/.env`。
- **命令分派**:`__main__.py` 加 `kb-service` 分支(init-config 子命令);`kb-worker` 分支移除 init-config 子命令。

### 决策:模板打包,不依赖 cwd(修旧 init-config 的脆弱点)
- 旧 `worker_init_config` 用 `Path.cwd()/模板`——`uv tool install` 后无仓库 `examples/` 即失败。新 ``kb-service` `init-config`` SHALL 从**打包进 wheel 的 package data**(`importlib.resources`)读取根 canonical example,不依赖 cwd。根 `kb-service.yaml.example` / `kb-service.env.example` 纳入 package data(pyproject)。(platform/node 的同类 cwd 修复在 `normalize-service-config-layout`。)

### 决策:Makefile dev 对齐
- `dev-bootstrap`:`kb-worker init-config` → ``kb-service` `init-config``。
- dev `kb-worker` target:加 `--config $(FLEETENT_HOME)/kb-service/kb-service.yaml`。
- 新增 dev `kb-serve` target:`fleetent kb serve --config $(FLEETENT_HOME)/kb-service/kb-service.yaml`。
- `kb-serve` 加进 `DEV_TARGETS`(env 导出);`dev-reset` 提示加 kb-serve。

### 决策:compose 路径对齐
- kb-worker/kb-serve 的 `--config` → `${FLEETENT_HOME}/kb-service/kb-service.yaml`;`env_file` → `${FLEETENT_HOME}/kb-service/.env`。

## Risks / Trade-offs

- **[模板寻址在装好环境失效]** 旧 cwd 依赖的坑。**Mitigation**:模板纳入 package data + `importlib.resources` 读取;测试在非仓库 cwd 下跑 init-config 仍生成。
- **[compose 路径变更]** #3 刚落地的扁平路径改 `kb-service/`。**Mitigation**:本 change 一并改 compose + spec,保持一致;`docker compose config` 校验。
- **[dev .env 加载]** dev bare-metal 下 kb-worker/kb-serve 取 `kb-service/.env` secrets。**Mitigation**:进程 `load_dotenv($FLEETENT_HOME/kb-service/.env)` 或 Makefile 导出;测试覆盖 dev 启动取到 secrets。
- **[存量 kb-worker/.env]** 已有环境的旧文件。**Mitigation**:退役即不再读;文档说明迁移到 `kb-service/`(把 embedder 等挪进 kb-service.yaml、secrets 挪进 kb-service/.env)。

## Migration Plan

- 加 ``kb-service` `init-config`` + 根 example 纳入 package data;移 `examples/kb-service/*`→根、删该目录、加 `kb-service.env.example`;退 `kb-worker init-config`/旧模板;改 Makefile dev + compose 路径。
- 升级:存量把 `kb-worker/.env` 内容迁到 `kb-service/`(docs 给步骤);跑 ``kb-service` `init-config`` 生成新布局。
- 回滚:还原代码;旧 `kb-worker/.env` 路径需手工恢复(故 merge 前验证 dev/compose 都能起)。

## Open Questions

- `kb-service/.env` 的 dev 加载方式(进程 load_dotenv vs Makefile export):实现时按现有 kb-worker .env 加载范式对齐。
