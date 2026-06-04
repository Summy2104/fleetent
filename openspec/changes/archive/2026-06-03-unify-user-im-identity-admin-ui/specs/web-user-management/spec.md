## MODIFIED Requirements

### Requirement: User list and lifecycle
The system SHALL list users filterable/sortable by status, last-active, and bound IM count, and SHALL support editing, disabling, and deleting a user.

The admin console SHALL present this list as the single User-centric identity view in one **Users** tab under the Access navigation group. Each row is one internal User. A User that has bound IM identities (`im_users.user_id = user.id`) SHALL show an expand/collapse control; expanding SHALL list each bound IM identity with its platform, platform_user_id, and allowed state, plus Bind / Block / Restore actions. A User with no bound IM identities SHALL NOT show an expander. Connectors owned by a User (`connectors.owner_id = user.id`) SHALL be shown under that User. Ownership SHALL be presented at the User level, not per IM identity. The list SHALL provide a source filter distinguishing auto-created IM-origin Users from human/API Users, with a source badge on each row. The console SHALL render whole-User disable (`users.status`) and single-IM-identity block (`im_users.allowed`) as distinct controls so the two are not conflated.

#### Scenario: Filtered list
- **WHEN** an admin lists users filtered to `status=active`
- **THEN** only active users are returned, sortable by last-active and bound IM count

#### Scenario: Disable user
- **WHEN** an admin disables a user
- **THEN** the user's `status` becomes `disabled` and they cannot log in, while data is retained

#### Scenario: User with IM identities is expandable
- **WHEN** an admin views a User that has one or more bound IM identities
- **THEN** the row shows an expand control, and expanding it lists each IM identity's platform, platform_user_id, and allowed state with Bind / Block / Restore actions

#### Scenario: User without IM identities has no expander
- **WHEN** an admin views a User with no bound IM identities
- **THEN** the row shows no expand/collapse control

#### Scenario: Connectors shown under their owning User
- **WHEN** a User owns one or more connectors (`connectors.owner_id = user.id`)
- **THEN** those connectors are shown under that User with status, enabled flag, and masked credentials, and ownership is presented at the User level rather than per IM identity

#### Scenario: Source filter distinguishes IM-origin users
- **WHEN** an admin toggles the source filter
- **THEN** the list distinguishes auto-created IM-origin Users (e.g. name `slack:U123`) from human/API Users, each row carrying a source badge, with all sources shown by default

#### Scenario: Two block semantics are distinct
- **WHEN** an admin views the unified Users view
- **THEN** whole-User disable (`users.status`) and single-IM-identity block (`im_users.allowed`) are rendered as separate controls with distinct labels
