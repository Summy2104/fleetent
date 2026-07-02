## Why

**确认可复现的跨租户凭证泄漏（HIGH）**。多租户 kb-worker（Change C）处理各租户 connector_sync 时，凭证解析走**进程全局 `os.environ`**，而 worker 是长驻单进程：

1. connector 凭证经 `CredentialRefResolver.resolve()` → `os.getenv(env_name)`（`connectors/confluence.py:128`、`google_drive.py:142`）——**读进程全局 env**。
2. worker 每 job 调 `load_tenant_connectors(home, tenant)` → `load_dotenv(tenants/<t>/kb/.env, override=False)`——**往全局 env 累加、job 间不清理**。
3. 各租户 connectors.yaml 从 example scaffold、引用**通用 env 变量名**（`FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN` 等，跨租户同名）。

⟹ worker 先处理租户 A（全局 env 设为 A 的 token）、再处理 B（`override=False` 不覆盖）→ **B 的连接器用 A 的凭证同步** → 轻则失败/串源，重则 **A 的 Drive/Confluence 文档被灌进 B 的 KB（跨租户数据泄漏）**。击穿多租户隔离。

（docker-compose 的 per-tenant `env_file` 只是放大器，另由 `kb-deploy-multitenant-fixup` 删；本 change 修**根**：凭证解析不走全局 env。）

## What Changes

- **凭证解析 scoped 化**：`CredentialRefResolver.resolve(credential_ref, env=...)`（confluence + google_drive 两处）接受**显式 env 映射**参数，`env:` 引用对该映射解析，**不再默认读全局 `os.getenv`**；未传时向后兼容默认 `os.environ`（standalone/单租户不受影响）。
- **per-tenant env 载为局部 dict**：`load_tenant_connectors` 返回该租户 `.env` 解析出的**局部 env 映射**（不再 `load_dotenv` 污染进程全局 `os.environ`）。
- **worker 按 job 租户传 scoped env**：worker 处理某租户 connector_sync 时，取该租户局部 env 映射，经 `_connector_settings` / `run_connector_sync` 线程到 resolver——每租户各用各的 secret，全局 env 零污染。

**不做**：docker-compose env_file（`kb-deploy-multitenant-fixup` 已处理）；embedding/其它。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `kb-ingest-worker`：多租户 worker 的 connector 凭证解析 SHALL 用 **per-tenant scoped env**（从该租户 `.env` 载为局部映射），SHALL NOT 经进程全局 `os.environ` 累加解析；不同租户即便用**同名** env 变量，各 connector SHALL 解析出**各自租户**的凭证（无跨租户串号/泄漏）。

## Impact

- **代码**：`connectors/confluence.py` + `connectors/google_drive.py`（`CredentialRefResolver.resolve` 加 env 参数）；`service_config.py`（`load_tenant_connectors` 返回局部 env 映射、不 `load_dotenv` 全局）；`worker.py` + `operations.run_connector_sync` / `_connector_settings`（线程 per-tenant env）。
- **spec**：`kb-ingest-worker` delta（ADD per-tenant secret 隔离要求）。
- **测试**：回归——两租户同名 env 变量不同值 → 各 connector 解析各自租户凭证。
- **无迁移、无 schema、无 wire 变更**。standalone/单租户经默认 `os.environ` 向后兼容。
- 与 `kb-deploy-multitenant-fixup` **文件零重叠，可并行**。
