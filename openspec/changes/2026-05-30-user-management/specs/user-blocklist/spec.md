## ADDED Requirements

### Requirement: One-click cascade block
Blocking a user (reason required) SHALL set `status=blocked`, revoke all the user's API keys, disable all associated IM accounts, add the email (and OAuth subject if any) to a no-registration list, and write an audit entry.

#### Scenario: Cascade takes effect
- **WHEN** an admin blocks a user holding 2 keys and bound Slack + Telegram, with a reason
- **THEN** both keys are revoked, both IM accounts are disabled, the email is added to the no-registration list, and an audit entry is written

#### Scenario: Blocked key rejected
- **WHEN** a key of a blocked user is used on `/chat`
- **THEN** the response is 401

#### Scenario: Re-registration blocked
- **WHEN** an account creation uses an email on the no-registration list
- **THEN** the operation is rejected

### Requirement: Unblock does not revive keys
Unblocking SHALL restore login but SHALL NOT auto-restore previously revoked keys; IM accounts require re-approval.

#### Scenario: Unblock restores login only
- **WHEN** an admin unblocks a user
- **THEN** `status` becomes `active`, previously revoked keys stay invalid, and IM accounts must be re-approved

### Requirement: Batch block
The system SHALL support batch-blocking by email domain, IP, or registration time window, auditing each with a shared batch id.

#### Scenario: Batch by email domain
- **WHEN** an admin batch-blocks `email domain = evil.com`
- **THEN** all matching accounts are blocked and recorded with one shared batch id in the audit log
