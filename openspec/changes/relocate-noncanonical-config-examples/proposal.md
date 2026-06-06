## Why

`config/` 目录现在仍同时承载 active deployment templates 与非 canonical 示例：

- `config/agents/*/agent.yaml.example` 是 legacy/dev multi-agent scan 示例和 Slack E2E 测试样例；它与 canonical `config/agent/agent.yaml.example` 只有单复数差异，容易被误解为部署入口。
- `config/knowledge-service/*` 是未来 standalone Knowledge Service 的示例模板；默认 MVP 部署中 Knowledge 与 Platform 一起部署，不应让 operator 以为 active `config/` 下必须维护独立 service config。

上一轮配置治理已经确立 `config/` 的一等边界是 Platform / Agent。为了降低路径歧义，非默认示例应移出 active `config/`，放到 `examples/` 或测试 fixture 目录。

## What Changes

- `config/` 下只保留 active canonical 模板目录：
  - `config/platform/`
  - `config/agent/`
- 删除或迁移 `config/agents/*`：
  - generic multi-agent example 移到 `examples/agents/` 或删除。
  - Slack E2E agent sample 移到 `tests/e2e/slack_scenarios/` 或测试 fixtures，并更新 README。
- 将 standalone Knowledge Service 示例从 `config/knowledge-service/` 移到 `examples/knowledge-service/`，并更新 docs/spec/tests 引用。
- 更新配置模板检查，确保 active `config/` 不再出现 `agents/` 或 `knowledge-service/`。

## Capabilities

### Modified Capabilities

- `configuration`: active `config/` 目录只承载 canonical Platform / Agent 模板；非 canonical 示例迁移到 examples/fixtures。
- `knowledge-service-config`: standalone Knowledge Service 的示例模板不在 active `config/` 下，而在 examples 目录。
- `slack-e2e-test-suite`: Slack E2E sample agent 路径迁移到 E2E scenario/fixture 目录。

## Module Boundary Impact

- **owning package**：无 runtime package owner 变更；配置样例归部署/测试文档边界。
- **public API surface**：无。
- **owned tables**：无。
- **config namespace**：`config/` active namespace 收敛为 `agent/` 与 `platform/`；standalone service 和测试样例进入 `examples/` / `tests/`。
- **cross-module dependencies**：无 runtime dependency 变更。
- **migration / shim plan**：MVP 未上线，不保留旧 example 路径 shim；文档和测试同步改路径。
