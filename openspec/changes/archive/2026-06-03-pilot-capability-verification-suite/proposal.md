## Why

`docs/capabilities/owner-capability-roadmap.md` 已把常乐负责范围收敛到 Observability、Memory、
Long-term Context、Reflection、Vector Store、Knowledge Base、Deployment / Config，并明确当前
Pilot Go / No-Go 不能只看默认测试是否通过，还需要准生产环境 smoke 和人工可审阅凭证。

当前项目已有 `tests/unit`、`tests/integration`、`tests/e2e`、`tests/evaluation` 分层，也已有部分
capability 级测试。但 owner roadmap 还缺一组统一的测试补强与验收报告入口，把“底层 contract 是否稳”、
“关键用户路径是否跑通”和“人工是否能看懂证据”串起来。这个 change 专门补测试和报告，不扩大产品功能。

## What Changes

- 新增 **Owner Capability Verification** 测试分组，覆盖 roadmap 中的 7 个 owner 能力域：
  Observability、Memory、Long-term Context、Reflection、Vector Store、Knowledge Base、
  Deployment / Config。
- 补充 capability contract integration tests：使用 tmp SQLite、fake provider、fake connector 和 fixture，
  验证 public API、store、trace、policy、sync、reindex、reflection proposal 等跨模块契约。
- 补充少量 Pilot acceptance E2E smoke：直接对应 Pilot 人工验收路径，默认只使用本地 / fake / dry-run
  依赖；真实 LLM、embedding、rerank、Google Drive、Confluence 和 Docker Compose 演练必须显式 opt-in。
- 新增可读验证报告生成入口：聚合 pytest、coverage、capability contract、evaluation、E2E smoke 和
  opt-in real smoke 的结果，输出 Markdown/JSON 证据，供人工判定 Go / Conditional Go / No-Go。
- 将报告问题分类固定为 roadmap 中的 `Pilot blocker`、`Docs gap`、`Enhancement`、`Out-of-scope`。

## Capabilities

### New Capabilities

- `pilot-capability-verification`: owner capability 验收测试与报告契约，要求测试、报告和人工凭证能支持
  Pilot Go / No-Go 判定。

### Modified Capabilities

<!-- 无：本 change 新增测试与验证报告能力，不改变已有业务 capability 的 public API。 -->

## Impact

- **owning package**：`observability` 为报告/证据聚合的主要归属；测试会覆盖 `intelligence`、
  `platform`、`integrations`、`runtime legacy flat modules` 和 `infrastructure/config` 的 public API。
- **public API surface**：允许新增测试/报告脚本入口，例如 `scripts/generate_pilot_verification_report.py`
  或等价 CLI；业务 public API 不因本 change 扩大。
- **owned tables**：无新增持久化表；测试使用 tmp SQLite / fixture，不触碰 `data/`。
- **config namespace**：可新增测试专用环境变量，例如 `FLEETENT_REAL_LLM_SMOKE=1`、
  `FLEETENT_REAL_EMBEDDING_SMOKE=1`、`FLEETENT_REAL_RERANK_SMOKE=1`、
  `FLEETENT_GOOGLE_DRIVE_SMOKE=1`、`FLEETENT_CONFLUENCE_SMOKE=1`，默认关闭。
- **cross-module dependencies**：测试只通过各模块 public API、admin CLI 或 HTTP/CLI 入口调用；不得
  import 已迁移 package 的 internal 实现。
- **migration / shim plan**：无迁移；如测试发现 legacy flat module 缺少可测边界，只做最小 public helper
  或 fixture seam，不引入业务迁移。

## Non-Goals

- 不实现 platform dashboard / review UI。
- 不默认连接真实 LLM、embedding、rerank、Google Drive 或 Confluence。
- 不把 graph / rerank 设为 agent 默认搜索策略。
- 不做真实生产环境的 secret manager 选型。
- 不用 E2E 覆盖所有组合；E2E 只覆盖少量 Pilot 关键路径。
