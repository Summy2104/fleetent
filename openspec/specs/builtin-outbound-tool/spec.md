# builtin-outbound-tool Specification

## Purpose
agent 主动 IM 外发能力：`send_im_message` 内置工具把 `outbound` 原语暴露给 agent，
经 medium 审批门治理，使 agent 能在对话之外主动给指定用户发 DM 或向频道发消息。
## Requirements
### Requirement: send_im_message tool sends via injected connectors

The builtin tool `send_im_message(target, text, target_type, platform, files)` SHALL send
*text* — and, when the optional `files` parameter lists namespace paths, file attachments —
to *target* through the live IM connectors injected via `ToolContext.outbound_connectors`,
using the same shared delivery core as `send_file` (`outbound.send_to` / `outbound.send_file_to`).
`target_type` selects a user DM (`user`, default) or a channel post (`channel`). An empty
`platform` SHALL default to the current conversation's platform from the session context.

Each `files` entry MUST be resolved within the dual-root namespace (workspace-relative or
`/exchange/...`); because every `send_im_message` call passes the medium permission gate,
an approved call constitutes cross-session authorization for `/exchange` artifacts owned by
other sessions. Paths outside the namespace MUST be refused per-file with an explanatory
text, without aborting delivery of the remaining valid entries.

The tool SHALL be registered with `risk_level="medium"` so every call passes the permission
gate — this invariant MUST hold regardless of arguments (the audit guarantee that proactive
outreach is always human-gated). The tool SHALL never raise — unreachable targets, missing
connectors, per-file resolution failures, and send failures each return an explanatory text
result.

#### Scenario: DM sent to a third-party user

- **WHEN** the agent calls `send_im_message(target="U_OTHER", text="hi")` in a Slack
  conversation and the call is approved
- **THEN** the message is delivered via the Slack connector as a DM to `U_OTHER` and
  the tool returns a success text naming the target

#### Scenario: assistant-pane DM path injects connectors

- **WHEN** the agent calls `send_im_message` from a Slack Assistant-pane conversation
  (the `_route_assistant_message` inbound path)
- **THEN** the Slack connector is available via `ToolContext.outbound_connectors`,
  identical to the channel/plain-DM inbound path

#### Scenario: channel post

- **WHEN** the agent calls `send_im_message(target="C_NOTICE", text="...", target_type="channel")`
  and the call is approved
- **THEN** the message is posted to the channel via `outbound.send_to`

#### Scenario: platform defaults to the current conversation

- **WHEN** `platform` is omitted in a Slack conversation
- **THEN** the Slack connector is used

#### Scenario: file attachment delivered after approval

- **WHEN** the agent calls `send_im_message(target="U_OTHER", text="report", files=["/exchange/srv/report.xlsx"])`
  and the call is approved
- **THEN** the artifact resolves through the namespace and is delivered to `U_OTHER` as a
  file attachment alongside the text

#### Scenario: cross-session artifact authorized by approval

- **WHEN** the agent calls `send_im_message` with a `files` entry owned by another session
  and the human approves the call
- **THEN** the file is delivered — the approval itself is the cross-session authorization

#### Scenario: invalid file entry degrades per-file

- **WHEN** `files` contains one valid workspace path and one path outside the namespace
- **THEN** the valid file is delivered, the invalid entry is reported in the result text,
  and no exception is raised

#### Scenario: medium gate invariant holds with files

- **WHEN** the agent calls `send_im_message` with any combination of `files`/`target`
- **THEN** the call passes the medium permission gate before any delivery

