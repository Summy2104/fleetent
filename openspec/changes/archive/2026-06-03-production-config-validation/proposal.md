## Why

Pilot 内测失败最常见的原因不是核心代码不可用，而是 provider route、credential_ref、data/secrets
目录权限、真实 smoke flag 或明文 secret 配置不一致。当前已有 `settings.yaml`、Pilot runbook 和
verification report，但缺少一个统一的 production / pilot profile 配置校验入口。

这个 change 增加配置校验能力，让 operator 在启动、验收或真实 smoke 前得到清晰的 pass / warning /
skipped / error 结果，减少人工排障。

## What Changes

- 新增配置校验入口（CLI 或 script），检查 settings、routes、credential_ref、data/secrets 目录、数据库 URL
  和真实 smoke 前置条件。
- 支持 profile：`dev`、`pilot`、`production`。
- `dev` 中缺少真实外部凭据为 warning；`pilot` 中记录为 skipped reason；`production` 中关键外部依赖缺失为 error。
- 检测 settings / routes / mcp config 中的疑似明文 secret，并 fail loud。
- 输出 Markdown/JSON friendly 的 validation summary，供 pilot verification report 复用。

## Capabilities

### New Capabilities

- `production-config-validation`: 配置、路径、credential_ref 和真实 smoke 前置条件校验。

## Impact

- **owning package**：`infrastructure/config` 概念归属；实现可放在 `fleetent.config` 附近或新增
  `fleetent.observability` / `platform.admin_cli` 入口暴露 summary。
- **public API surface**：可新增 `validate_runtime_config(profile: str) -> ValidationReport` 和
  `fleetent-admin validate-config`。
- **owned tables**：无。
- **config namespace**：无新运行配置；新增 CLI 参数/profile 名称。
- **cross-module dependencies**：读取 config、model routes、MCP config、connector credential_ref 和
  diagnostics/pilot verification public API；不得 import package internal 实现。
- **migration / shim plan**：无。

## Non-Goals

- 不实现 config center、hot reload 或 UI。
- 不读取真实 secret payload；只验证引用存在和权限边界。
- 不默认连接真实外部服务；连接测试仍由 opt-in smoke 负责。
