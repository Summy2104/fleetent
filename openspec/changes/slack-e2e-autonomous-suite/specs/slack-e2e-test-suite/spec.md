## REMOVED Requirements

### Requirement: Chinese scenario catalog

**Reason**: 旧套件经 Claude Slack MCP 收发、场景写死在 yaml，无法测试文件收发、不支持自主探索；由 `slack-e2e-autonomous-suite` 全面取代。

**Migration**: 改用 `slack-e2e-autonomous-driver` 的结构化能力覆盖清单 + rubric，对话由 Claude 自主驱动而非写死 yaml。

### Requirement: Coverage completeness

**Reason**: frozen 17-tag 覆盖集已被新套件约 50 点的 A/B/C 分组覆盖清单取代。

**Migration**: 见 `slack-e2e-autonomous-driver` 的「覆盖清单驱动与分组门控」requirement。

### Requirement: LLM-as-user black-box execution

**Reason**: MCP 通道无法上传文件，黑盒执行改由 Slack Web API helper 承载。

**Migration**: 见 `slack-e2e-api-helper`（收发契约）与 `slack-e2e-autonomous-driver`（黑盒执行与诚实铁律）。

### Requirement: Honesty rules

**Reason**: 诚实铁律由新套件承接，措辞与判定机制更新。

**Migration**: 见 `slack-e2e-autonomous-driver` 的「黑盒执行与诚实铁律」requirement。

### Requirement: Catalog validator (automated gate)

**Reason**: 旧 yaml catalog 废弃，对应 validator（`tests/integration/test_slack_scenarios_catalog.py`）一并移除。

**Migration**: 新套件覆盖清单的结构校验由 `slack-e2e-autonomous-driver` 的清单校验 requirement 及其 unit 测试（`tests/unit/test_slack_e2e_catalog.py`）承接，仍进常规测试套件。

### Requirement: Slack E2E sample agent is a test fixture

**Reason**: 随旧 `tests/e2e/slack_scenarios/` 目录一并移除。

**Migration**: 被测 agent 由用户在运行时显式指定（agent / bot user id / channel / user token），不再依赖随附 sample agent fixture。
