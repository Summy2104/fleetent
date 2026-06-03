## ADDED Requirements

### Requirement: Admin creates users manually
An admin SHALL create a user by email + name with either an initial password or a "set password on first login" flag; the account is usable immediately.

#### Scenario: Manual create
- **WHEN** an admin submits email, name, and an initial password
- **THEN** the account is created `status=active` and can be used; a notification email is sent

#### Scenario: Create with first-login reset
- **WHEN** an admin creates a user with "set password on first login"
- **THEN** the account has `must_reset=1` and the user must set a password at first login

#### Scenario: Duplicate email rejected
- **WHEN** an admin creates a user whose email already exists
- **THEN** the operation is rejected and nothing is persisted

### Requirement: One-time invite links
An admin SHALL generate a one-time invite link for an email; the user sets a password to activate; the token expires after use or timeout.

#### Scenario: Invite then activate
- **WHEN** an admin generates an invite for an email
- **AND** the user opens the link within the validity window and sets a password
- **THEN** the account is activated, the first API key is issued, and the invite token is invalidated

#### Scenario: Reused/expired invite
- **WHEN** an already-used or expired invite link is opened
- **THEN** the response is "invite invalid" and no account is created

### Requirement: CSV bulk import
An admin SHALL bulk-import users from a CSV; rows that fail are reported without aborting the batch.

#### Scenario: Bulk import with partial failures
- **WHEN** an admin uploads a CSV where some rows are valid and some duplicate existing emails
- **THEN** valid rows create accounts and failed rows are reported in a summary

### Requirement: User list and lifecycle
The system SHALL list users filterable/sortable by status, last-active, and bound IM count, and SHALL support editing, disabling, and deleting a user.

#### Scenario: Filtered list
- **WHEN** an admin lists users filtered to `status=active`
- **THEN** only active users are returned, sortable by last-active and bound IM count

#### Scenario: Disable user
- **WHEN** an admin disables a user
- **THEN** the user's `status` becomes `disabled` and they cannot log in, while data is retained
