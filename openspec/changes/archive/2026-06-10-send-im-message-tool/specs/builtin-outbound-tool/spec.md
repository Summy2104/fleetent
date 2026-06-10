# builtin-outbound-tool Delta

## ADDED Requirements

### Requirement: send_im_message tool sends via injected connectors

The builtin tool `send_im_message(target, text, target_type, platform)` SHALL send
*text* to *target* through the live IM connectors injected via
`ToolContext.outbound_connectors`, using `outbound.send_to`. `target_type` selects a
user DM (`user`, default) or a channel post (`channel`). An empty `platform` SHALL
default to the current conversation's platform from the session context. The tool
SHALL be registered with `risk_level="medium"` so every call passes the permission
gate, and SHALL never raise — unreachable targets, missing connectors, and send
failures each return an explanatory text result.

#### Scenario: DM sent to a third-party user

- **WHEN** the agent calls `send_im_message(target="U_OTHER", text="hi")` in a Slack
  conversation and the call is approved
- **THEN** the message is delivered via the Slack connector as a DM to `U_OTHER` and
  the tool returns a success text naming the target

#### Scenario: channel post

- **WHEN** the agent calls `send_im_message(target="C_NOTICE", text="...", target_type="channel")`
  and the call is approved
- **THEN** the message is posted to the channel via `outbound.send_to`

#### Scenario: platform defaults to the current conversation

- **WHEN** `platform` is omitted in a Slack conversation
- **THEN** the Slack connector is used

#### Scenario: medium risk gates every call

- **WHEN** the agent plans a `send_im_message` call and the permission gate is enabled
- **THEN** the call requires approval per the agent's `action_gate_medium_mode` and
  `approval_routing` configuration before executing

#### Scenario: missing connector returns an explanatory result

- **WHEN** the tool runs in a context without IM connectors (e.g. the TUI/HTTP path)
- **THEN** it returns a text explaining that proactive IM sending is unavailable in
  this channel, without raising

#### Scenario: unreachable target returns an explanatory result

- **WHEN** `is_reachable` reports the target unreachable (e.g. a Telegram user who
  never started the bot)
- **THEN** the tool returns a text explaining the target cannot be reached, without
  sending
