## ADDED Requirements

### Requirement: Materialize 时 scaffold agent .env / TUI token

`fleetent node start` 在 reconcile 把某个期望 agent 的 home materialize（写 `agent.yaml`）时，SHALL 同时确保该 agent home 存在 `.env` 且含一个有效的 `FLEETENT_TUI_TOKEN`（`ma-<64 hex>` 形态）。该 scaffold SHALL 幂等：

- 当 home 无 `.env`（或 `.env` 缺 `FLEETENT_TUI_TOKEN`）时，SHALL 生成一个新的 `FLEETENT_TUI_TOKEN` 写入 `.env`；
- 当 `.env` 已含 `FLEETENT_TUI_TOKEN` 时，SHALL 原样保留，MUST NOT 覆盖文件或轮换已有 token（避免使在跑 agent 的既有 token 失效）。

该 token 是 forwarder（`/forward/agents/{name}/chat`）与 IM-edge 注入 agent loopback `/chat` 的 `Authorization: Bearer` 凭据；scaffold 后，新 pin 到该 node 的 managed agent SHALL 无需任何手工补 `.env` 即可经 forwarder/IM-edge 对话。scaffold 行为 SHALL NOT 写入任何真实 secret（model api key、IM token 等），这些经 node secret 注入走进程环境。

#### Scenario: 新 materialize 的 agent 自动获得 TUI token

- **WHEN** node reconcile materialize 一个 home 此前不存在 `.env` 的期望 agent
- **THEN** 该 home 出现 `.env` 且含一个 `ma-<64 hex>` 形态的 `FLEETENT_TUI_TOKEN`
- **AND** 经 forwarder `/forward/agents/{name}/chat` 触达该 agent 不再返回 503 `has no env scaffold`

#### Scenario: 已存在的 .env 与 token 被保留

- **WHEN** node reconcile materialize 一个 home 已存在含 `FLEETENT_TUI_TOKEN=ma-...` 的 `.env` 的 agent
- **THEN** 该 `.env` 内容（含原 `FLEETENT_TUI_TOKEN` 值）保持不变
- **AND** node MUST NOT 因 materialize 而轮换或清空该 token

#### Scenario: scaffold 不落真实 secret

- **WHEN** node 为某 agent 生成 `.env` scaffold
- **THEN** 写入的 `.env` 仅含 `FLEETENT_TUI_TOKEN`（及 agent 配置引用的 env 变量名占位、值为空）
- **AND** model api key / IM token 等真实 secret MUST NOT 出现在该 `.env` 中（它们经 node secret 注入走进程环境）
