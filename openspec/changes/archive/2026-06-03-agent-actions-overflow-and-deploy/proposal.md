# Collapse agent row actions into an overflow menu + add Deploy

## Why

Each agent row renders a long line of action buttons (Stats, Versions, Edit, Bindings,
Clone, Enable/Disable, Archive/Restore, Delete). The row is crowded and hard to scan.
Operators also lack a one-click way to put an agent live on an IM channel.

## What Changes

- Collapse the per-row agent actions into a single `⋯` overflow menu. The menu lists the
  existing actions (Stats, Versions, Edit, Bindings, Clone, Enable/Disable,
  Archive/Restore, Delete). Admin-only items stay hidden for viewers.
- Add a **Deploy** action to the menu: it opens a small dialog (platform + channel_id)
  and binds the agent to that IM channel so it serves there — "deploying" the agent.
  Reuses the existing channel-binding endpoint
  (`POST /admin/agents/{name}/bindings/channels/{platform}/{channel}`); no API or schema
  change.

## Impact

- Affected specs: `agent-admin-ui`
- Affected code: `static/admin.html`
- Backward compatibility: pure presentational regrouping plus a new convenience action
  over an existing endpoint; no behavior change to lifecycle/binding semantics.
