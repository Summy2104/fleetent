## MODIFIED Requirements

### Requirement: Map platform user to internal user
The system SHALL map `(platform, platform_user_id)` to an internal `user_id` before routing to the agent pipeline **when an identity resolver has been injected**. In managed deployments the platform injects the resolver at startup via `im_gateway.access.set_im_identity_resolver`; the resolver is platform-owned and may write platform identity tables, while the agent module MUST NOT know its implementation or schema. Without resolver injection (standalone), `resolve_identity` SHALL return the native `platform_user_id` unchanged.

On first contact provisioning SHALL go through an **email-keyed resolution** (`resolve_or_provision`) when a **verified email** is available for the channel identity: it SHALL look up an existing user by `(edge_tenant, normalized_email)` and, if found, **link** the channel identity to that existing user (write the `im_users` mapping); if not found, create a new email-keyed user in the edge tenant and link it. When **no verified email** is available, provisioning SHALL fall back to creating a channel-keyed user in the **connector edge tenant** (`create_user(tenant_id=edge_tenant)`, edge_tenant = the receiving bot's `agent.tenant_id`).

Linking SHALL be **attach-only, never merge**: it only attaches a channel identity that has **no existing user mapping** to an email-keyed user. The system MUST NOT auto-merge two already-existing internal users (e.g., a channel identity already mapped to user A whose verified email matches user B) — such cases are left to manual/admin resolution.

#### Scenario: Known user (managed)
- **WHEN** a Slack message arrives from `platform_user_id=U123` (already in `im_users`) and the resolver is injected
- **THEN** the resolver returns the corresponding internal `user_id`, used as `Principal.user_id`

#### Scenario: Unknown user, verified email links to existing user (managed)
- **WHEN** a message arrives from a `platform_user_id` not in `im_users`, a verified email is available, and a user with that `(edge_tenant, normalized_email)` already exists
- **THEN** the channel identity is **linked** to that existing user (new `im_users` row → existing `user_id`); no new user is created

#### Scenario: Unknown user, verified email, no existing user (managed)
- **WHEN** a message arrives from an unmapped `platform_user_id` with a verified email and no matching user exists
- **THEN** a new email-keyed user is created in the edge tenant and the channel identity is mapped to it

#### Scenario: Unknown user, no verified email (managed)
- **WHEN** a message arrives from an unmapped `platform_user_id` and no verified email is available
- **THEN** a new channel-keyed user is created in the edge tenant and mapped (current behavior; cross-channel unification deferred to manual `/link`)

#### Scenario: No auto-merge of pre-existing users
- **WHEN** a channel identity already mapped to user A presents a verified email matching a different existing user B
- **THEN** the system MUST NOT merge A and B automatically; the existing mapping is unchanged and the case is surfaced for manual resolution

#### Scenario: Same person converges across IM and bearer (managed)
- **WHEN** the same human first talks over IM and later calls with that mapped user's bearer key (or reverse)
- **THEN** both paths resolve to the same `Principal.user_id`; agent-side memory/session converge

#### Scenario: Standalone passthrough
- **WHEN** an IM message arrives with no resolver injected
- **THEN** `resolve_identity` returns the native `platform_user_id`, no platform table read

#### Scenario: Blocked user rejected (managed)
- **WHEN** the resolver maps a channel identity to a user whose `users.status == "blocked"`
- **THEN** the message is rejected (blocking is enforced at the platform resolver via `users.status`)

#### Scenario: Tenant mismatch is rejected (managed)
- **WHEN** the mapped user's `tenant_id` differs from the connector edge tenant
- **THEN** the message is rejected and a diagnostic log entry is recorded
