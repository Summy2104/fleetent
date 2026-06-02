## ADDED Requirements

### Requirement: Three-tier roles
Users SHALL have a `role` of `built_in_admin`, `admin`, or `viewer`. `/admin/*` access SHALL require `role` in {`admin`, `built_in_admin`}; write operations SHALL be denied to `viewer`. This `role` replaces the boolean `is_admin`; for compatibility `is_admin` is true iff `role` is in {`admin`, `built_in_admin`}.

#### Scenario: Viewer blocked from write
- **WHEN** a `viewer` calls a write endpoint under `/admin`
- **THEN** the response is 403 and no change is persisted

#### Scenario: Admin allowed
- **WHEN** an `admin` calls `GET /admin/users`
- **THEN** the response is 200

### Requirement: Built-in admin seeding
On first startup with no admin present, the system SHALL seed a built-in admin with a fixed username, a generated temporary password written to the startup log, `must_reset=1`, and `role=built_in_admin`.

#### Scenario: Seed on first boot
- **WHEN** the server starts and no built-in admin exists
- **THEN** a `built_in_admin` user is created with `must_reset=1` and the initial password is written to the startup log

#### Scenario: Idempotent seed
- **WHEN** the server starts and a built-in admin already exists
- **THEN** no new admin is created and no password is logged

### Requirement: Forced password reset on first login
A user with `must_reset=1` SHALL be forced to change the password before accessing any other page.

#### Scenario: Must-reset gate
- **WHEN** the built-in admin logs in with the initial password and `must_reset=1`
- **THEN** access to any page other than the change-password flow is rejected until the password is changed, after which `must_reset` is cleared

### Requirement: Built-in admin is protected
The built-in admin SHALL NOT be deletable, renamable, or demotable by anyone; only the built-in admin may change its own password.

#### Scenario: Delete/demote built-in admin rejected
- **WHEN** any user (including another admin) attempts to delete, rename, or demote the built-in admin
- **THEN** the operation is rejected and nothing is persisted

#### Scenario: Regular admin cannot block built-in admin
- **WHEN** a non-built-in admin attempts to block or demote the built-in admin
- **THEN** the operation returns 403 and nothing is persisted

### Requirement: Email/password login with idle timeout
The system SHALL authenticate admins via email + password, issuing a server-side login session distinct from the `/chat` Bearer API key, and SHALL log out sessions after an idle timeout.

#### Scenario: Login issues a session
- **WHEN** a user submits a correct email/password
- **THEN** a login session is established

#### Scenario: Idle timeout logs out
- **WHEN** a login session is idle beyond the configured timeout
- **THEN** the next request requires re-authentication

### Requirement: 2FA for high-risk operations
High-risk operations (delete user, block, change role, revoke key) SHALL require a passing 2FA (TOTP) check for the current action.

#### Scenario: High-risk without 2FA blocked
- **WHEN** an admin attempts to delete a user without passing 2FA
- **THEN** the operation is rejected pending 2FA; once verified it proceeds and is audited

### Requirement: No public self-registration
The system SHALL NOT expose a public self-registration endpoint.

#### Scenario: Register path absent
- **WHEN** a visitor requests `/register`
- **THEN** the response is 404 or an explicit "contact your administrator" message, with no way to self-create an account
