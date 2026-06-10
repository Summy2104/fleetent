# permission-gate Delta

## ADDED Requirements

### Requirement: Approval prompts carry interactive actions where supported

Approval prompts SHALL include platform-rendered interactive actions (approve / reject /
approve-always) on delivery channels that support them, while always retaining the
text-command instructions as a universal fallback. The gate SHALL pass the interactive
payload opaquely (it does not know platform rendering details) and SHALL degrade to the
plain-text prompt when the delivery channel rejects the payload.

#### Scenario: requester prompt carries actions on a supporting channel

- **WHEN** a requester-routed approval prompt is delivered through a reply channel that
  accepts an interactive payload
- **THEN** the prompt message includes the interactive actions alongside the text
  instructions

#### Scenario: outbound approver DM carries actions

- **WHEN** an outbound approver is contacted on a platform supporting interactive
  payloads (Slack)
- **THEN** the DM includes the interactive actions alongside the text instructions

#### Scenario: non-supporting channel falls back to text

- **WHEN** the delivery channel rejects the interactive payload (TypeError on the extra
  argument)
- **THEN** the gate re-sends the plain-text prompt and the approval flow continues
  unaffected
