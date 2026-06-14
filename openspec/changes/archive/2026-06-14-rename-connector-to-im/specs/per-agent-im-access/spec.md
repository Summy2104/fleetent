# per-agent-im-access Delta

> 代表性 delta（OpenSpec 要求 ≥1）。纯改名、零行为。其余 6 个相关 spec（per-agent-slack/telegram-connector、file-agent-runtime、im-connector-config/registry、im-gateway）的同类命名同步在 apply 时与代码改名同一次 find-replace 完成（tasks 3.1），再 archive 同步 canonical。

## MODIFIED Requirements

### Requirement: Per-agent IM access config in the agent home
An agent SHALL carry its IM access rules inside its **`im`** binding declarations, not in a top-level `access` block. Each binding (**`im.slack`**, **`im.telegram`**) SHALL embed an **`access: ImAccess`** object with **`allow_groups`** (list), `allow_users` (list), and `require_approval` (bool); IM 能力 `supports_dm`/`supports_groups` 在顶层 `im` 上。The runtime SHALL resolve access policy by reading the binding that matches `msg.platform`, with zero platform-DB access. The top-level `AgentFile.access` field and `AgentAccess` class remain removed. （纯改名：`connectors`→`im`、`ConnectorAccess`→`ImAccess`、`allow_channels`→`allow_groups`；行为与阶段 3 完全一致。）

#### Scenario: Access rules loaded from the binding's access block
- **WHEN** an agent home declares `im.slack.access.allow_users: ["u_alice"]` and the agent loads
- **THEN** the resolved agent exposes that allow rule under `im.slack.access` for runtime evaluation, with no platform-DB read

#### Scenario: Absent access block defaults to closed-with-approval
- **WHEN** an agent home declares `im.slack` with no `access` sub-block
- **THEN** the agent applies a safe default (`ImAccess()`: no implicit allow, approval required) for Slack messages

#### Scenario: Slack and Telegram can have independent access policies
- **WHEN** an agent declares `im.slack.access.allow_all_users: false` and `im.telegram.access.require_approval: false`
- **THEN** the runtime enforces the Slack policy for Slack messages and the Telegram policy for Telegram messages independently

#### Scenario: 群白名单字段为 allow_groups
- **WHEN** an agent declares `im.slack.access.allow_groups: ["C1"]`
- **THEN** 群准入按该 `allow_groups` 列表判定（语义同阶段 3 的群白名单，仅字段名由 `allow_channels` 改为 `allow_groups`）
