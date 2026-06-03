## Why

内测和 Pilot 可以没有完整 dashboard，但必须能安全导出问题证据。当前 diagnostics 已有基础导出和 retention
边界，但生产交付前需要更明确的 manifest、redaction、禁止项和导出权限契约，避免把 secret、SQLite 主库、
完整 prompt/reply 或 KB 正文放进问题上报包。

## What Changes

- 强化 diagnostics export：增加 manifest、artifact list、redaction summary 和 skipped item reason。
- 默认只导出 summary / metadata，不导出完整 prompt、reply、KB 正文、SQLite 主库、backup 或 secret payload。
- 提供显式 safe payload flag，仅允许导出已脱敏 trace payload 摘要，不导出原文。
- 将 diagnostics export 接入 pilot verification report 的 artifact evidence。

## Capabilities

### New Capabilities

- `diagnostics-redaction-export-hardening`: 安全诊断包导出、manifest 和 redaction 契约。

## Impact

- **owning package**：`observability`。
- **public API surface**：可扩展 diagnostics export API / admin CLI 输出 manifest。
- **owned tables**：无。
- **config namespace**：可新增 diagnostics export 参数或 CLI flag；不新增生产常驻配置。
- **cross-module dependencies**：读取 observability traces、usage/performance summary、config summary、connector status
  public API；不得读取 secret payload 或 SQLite 主库文件。
- **migration / shim plan**：无。

## Non-Goals

- 不实现 dashboard / alerting。
- 不导出完整 transcript、prompt、reply、KB document content、SQLite 主库或 backups。
- 不压缩/上传到外部服务。
