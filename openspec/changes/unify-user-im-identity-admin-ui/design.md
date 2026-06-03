## Context

`admin.html` is a self-contained vanilla-JS SPA. Today the Access group has two tabs: **Users** (`#tab-users`, `loadUsers`/`renderUsers` over `/admin/users`) and **IM** (`#tab-im`, `loadIm` rendering per-platform groups of connectors + IM users over `/admin/im/connectors` + `/admin/im-users`, from the just-archived `merge-im-connectors-ui-into-im-users`).

Data model (verified):
- `users` table: `id, name, api_key, created_at, email, role, status, must_reset, ...` — **no `owner_id`**.
- `im_users`: `(owner_id, platform, platform_user_id, user_id, allowed, created_at)` — `user_id → users.id`; auto-created on first message via `identity.get_or_create`, which also creates a backing User named `{platform}:{platform_user_id}` with `allowed=1`.
- `connectors`: keyed `(owner_id, platform)`; `owner_id` is a `users.id`.

So both IM identities and connectors already reference a User id. The unification is a presentation re-axis, not a schema change.

## Goals / Non-Goals

**Goals:**
- Single User-centric **Users** tab; remove the standalone IM tab.
- Per User: foldable IM identities (only when present) + connectors owned by that User.
- Owner presented at User level; drop per-`im_users` owner display.
- Source filter + badge separating IM-origin Users from human/API Users.
- Distinct controls for `users.status` (whole-User disable) vs `im_users.allowed` (per-identity block).
- Behavior-preserving backend; reuse existing endpoints/IM package API.

**Non-Goals:**
- No schema/route/API changes. No new `owner_id` on `users`.
- No change to `identity.get_or_create` auto-creation behavior.
- No change to connector credential storage/masking or the add-connection modal's per-platform fields.
- No cross-owner re-grouping logic beyond `owner_id = user.id` / `user_id = user.id` joins.

## Decisions

- **Single render off three endpoints.** `loadUsers` fetches `/admin/users`, `/admin/im-users`, `/admin/im/connectors` in parallel; build `imByUser` (`im_users.user_id → [identity]`) and `connByOwner` (`connectors.owner_id → [connector]`) maps; render one row per User, with a child region populated only when that User has IM identities and/or owned connectors.
- **Expander gating.** Render the expand/collapse control only when `imByUser[user.id]?.length` (per spec, expander is for IM identities). Owned connectors render in the same expandable child region.
- **Source classification (presentation-only).** Treat a User as IM-origin when it has bound IM identities OR its name matches the `{platform}:{id}` auto-name pattern; otherwise human/API. Badge each row; a filter `<select>`/toggle controls visibility (default: all). No backend flag added.
- **Two block semantics.** Whole-User disable keeps the existing Users action (`/admin/users/{id}/block|unblock`, status pill). Per-identity block uses the existing IM actions (`/admin/im-users/{id}/block|restore`, allowed pill) inside the expanded child. Labels: "Disable user" vs "Block identity".
- **Remove IM tab.** Delete `#tab-im` section + `loadIm`/`#im-groups`; drop `im` from nav, `TAB_GROUP`, `GROUP_DEFAULT_TAB`, `LOADERS`. Keep the connector modal (`openConnModal`/`createConn`/`renderConnFields`/`CONN_FIELDS`) and `connEnable`/`connDisable`; their refresh callback repoints to `loadUsers`. "Add connection" lives in the Users tab create bar (admin-gated).
- **TDD via UI-marker tests.** Extend `test_admin_console_ui.py` / `test_im_admin_api.py`: assert single Users axis (no `data-tab="im"`, no `#tab-im`, no `#im-groups`), expander wiring, per-User connector grouping (`owner_id`/`user_id` joins in `renderUsers`), source filter control, retained connector modal + enable/disable + viewer gate.

## Risks / Trade-offs

- **List flooding by auto-created Users.** Each IM identity spawns a backing User, so the Users list can grow large. Mitigated by the source filter; not solved structurally (no backend change). Accepted.
- **Owner anchor asymmetry.** Connectors are typically owned by the built-in admin owner, while IM identities bind to their own auto-created Users — so connectors cluster under the admin User while identities spread across many Users. This is accurate to the data but may surprise; documented in the connector child labeling.
- **Single-tab density.** Folding two concerns (identities + connectors) under Users increases per-row complexity; mitigated by collapse-by-default and only rendering child regions when non-empty.
- **Loss of platform-grouped connector view.** The just-shipped per-platform grouping is removed. Trade-off accepted per the chosen User-axis; connectors remain fully manageable, just grouped by owner instead of platform.
