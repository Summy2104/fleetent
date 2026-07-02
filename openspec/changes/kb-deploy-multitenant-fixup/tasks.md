# Tasks: kb-deploy-multitenant-fixup

> 纯部署/文档对齐到 Change C 的多租户模型。无代码逻辑改动（worker/serve/config 均 C 已落地）。
> 不含 #2（跨租户 secret 串号的 worker 逻辑修）——那个单独核实+修。

## 1. docker-compose 去 per-tenant env_file

- [ ] 1.1 [impl] `docker-compose.yml`：删除 kb-worker 与 kb-serve 服务块里的 `env_file: - ${FLEETENT_HOME}/tenants/default/kb/.env`（两处）。保留 `command`(读本机 `${FLEETENT_HOME}/kb-service.yaml`)、`environment: FLEETENT_HOME`、`volumes: *fleetent-home-volume`（全 HOME 卷）。
- [ ] 1.2 [verify] 起栈冒烟（或静态校验）：compose 在**无 `tenants/default/kb/.env`** 时仍能起 kb-worker/kb-serve（不因缺文件失败）；worker 处理某租户 job 时经 `load_tenant_connectors` 从该租户 `tenants/<t>/kb/.env` 载 secret。

## 2. container-deployment spec 对齐（delta 已在本 change）

- [ ] 2.1 delta 已把 "Compose 编排长驻服务全栈" 改为多租户 host config + 无 per-tenant env_file——archive 时同步进 `openspec/specs/container-deployment/spec.md`。

## 3. Makefile 注释 + kb-create 便利 target

- [ ] 3.1 [impl] 更新注释：`kb-worker` → "Start the multi-tenant KB ingest worker (polls all tenant queues)"；`kb-serve` → "Start the multi-tenant KB read/API service (host kb-service.yaml)"。
- [ ] 3.2 [impl] 新增 `kb-create` target：`uv run fleetent kb create --config $(FLEETENT_HOME)/kb-service.yaml --tenant $(or $(TENANT),default) --kb $(KB)`（`@test -n "$(KB)" || { echo "usage: make kb-create KB=<id> [TENANT=default]"; exit 2; }`）；加进 `DEV_TARGETS` 的 env 导出组。`dev-reset` 提示补一句"建 KB：make kb-create KB=<id>"。

## 4. 收尾门禁（全绿才算完）

- [ ] 4.1 `openspec validate kb-deploy-multitenant-fixup --strict`
- [ ] 4.2 `make test-pr` + `make test-integration-ci`（本 change 不改代码逻辑，判据"对照 main 基线无新增失败"；若有 compose/部署相关测试如 test_deployment_docs / container 一并绿）。
- [ ] 4.3 手验：`docker compose config` 校验通过；`make kb-create KB=demo` 在 dev 起栈后建出 KB、`kb serve` 检索可命中。
- [ ] 4.4 tasks.md 全 `[x]`；功能分支 `openspec archive kb-deploy-multitenant-fixup`（同步 container-deployment spec）；**不扫 openspec/changes/archive/ 历史产物**；commit（含 Co-Authored-By 签名）+ 推分支；**不 merge main，等 Randy 定夺**。
