## Why

为了避免一开始引入完整 scheduler / worker / workflow UI，Pilot 可以先依赖可靠的手动维护入口。但这些入口
必须可 dry-run、可审计、输出可读 summary，并对 destructive 操作要求显式确认。否则内测跑几天后，
memory、KB、vector index 和 reflection proposal 状态不可控。

## What Changes

- 新增或补齐手动维护 CLI / admin entrypoints：
  - memory retention / compaction dry-run / apply
  - KB sync dry-run / execute
  - vector reindex dry-run / apply / rebuild
  - reflection report run
  - maintenance proposal list / approve / reject / apply
- destructive 操作必须先支持 dry-run，apply/rebuild/delete 必须带 `--yes`。
- 每次 apply/rebuild/delete/approve/reject 写 audit 或 observability event。
- 内测阶段允许 CLI 直接触发 Memory / Reflection / Vector / KB 维护操作，但不做自动定时触发。
- 输出 human-readable summary 和 JSON summary，供 Pilot report / diagnostics 引用。

## Capabilities

### New Capabilities

- `manual-maintenance-entrypoints`: Pilot 期间无 scheduler/UI 情况下的受控手动维护入口。

## Impact

- **owning package**：`platform.admin_cli` 作为入口；实际操作归各 owner module public API。
- **public API surface**：可新增 admin CLI subcommands 和 summary DTO。
- **owned tables**：无新增业务表；如需要 audit event 则复用 audit/observability。
- **config namespace**：无。
- **cross-module dependencies**：调用 memory、knowledge_base、vector_store、reflection public API；写 audit/trace public API。
- **migration / shim plan**：无。

## Non-Goals

- 不实现 scheduler / worker。
- 不实现 review UI。
- 不允许无确认 destructive apply。
- 不新增自动修复或自动发布。

## Strategy Defaults for Review

- All destructive operations require `--yes`.
- Rebuild operations must support dry-run and print affected namespace/source counts.
- Shared Memory direct admin edit is not included; use proposal/apply lifecycle first.
- No scheduler/worker automation in this change; operators trigger maintenance manually.
