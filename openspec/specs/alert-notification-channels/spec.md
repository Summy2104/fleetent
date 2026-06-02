# alert-notification-channels Specification

## Purpose
TBD - created by archiving change 2026-06-02-resource-monitoring-alerting. Update Purpose after archive.
## Requirements
### Requirement: Per-rule multi-channel notification
Each alert rule SHALL be able to target one or more notification channels: email (self-hosted SMTP), IM push (reusing im-gateway to push to Slack/Telegram/WhatsApp admins), Webhook (POST to an external alerting/on-call system), and in-app (alert center plus a banner at the top of the health dashboard). Channel credentials (SMTP password, Webhook secret, IM token) SHALL never be echoed in plaintext in any view or audit entry.

#### Scenario: Multiple channels notified on trigger
- **WHEN** a rule configured with email and in-app channels triggers
- **THEN** the email channel and the in-app alert center each receive a notification for the alert

#### Scenario: IM push reuses im-gateway
- **WHEN** a rule with an IM channel triggers
- **THEN** the alert message is delivered to the configured admins via im-gateway's Slack/Telegram/WhatsApp push, and this face does not reimplement IM delivery

#### Scenario: Channel credentials masked
- **WHEN** an admin or viewer browses channel configuration that references an SMTP password, Webhook secret, or IM token
- **THEN** those credentials are masked in every view and no audit entry echoes them in plaintext

### Requirement: Webhook outbound to external systems
When a rule with a Webhook channel triggers, the platform SHALL POST the alert content to the configured Webhook URL. Webhook is the only channel that initiates outbound network traffic and SHALL exist only when an admin explicitly configures it.

#### Scenario: Webhook posted to external on-call system (场景 94)
- **WHEN** a rule configured with a Webhook channel pointing to an external on-call system triggers
- **THEN** the platform POSTs the alert content to that Webhook URL

### Requirement: Send failure retry and failure record
Every channel send SHALL record its result. A failed send SHALL be retried a bounded number of times with backoff, and a final failure SHALL be recorded and made visible in the UI. Retries SHALL NOT block the evaluation loop.

#### Scenario: Webhook failure is retried and recorded (场景 94)
- **WHEN** a Webhook POST fails
- **THEN** the send is retried with backoff a bounded number of times, and a final failure is recorded as a notification failure visible in the alert's handling record

#### Scenario: Retry does not block evaluation
- **WHEN** a channel send is retrying
- **THEN** the alert evaluation loop continues to run other rules and is not blocked by the pending retries

