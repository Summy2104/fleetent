## Context

Change C 落地多租户 KB 服务（本机 `kb-service.yaml` + per-tenant `tenants/<t>/kb/{connectors.yaml,.env,data/}`，worker 经 `load_tenant_connectors` 按需载各租户 `.env`）。部署侧遗漏：docker-compose 仍 per-tenant `env_file`、container-deployment spec 仍单租户描述、Makefile 注释过时 + dev 无建 KB 便利。本 change 纯部署/文档对齐，无代码逻辑改动。

## Goals / Non-Goals

**Goals**
- docker-compose kb 服务去 per-tenant env_file，符合多租户（host config + 按需载 secret + 全 HOME 卷）。
- container-deployment spec 对齐多租户。
- Makefile 注释更新 + `kb-create` 便利 target。

**Non-Goals**
- 不改 worker/serve/config 代码逻辑（Change C 已落地）。
- 不修跨租户 secret 串号（#2，单独核实+修）。

## Decisions

**D1：docker-compose 删 env_file，不换成"载所有租户 env"。** worker 经 `load_tenant_connectors` 按需从 `tenants/<t>/kb/.env` 载（卷已挂全 `FLEETENT_HOME`）——boot 时预载任何单租户 env 都错（脆 + 串号）。故直接删 `env_file`，让按需载生效。kb-serve 不碰 connector secret，无需 env_file。

**D2：spec 对齐 Change C 的真实布局。** container-deployment 的 `--config`/`env_file`/data 路径从 `kb-service/<tenant>/` 旧描述改为：kb-worker/kb-serve 用本机 `$FLEETENT_HOME/kb-service.yaml`（无 per-tenant env_file），数据在 `tenants/<t>/kb/data/`，服务本机所有租户。

**D3：dev 便利 `kb-create` target。** `kb create` 已支持 `--config <host> --tenant <t> --kb <id>`（Change C 加的 `--tenant`）。加参数化 make target，dev 起栈后 `make kb-create KB=<id> [TENANT=default]` 即可建 KB，解多租户 worker 起栈后无租户空转的体感。

## Risks / Trade-offs

- **删 env_file 后 default 租户 secret 仍可达吗** → 可达：`tenants/default/kb/.env` 在挂载的 `FLEETENT_HOME` 卷上，worker 处理 default 的 job 时 `load_tenant_connectors` 按需载。不丢功能，反修"无 default 时 compose 起不来"。
- **spec 与 #2（secret 串号）耦合** → 本 change 只对齐部署形态；串号是 worker 载 secret 的逻辑问题，删 env_file 消掉其"放大器"但不算根治，#2 单独修。design 注明。

## Migration Plan

无迁移。改 compose/Makefile/spec。回滚 = revert。

## Open Questions

无。
