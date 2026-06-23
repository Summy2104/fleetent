## MODIFIED Requirements

### Requirement: send_im_message tool sends via injected connectors

The builtin tool `send_im_message(target, text, target_type, platform, files)` SHALL send
*text* — and, when the optional `files` parameter lists namespace paths, file attachments —
to *target* through the live IM connectors injected via `ToolContext.outbound_connectors`,
using the same shared delivery core as `send_file` (`outbound.send_to` / `outbound.send_file_to`).
`target_type` selects a user DM (`user`, default) or a channel post (`channel`). An empty
`platform` SHALL default to the current conversation's platform from the session context.

Each `files` entry MUST be resolved within the dual-root namespace (workspace-relative or
`/exchange/...`); when the call is approval-gated (target is a third party), an approved call
constitutes cross-session authorization for `/exchange` artifacts owned by other sessions.
Paths outside the namespace MUST be refused per-file with an explanatory text, without
aborting delivery of the remaining valid entries.

The tool's risk level SHALL be determined at call time by `approval_policy.risk_for` on the
**recipient-identity axis**: when `(target, target_type)` resolves to the current conversation
address (the same DM user or the same channel as the inbound message), the call SHALL be
`none`; when it targets a different user or a different channel, the call SHALL be `medium`
(proactive outreach to someone other than the current conversation participant is human-gated).
When the current conversation address cannot be resolved, the call MUST fail closed to `medium`.
The tool SHALL never raise — unreachable targets, missing connectors, per-file resolution
failures, and send failures each return an explanatory text result.

**No self-delivery to the current conversation.** When `(target, target_type)` resolves to the
current conversation address (i.e. `approval_policy.risk_for` is `none` because the target is
the current-conversation DM user or the current channel), the tool SHALL NOT deliver anything —
it SHALL return a no-op text result instructing the model that replying to the current
conversation is done by emitting plain text (which the harness delivers automatically), and that
`send_im_message` is only for proactive outreach to other users/channels. This prevents the
duplicate where the model both calls `send_im_message` for the current conversation and emits a
final reply (both of which would otherwise be delivered). This supersedes any prior
"channel self-DM pinning" behavior: a self-DM to the current-conversation sender is a no-op, not
a channel-pinned delivery.

The tool's documented purpose SHALL describe it as **proactive outreach to other users or
other channels** — replying to the current conversation is done with `send_file` (for files)
or a plain text reply — so the model is not steered to route "send it to me" through this tool.

#### Scenario: DM to a third-party user is gated

- **WHEN** the agent calls `send_im_message(target="U_OTHER", text="hi")` in a Slack
  conversation whose sender is not `U_OTHER`, and the call is approved
- **THEN** the message is delivered via the Slack connector as a DM to `U_OTHER` and
  the tool returns a success text naming the target

#### Scenario: Send to the current conversation is a no-op

- **WHEN** the agent calls `send_im_message` whose `(target, target_type)` resolves to the
  current conversation address (the same DM user, or the same channel as the inbound message)
- **THEN** `approval_policy.risk_for` returns `none`, the tool does NOT call the connector
  (nothing is delivered), and it returns a no-op text telling the model to reply with plain
  text instead — so the current-conversation reply is delivered once (by the harness), not twice

#### Scenario: post to a different channel is gated

- **WHEN** the agent calls `send_im_message(target="C_NOTICE", text="...", target_type="channel")`
  where `C_NOTICE` is not the current channel, and the call is approved
- **THEN** the message is posted to the channel via `outbound.send_to`

#### Scenario: self-DM from a channel is not delivered

- **WHEN** the inbound conversation is a Slack **channel** (`chat_type == "channel"`) whose
  sender is `U_SELF`, and the agent calls
  `send_im_message(target="U_SELF", text="here", target_type="user", files=["report.png"])`
- **THEN** the tool no-ops (no channel-pinned delivery): neither the text nor the file is sent,
  and it returns the plain-text-reply guidance, because the target is the current-conversation
  participant

#### Scenario: self-DM from a DM conversation is a no-op

- **WHEN** the inbound conversation is itself a DM with `U_SELF` (`chat_type != "channel"`) and
  the agent calls `send_im_message(target="U_SELF", text="here", target_type="user")`
- **THEN** the tool no-ops (the target is the current conversation) and returns the
  plain-text-reply guidance

#### Scenario: third-party DM from a channel is not affected

- **WHEN** the inbound conversation is a channel and the agent calls
  `send_im_message(target="U_OTHER", text="hi", target_type="user")` where `U_OTHER` is not
  the sender
- **THEN** the call is `medium` (gated), and after approval the message is delivered to
  `U_OTHER`'s DM

#### Scenario: assistant-pane DM path injects connectors

- **WHEN** the agent calls `send_im_message` from a Slack Assistant-pane conversation
  (the `_route_assistant_message` inbound path)
- **THEN** the Slack connector is available via `ToolContext.outbound_connectors`,
  identical to the channel/plain-DM inbound path

#### Scenario: platform defaults to the current conversation

- **WHEN** `platform` is omitted in a Slack conversation
- **THEN** the Slack connector is used

#### Scenario: file attachment to a third party delivered after approval

- **WHEN** the agent calls `send_im_message(target="U_OTHER", text="report", files=["/exchange/srv/report.xlsx"])`
  where `U_OTHER` is not the current conversation participant, and the call is approved
- **THEN** the artifact resolves through the namespace and is delivered to `U_OTHER` as a
  file attachment alongside the text

#### Scenario: cross-session artifact authorized by approval

- **WHEN** the agent calls `send_im_message` to a third party with a `files` entry owned by
  another session and the human approves the call
- **THEN** the file is delivered — the approval itself is the cross-session authorization

#### Scenario: invalid file entry degrades per-file

- **WHEN** `files` contains one valid workspace path and one path outside the namespace
- **THEN** the valid file is delivered, the invalid entry is reported in the result text,
  and no exception is raised

#### Scenario: fail-closed when the current address is unresolvable

- **WHEN** the agent calls `send_im_message` but the current conversation address cannot be
  resolved from the session context
- **THEN** `approval_policy.risk_for` returns `medium` and the call passes the permission gate
  before any delivery
