# Roomier, themed template editor

## Why

The template modal's system-prompt textarea is cramped and renders with an
unthemed white background (the global input styling covers `input, select` but
not `textarea`), making it uncomfortable to author a prompt. The editor should
be roomy and match the dark theme.

## What Changes

- Extend the global form-control styling to include `textarea` (dark
  background, theme border, full width, vertical resize) so textareas match
  inputs across the console.
- Widen the template modal and increase the system-prompt textarea height so
  there is comfortable room to write a prompt.

Pure-frontend (admin.html) CSS/markup change; no API, data, or behavior change.

## Impact

- Affected specs: `admin-console-design-system` (ADDED: themed, comfortably
  sized multi-line editors).
- Affected code: `src/fleetent/static/admin.html` only.
