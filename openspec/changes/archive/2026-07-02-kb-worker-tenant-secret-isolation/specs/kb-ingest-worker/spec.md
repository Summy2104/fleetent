## ADDED Requirements

### Requirement: 多租户 worker per-tenant secret 隔离

多租户 kb-worker 解析 connector 凭证(`credential_ref` 的 `env:` 引用)时 SHALL 对**该 job 所属租户的 scoped env**(从该租户 `tenants/<tenant>/kb/.env` 载为局部映射)解析,SHALL NOT 经进程全局 `os.environ` 累加解析。per-tenant `.env` 的加载 SHALL NOT 污染进程全局环境(不 `load_dotenv` 进 `os.environ`)。因此**不同租户即便使用同名 env 变量,各 connector SHALL 解析出各自租户的凭证**,不发生跨租户串号/数据泄漏。standalone / 单租户(`--tenant` 锁 或 `agent run` 同机)路径 MAY 沿用进程 `os.environ` 解析(向后兼容)。

#### Scenario: 同名 env 变量跨租户不串
- **WHEN** 租户 A 与 B 的 connectors 都引用同名 env 变量(如 `FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN`)但各自 `.env` 值不同,worker 先后处理 A、B 的 connector_sync
- **THEN** A 的同步用 A 的凭证、B 的同步用 B 的凭证(各自租户 scoped env 解析)
- **AND** 处理 B 时不因进程全局 env 已被 A 设值而误用 A 的凭证

#### Scenario: per-tenant .env 不污染全局
- **WHEN** worker 加载某租户 `.env` 以解析其 connector 凭证
- **THEN** 该加载产出局部 env 映射供本 job 解析,不写入进程全局 `os.environ`
- **AND** 后续其它租户 job 的解析不受此前租户 env 残留影响
