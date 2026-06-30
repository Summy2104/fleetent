## 1. kb-service init-config 命令 + 模板打包

- [x] 1.1 写 unit 测试:`kb-service init-config` 在 `$FLEETENT_HOME/kb-service/` 生成 `kb-service.yaml` + `.env`;幂等(已存在 skip)、`--force` 覆盖;**在非仓库 cwd 下也能生成**(模板从 package data 读,不依赖 cwd)(见红)
- [x] 1.2 移 `examples/kb-service/kb-service.example.yaml` → 根 `kb-service.yaml.example`、删 `examples/kb-service/` 目录;把根 `kb-service.yaml.example` + `kb-service.env.example` 纳入 wheel package data(pyproject);实现 `kb-service init-config`(`importlib.resources` 读根模板,不依赖 cwd);`__main__.py` 加 `kb-service` 分派;跑 1.1 见绿
- [x] 1.3 加根 `kb-service.env.example`(KB_SERVICE_KEY / KB_CONN_* / KB_EMBEDDING_API_KEY / KB_EXTRACTION_API_KEY,注释鼓励 credential_ref 复用)

## 2. 退役旧 kb-worker init-config

- [x] 2.1 写 unit 测试:`fleetent kb-worker init-config` 不再存在(见红/对照)
- [x] 2.2 删 `worker_init_config.py` + `kb-worker.env.example`;`__main__.py` 的 kb-worker 分支移除 init-config 子命令;删对应测试;跑 2.1 见绿;`git grep kb-worker.env\|worker_init_config` 无悬空引用

## 3. Makefile dev 对齐

- [x] 3.1 `dev-bootstrap`:`uv run fleetent kb-worker init-config` → `uv run fleetent kb-service init-config`
- [x] 3.2 dev `kb-worker` target:`uv run fleetent kb-worker --config $(FLEETENT_HOME)/kb-service/kb-service.yaml`
- [x] 3.3 新增 dev `kb-serve` target:`uv run fleetent kb-serve --config $(FLEETENT_HOME)/kb-service/kb-service.yaml`;`kb-serve` 加进 `DEV_TARGETS`;`dev-reset` 提示加 kb-serve
- [x] 3.4 integration/烟测:`make dev-reset` 后 dev kb-worker 与 kb-serve 经 `kb-service/` 配置可启动(取到 .env secrets)

## 4. compose 路径对齐

- [x] 4.1 docker-compose:kb-worker/kb-serve 的 `--config` → `${FLEETENT_HOME}/kb-service/kb-service.yaml`;`env_file` → `${FLEETENT_HOME}/kb-service/.env`
- [x] 4.2 `docker compose config` 校验通过;四服务都在、路径正确

## 5. 收尾

- [x] 5.1 跑 `make test-pr` + `make test-unit-ci`(含 76% 覆盖率关)+ `make test-integration-ci`,判"对照 main 基线无新增失败、覆盖率不破 76"(并行 flaky 先 `-p no:randomly` 串行复核)
- [x] 5.2 ruff format/check;module-boundaries 护栏过;`openspec validate align-kb-tooling-to-standalone` 通过
- [x] 5.3 更新 docs(部署 + dev 指南):`kb-service init-config` 生成 `kb-service/`、worker/serve 共用、与 platform .env 分开、存量从 kb-worker/.env 迁移步骤(非代码产物,人工确认后再 commit)
