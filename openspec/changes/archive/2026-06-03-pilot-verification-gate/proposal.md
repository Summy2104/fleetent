## Why

项目已经有 pilot verification report，但内测前门禁还没有被定义成稳定 release / Pilot gate。为了避免
“测试跑过但证据不可复核”，需要把默认命令、OpenSpec validate、module boundary、capability evidence
和 real smoke skipped/pass/fail 规则固定下来。

## What Changes

- 定义 `pilot-verification-gate`：内测前推荐运行的标准命令集合和报告判定规则。
- 将 config validation、diagnostics artifact、pytest layers、OpenSpec validate、module boundary check 和
  opt-in smoke 状态聚合到 Markdown/JSON report。
- 给出明确最终状态：`Go`、`Conditional Go`、`No-Go`。
- 将 `Pilot blocker`、Docs gap、Enhancement、Out-of-scope 分类作为 gate 的一部分。

## Capabilities

### New Capabilities

- `pilot-verification-gate`: Pilot / 内测前验证门禁和报告判定规则。

## Impact

- **owning package**：`observability`。
- **public API surface**：可扩展 `scripts/generate_pilot_verification_report.py` 或新增 admin CLI wrapper。
- **owned tables**：无。
- **config namespace**：无。
- **cross-module dependencies**：执行测试命令、OpenSpec validate、module boundary check、config validation、
  diagnostics export 和 opt-in smoke public entrypoints。
- **migration / shim plan**：无。

## Non-Goals

- 不替代完整 CI 系统。
- 不要求默认连接真实外部服务。
- 不自动修复失败项。
