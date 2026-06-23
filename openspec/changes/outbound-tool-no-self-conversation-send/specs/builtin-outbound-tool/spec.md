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

Delivery to a third party (target ≠ current conversation) is unchanged: it is `medium`-gated,
delivers via the connector, and an approved call authorizes cross-scope `/exchange` artifacts.

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

#### Scenario: Self-DM from a channel is not delivered

- **WHEN** the inbound conversation is a channel and the agent calls
  `send_im_message(target=<current sender>, target_type="user")`
- **THEN** the tool no-ops (no channel-pinned delivery) and returns the plain-text-reply
  guidance, because the target is the current conversation participant
