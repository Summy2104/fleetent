## Context

多租户 kb-worker 凭证解析走进程全局 os.environ + `load_dotenv(override=False)` 跨租户累加 + 通用 env 变量名 → 确认可复现跨租户凭证/数据泄漏（详见 proposal 复现链）。修根：凭证解析 scoped 到 per-tenant env，不碰全局。

## Goals / Non-Goals

**Goals**
- 多租户 worker 各租户 connector 用各自租户 secret，全局 env 零污染。
- 同名 env 变量跨租户不串。

**Non-Goals**
- 不改 docker-compose env_file（fixup 处理）。
- 不改 embedding/检索/其它。
- 不改 standalone/单租户既有行为（向后兼容）。

## Decisions

**D1：resolver 收显式 env 映射，默认 os.environ。** `CredentialRefResolver.resolve(credential_ref, env: Mapping[str,str] | None = None)`（confluence + google_drive）：`env:` 引用对 `env`（缺省 `os.environ`）解析。standalone/单租户不传 → 走 os.environ（现状不变）；多租户 worker 传 per-tenant scoped 映射。`file://` 引用不受影响（读文件）。

**D2：`load_tenant_connectors` 返回局部 env 映射、不污染全局。** 不再 `load_dotenv(env_path, override=False)` 进 os.environ；改为**解析该租户 `.env` 为局部 dict**（`dotenv.dotenv_values(env_path)`）返回给调用方。这样进程全局 env 不再跨租户累加。

**D3：worker 按 job 租户线程 scoped env。** worker 处理某租户 connector_sync：取该租户局部 env（D2）→ 经 `_connector_settings` / `run_connector_sync` 传到 connector 客户端构造与 resolver → 该 job 只用该租户 secret。多个租户 job 顺序处理互不污染（无共享全局 env）。

**D4：向后兼容 standalone。** 单租户 standalone（`--tenant` 锁 或 `agent run` 同机）resolver 不传 env → 默认 os.environ，行为不变；`load_tenant_connectors` 的局部返回只在多租户 worker 路径消费。

## Risks / Trade-offs

- **resolver 签名变更波及调用点** → 加**可选** env 参数（默认 os.environ），非破坏；grep 所有 `CredentialRefResolver().resolve(` / connector 客户端构造点，多租户路径显式传 env，其余不变。
- **operations.run_connector_sync 需接受并下传 env** → 若其签名不便加参数，可让 `_connector_settings` 在多租户路径预解析凭证进 settings（scoped），避免深层 os.getenv；apply 时按实际调用链选侵入最小的接法。
- **`dotenv_values` vs `load_dotenv`** → 前者返回 dict 不改全局，正是所需；确认 python-dotenv 版本支持（已用 load_dotenv，同库）。

## Migration Plan

无迁移。纯逻辑修。回滚 = revert（回到全局 env 解析，恢复串号风险）。

## Open Questions

无（若 run_connector_sync 深层仍读 os.getenv，则在 connector 客户端构造边界注入 scoped 凭证——apply 时按调用链定最小侵入点）。
