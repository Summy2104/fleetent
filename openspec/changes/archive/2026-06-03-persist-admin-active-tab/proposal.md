# Persist active admin tab across reloads

## Why

Reloading the admin console always lands the user back on the Users tab,
regardless of where they were (e.g. refreshing on Agents jumps to Users).
The active tab should survive a reload so the user stays where they were.

## What Changes

- Reflect the active tab in `location.hash` when `switchTab()` runs.
- On app entry, restore the tab from the hash (falling back to `users` when
  the hash is missing or not a known tab) instead of hardcoding `users`.

Pure-frontend (admin.html) change; no API or data changes.

## Impact

- Affected specs: `admin-console-design-system` (ADDED: active tab persists
  across reload).
- Affected code: `src/fleetent/static/admin.html` only.
