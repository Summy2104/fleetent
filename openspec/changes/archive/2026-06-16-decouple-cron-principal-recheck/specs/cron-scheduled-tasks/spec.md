## MODIFIED Requirements

### Requirement: Scheduled tasks are agent-owned with no platform dependency
Scheduled-task persistence and scheduling SHALL be entirely agent-runtime concerns. `schedule_store` and `cron_scheduler` MUST NOT `import fleetent.platform.*` and MUST NOT write to any platform table. The fire-time path SHALL NOT read platform-owned tables either: `cron_scheduler` MUST NOT open or query the platform management database (the `users` table) to resolve a fired task's principal — in particular it MUST NOT call `user_store.get_by_id` directly, and MUST NOT import `user_store` for that purpose. An agent SHALL be able to create **and fire** scheduled tasks in an environment where the platform service is absent and the platform database / `scheduled_tasks` table do not exist, **regardless of how `DATABASE_URL` is configured** (unset, empty, or pointing at a non-existent file) — a malformed or empty `DATABASE_URL` SHALL NOT cause fired tasks to be skipped.

#### Scenario: Create and fire without platform
- **WHEN** `fleetent agent run` is executed with no platform service and no platform database present
- **THEN** the `schedule` tool can create a task and the in-process scheduler fires it on time

#### Scenario: No reverse dependency on platform
- **WHEN** the agent-runtime scheduling modules are imported
- **THEN** they do not import `fleetent.platform.*`, do not import `user_store`, and do not access platform-owned tables

#### Scenario: Empty or malformed DATABASE_URL does not break firing
- **WHEN** a standalone agent fires a task created by a real IM user while `DATABASE_URL` is set to an empty string (or any value that would fail to open the management database)
- **THEN** the task still fires and delivers — the principal is resolved from the task's archived IM identity without touching the management database

## ADDED Requirements

### Requirement: Fire-time principal resolution is injection-decoupled from platform
The scheduler's fire-time principal resolution SHALL use an injection seam, mirroring the existing platform-resolver pattern (`user_store.set_api_key_resolver`, `connectors.set_provider`, `set_im_identity_resolver`). `cron_scheduler` SHALL expose a module-level `set_principal_resolver(resolver)` whose installed callable maps a fired task to a `Principal | None`. When **no** resolver is installed (the standalone agent — the platform `server.py` lifespan that injects it never runs), the scheduler SHALL trust the task's archived identity unconditionally — `Principal(user_id, tenant_id="default")` for any non-`system`/non-`default` user_id — without opening or querying any database (the agent-independence baseline). When a resolver **is** installed (platform mode), the scheduler SHALL delegate principal resolution to it; the resolver SHALL perform the creator revocation recheck against the `users` table — returning `None` for a blocked creator (skip), `Principal(user_id, "default")` for a vanished creator that still carries a platform IM `origin`, the creator's current `Principal(user_id, tenant_id)` for an active creator, and `None` for a vanished creator with no IM origin. A raised exception from the installed resolver (e.g. a locked or unreachable management DB) SHALL be caught and treated as fail-closed (`None`, skip) — never fire a task whose identity cannot be reverified. The `system` and `default` user_id short-circuits SHALL remain unchanged and SHALL NOT consult the resolver or any database.

#### Scenario: Standalone trusts archived identity without a database
- **WHEN** no principal resolver is installed and a fired task carries a non-`system`/non-`default` user_id (with or without an IM `origin`)
- **THEN** `_resolve_cron_principal` returns `Principal(user_id, "default")` without calling `user_store` or opening any database

#### Scenario: Platform-injected resolver enforces revocation
- **WHEN** the platform lifespan has called `set_principal_resolver` and a fired task's creator is now `blocked` in the `users` table
- **THEN** the injected resolver returns `None` and the fire is skipped; an unblocked creator resolves to their current `Principal(user_id, tenant_id)`

#### Scenario: Platform resolver lookup error fails closed
- **WHEN** a principal resolver is installed and it raises while consulting the `users` table (locked DB, I/O error)
- **THEN** `_resolve_cron_principal` catches the error, logs `cron_principal_recheck_failed`, and returns `None` so the task does not fire unverified

#### Scenario: system and default short-circuit unchanged
- **WHEN** a fired task has user_id `system` or `default`
- **THEN** the principal resolves to `SYSTEM_PRINCIPAL` / `Principal("default", "default")` respectively without consulting the resolver or any database
