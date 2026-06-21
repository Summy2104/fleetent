## ADDED Requirements

### Requirement: API key revoke and rotate in the React SPA

The React admin SPA SHALL let an admin, for a selected user, list API keys, create a key, **rotate** a key, and **revoke** an individual key — closing the legacy gap where keys could only be created. A newly created or rotated key's plaintext value SHALL be shown once for copy and SHALL NOT be re-displayed or re-fetched afterward; the list SHALL show only a masked prefix.

#### Scenario: Revoke an individual key

- **WHEN** an admin revokes a listed key and confirms
- **THEN** the SPA calls `DELETE /admin/keys/{key_id}` and the key is removed from the list

#### Scenario: Rotate a key shows the new secret once

- **WHEN** an admin rotates a key
- **THEN** the SPA calls `POST /admin/users/{id}/rotate-key`, shows the new plaintext key once for copy, and the list afterward shows only the masked prefix

#### Scenario: Plaintext key is never re-shown

- **WHEN** the key list is re-rendered or re-fetched after creation/rotation
- **THEN** no plaintext key value is displayed; only the masked prefix is shown
