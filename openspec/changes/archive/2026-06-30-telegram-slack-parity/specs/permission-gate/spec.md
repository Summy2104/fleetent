## MODIFIED Requirements

### Requirement: Approval prompts carry interactive actions where supported

Approval prompts SHALL include platform-rendered interactive actions (approve / reject /
approve-always) on delivery channels that support them, while always retaining the
text-command instructions as a universal fallback. The gate SHALL pass the interactive
payload opaquely (it does not know platform rendering details) and SHALL degrade to the
plain-text prompt when the delivery channel rejects the payload. The gate MUST NOT import
or construct any platform-specific rendering (e.g. Slack Block Kit); rendering SHALL happen
at the outbound delivery boundary, dispatched by platform (Slack → Block Kit; Telegram →
inline keyboard), so that adding a delivery platform never changes the gate. Telegram SHALL
be a supporting channel: its approval prompts carry an inline keyboard whose buttons encode
the `approval_id` and the decision.

Approval prompts SHALL additionally carry a human-readable summary of the gated call so the
approver can verify WHAT is being approved before deciding — in both the interactive payload
and the text fallback. For `send_im_message` the summary SHALL identify the recipient,
resolving the platform-native target id to a display label best-effort via the injected IM
connector (Slack `users.info` → `@<name>`, `conversations.info` → `#<name>`), falling back to
the raw id on any failure or timeout so the prompt is never blocked or delayed; it SHALL also
state the target type (DM vs channel), a short preview of the message text, and the attachment
count when files are attached. For other gated tools the summary SHALL be a compact,
secret-masked rendering of the call arguments. Summary construction MUST NOT raise and MUST
NOT depend on `fleetent.platform`.

#### Scenario: requester prompt carries actions on a supporting channel

- **WHEN** a requester-routed approval prompt is delivered through a reply channel that
  accepts an interactive payload
- **THEN** the prompt message includes the interactive actions alongside the text
  instructions

#### Scenario: outbound approver DM carries actions

- **WHEN** an outbound approver is contacted on a platform supporting interactive
  payloads
- **THEN** the approver DM includes the interactive actions alongside the text instructions

#### Scenario: gate passes a neutral intent rendered at the boundary

- **WHEN** the gate builds an approval prompt
- **THEN** it produces a platform-neutral interactive intent (approval id + action set +
  summary) without importing or constructing Slack Block Kit, and the outbound boundary
  renders it per platform (Slack Block Kit unchanged; Telegram inline keyboard)

#### Scenario: Telegram approval prompt carries an inline keyboard

- **WHEN** an approval prompt is delivered to a Telegram approver
- **THEN** the message carries an inline keyboard with approve / reject / approve-always
  buttons whose callback data encodes the approval id and decision, alongside the text
  fallback

#### Scenario: send_im_message prompt shows the resolved recipient

- **WHEN** a `send_im_message(target="U_OTHER", text="...", target_type="user")` call is gated
  and the approval prompt is built with a reachable Slack connector
- **THEN** the prompt (interactive and text) shows the recipient resolved to a display label
  (e.g. `@张三`), the target type (私信), and a preview of the message text

#### Scenario: recipient resolution failure degrades to raw id

- **WHEN** the recipient display name cannot be resolved (API error/timeout or non-Slack platform)
- **THEN** the prompt shows the raw target id instead, and the prompt is still delivered
  (resolution failure never blocks or delays the approval prompt)
