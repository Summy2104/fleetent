## Why

Change C（`kb-service-multi-tenant`）把 KB 变成单机多租户中心服务（本机 `kb-service.yaml` + per-tenant `connectors.yaml`/`.env`，principal 路由，worker 按需载各租户 secret），但**部署侧没跟上**：

- **docker-compose.yml**：kb-worker/kb-serve 的 `command` 已读本机 `$FLEETENT_HOME/kb-service.yaml`，但仍留 `env_file: $FLEETENT_HOME/tenants/default/kb/.env`——单租户遗留，多租户下**脆**（该文件不存在则 compose 起不来，多租户未必有 `default`）、**冗余**（整个 `FLEETENT_HOME` 已挂卷、worker 按需载各租户 `.env`）、且**放大跨租户 secret 串号风险**（预载 default secret 进程 env + 按需 `override=False` → 其它租户同名变量被 default 值覆盖）。
- **container-deployment spec**：仍描述单租户模型（`--config .../kb-service/<tenant>/kb-service.yaml` + per-tenant `env_file`），与 Change C 落地的多租户/host config 冲突（Change C 只改了 kb-standalone-ingest/read-service/worker 三 spec，漏了 container-deployment）。
- **Makefile 注释过时**（kb-worker "single queue consumer" / kb-serve "shared standalone" → 现多租户）；dev 起栈后无 KB、多租户 worker 空转（须先 `kb create`）。

本 change 把**部署侧对齐到多租户模型**。（跨租户 secret 串号的底层 worker 逻辑单独深挖修，见 #2，不在本 change。）

## What Changes

- **docker-compose.yml**：kb-worker/kb-serve **删除 `env_file: .../tenants/default/kb/.env`**（保留 `command` 读本机 `kb-service.yaml` + `FLEETENT_HOME` env + 全 HOME 卷）；worker 按需从各租户 `tenants/<t>/kb/.env` 载 secret。kb-serve 本不碰 connector secret，env_file 对它更多余。
- **container-deployment spec**：MODIFY 为多租户——kb-worker/kb-serve 以本机 `$FLEETENT_HOME/kb-service.yaml` 运行（不再 per-tenant `--config`/`env_file`），服务本机所有租户、按 principal 路由；per-tenant 数据/连接器在 `tenants/<t>/kb/`。
- **Makefile**：更新 kb-worker/kb-serve 注释为多租户；新增 `kb-create` 便利 target（`fleetent kb create --config $FLEETENT_HOME/kb-service.yaml --tenant <t> --kb <id>`），dev 起栈后可快速建 KB；`dev-reset` 提示补一句"建 KB 用 make kb-create"。

**不做**：跨租户 secret 串号的 worker 逻辑修复（#2，单独核实+修）；embedding/其它 Change C 已定项。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `container-deployment`：compose 的 kb-worker/kb-serve 从"per-tenant `--config`+`env_file`（单租户 default）"改为"本机 `$FLEETENT_HOME/kb-service.yaml`、多租户、无 per-tenant `env_file`"；共享数据卷下 worker 写 / kb-serve 读各租户 `tenants/<t>/kb/data/`；agent 经 compose 网络以服务名 `kb-serve` 读 KB 不变。

## Impact

- **部署**：`docker-compose.yml`（删 2 处 env_file）；`Makefile`（注释 + `kb-create` target + dev-reset 提示）。
- **spec**：`container-deployment` delta。
- **无代码逻辑改动**（worker/serve/config 均 Change C 已落地）；**无迁移、无 schema**。
- 兼容：删 env_file 不影响 default 租户（其 `.env` 仍在卷上、按需载）；反而修好"无 default 租户时 compose 起不来"。
