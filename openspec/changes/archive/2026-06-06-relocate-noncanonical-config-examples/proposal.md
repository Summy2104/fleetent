## Why

`config/` 目录现在仍同时承载 active deployment templates 与非 canonical 示例：

- `config/agents/*/agent.yaml.example` 是 legacy/dev multi-agent scan 示例和 Slack E2E 测试样例；它与 canonical `config/agent/agent.yaml.example` 只有单复数差异，容易被误解为部署入口。
- `config/knowledge-service/*` 是未来 standalone Knowledge Service 的示例模板；当前 MVP 阶段 Knowledge 与 Platform 一起部署，不应提前提供独立 service config，避免 operator 误以为这是当前支持的部署形态。

上一轮配置治理已经确立 `config/` 的一等边界是 Platform / Agent。为了降低路径歧义，当前阶段只保留 active 配置模板和必要测试 fixture；尚未支持的独立服务示例不提前落地。

## What Changes

- `config/` 下只保留 active canonical 模板目录：
  - `config/platform/`
  - `config/agent/`
- 删除或迁移 `config/agents/*`：
  - generic multi-agent example 删除，避免与 canonical `config/agent/` 重复。
  - Slack E2E agent sample 移到 `tests/e2e/slack_scenarios/` 或测试 fixtures，并更新 README。
- 删除 `config/knowledge-service/` standalone 示例；不新增 `examples/knowledge-service/`，未来真的支持独立 Knowledge Service 时再单独引入。
- 更新配置模板检查，确保 active `config/` 不再出现 `agents/` 或 `knowledge-service/`。

## Capabilities

### Modified Capabilities

- `configuration`: active `config/` 目录只承载 canonical Platform / Agent 模板；测试样例迁移到 fixtures，未支持的独立服务示例不落地。
- `knowledge-service-config`: 当前 MVP 不提供 standalone Knowledge Service 示例模板；未来由独立变更引入。
- `slack-e2e-test-suite`: Slack E2E sample agent 路径迁移到 E2E scenario/fixture 目录。

## Module Boundary Impact

- **owning package**：无 runtime package owner 变更；配置样例归部署/测试文档边界。
- **public API surface**：无。
- **owned tables**：无。
- **config namespace**：`config/` active namespace 收敛为 `agent/` 与 `platform/`；测试样例进入 `tests/`，standalone Knowledge Service 示例延后。
- **cross-module dependencies**：无 runtime dependency 变更。
- **migration / shim plan**：MVP 未上线，不保留旧 example 路径 shim；文档和测试同步改路径。
