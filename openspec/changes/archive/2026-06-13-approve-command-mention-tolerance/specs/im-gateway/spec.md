## MODIFIED Requirements

### Requirement: Slack approval interactivity

The Slack adapter SHALL render permission-gate approval prompts as Block Kit messages
with three interactive buttons — approve, reject, and approve-always — each carrying the
approval id in its action value. The adapter SHALL register a Socket Mode `block_actions`
handler that maps the clicked action to a gate decision, passing the **clicking user's
Slack id** (from the interaction payload) as the decision actor so the gate's
authorization check applies. On an accepted decision the adapter SHALL update the
original prompt message to a result state with the buttons removed; on a rejected
decision (unauthorized actor or expired approval) it SHALL show the clicker an
ephemeral notice and leave the prompt intact. The `approve <id>` / `reject <id>` text
commands SHALL keep working on all platforms. **In a channel the bot must be @-mentioned
to be addressed, so the adapter SHALL recognize the `approve`/`reject <id>` text command
even when the message is prefixed with a leading bot mention, by stripping a single
leading `<@id>` (optionally `<@id|label>`) before matching; the id format check is
unchanged, so ordinary prose that merely @-mentions the bot is not misread as approval.**

#### Scenario: approval prompt renders buttons

- **WHEN** the permission gate sends an approval prompt through a Slack reply or a Slack
  outbound DM
- **THEN** the message carries Block Kit actions `approval_approve`, `approval_reject`,
  and `approval_approve_always` with the approval id as their value

#### Scenario: authorized click resolves and updates the message

- **WHEN** an authorized actor clicks 批准 (approve) on the prompt
- **THEN** the gate resolves the approval with the clicker's Slack id and the original
  message is updated to a result state without buttons

#### Scenario: approve-always click grants the allow-always fingerprint

- **WHEN** an authorized actor clicks 始终允许 (approve always)
- **THEN** the gate resolves with `always=True`, persisting the allow-always grant

#### Scenario: unauthorized click is rejected with an ephemeral notice

- **WHEN** a user who is not an authorized decision actor clicks any approval button
- **THEN** the approval stays pending, the prompt keeps its buttons, and the clicker
  receives an ephemeral notice

#### Scenario: text command fallback unaffected

- **WHEN** a user replies `approve <id>` instead of clicking
- **THEN** the decision flows through the existing text-command path unchanged

#### Scenario: platforms without blocks degrade to text

- **WHEN** the approval prompt is delivered via a reply channel that does not accept a
  `blocks` argument (e.g. Telegram, TUI)
- **THEN** the plain-text prompt with the `approve <id>` / `reject <id>` instructions is
  sent instead

#### Scenario: channel approve with a leading bot mention resolves

- **WHEN** a user in a channel replies `<@bot> approve <id>` (the bot must be @-mentioned
  to receive the message)
- **THEN** the adapter strips the single leading mention, recognizes the `approve <id>`
  text command, and resolves the approval — instead of treating it as a new agent turn

#### Scenario: prose that mentions the bot is not misread as approval

- **WHEN** a user sends `<@bot> approve the plan` (no valid approval id)
- **THEN** the leading mention is stripped but the id-format check fails, so the message
  is handled as a normal agent turn, not an approval decision
