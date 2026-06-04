## Why

IM access control (channel allowlist + user approval) is keyed by **owner** and lives
in the platform DB (`im_channel_allowlist`, `im_user_store`). For a self-contained agent
that runs as its own process (see `agent-runtime-cli`), access control must travel with
the agent — not depend on a platform database. This change makes IM access **per-agent**
and **agent-home-local**, so a standalone agent enforces its own allowlist with zero
platform-DB access.

## What Changes

- **Per-agent access model**: the set of allowed channels/users and approved users is
  scoped to a single agent, not an owner/workspace.
- **Platform authors, agent home holds**: static allow rules are authored on the
  platform and **materialized into the agent's home** (an `access` block in `agent.yaml`,
  or a sibling `allowlist` file in the agent home). The agent reads them locally.
- **Runtime evaluation is local + zero platform DB**: the IM access gates (now on the
  unified `im` module: `im.is_allowed` / `im.check_allowed_by_user_id`) are evaluated by
  the agent runtime against the agent's local access config + the agent's **own local
  approval store** (agent home `data/`), not the owner-keyed platform tables.
- **User identity resolved locally too**: the (platform, platform_user_id)→user mapping
  the IM adapters do today via the platform `user_store` (`get_or_create`) is made
  agent-local — the agent runtime uses the platform-native IM user id as the identity
  (or an agent-local mapping store), so it never reads the platform user DB. (Closes the
  gap where allowlist was local but identity still hit the platform DB.)
- **Dynamic approval writes locally**: a pending→approved transition at runtime writes to
  the agent's local approval store (agent home `data/`), keeping the agent self-contained.
- **Default closed**: when an agent declares no `access` rules, the safe default is
  "no implicit allow; approval required" (this changes the legacy "allowlist-off =
  allow-all" default).
- **BREAKING**: the owner-keyed allowlist/user-approval/user-mapping DB path is no longer
  consulted on the agent runtime path; platform-side editing produces the materialized
  per-agent rules.

## Capabilities

### New Capabilities
- `per-agent-im-access`: per-agent IM access model — static allow rules in the agent
  home + an agent-local approval store, evaluated in the agent runtime with no platform
  DB read.

### Modified Capabilities
- `im-channel-allowlist`: channel allow decisions are per-agent and sourced from the
  agent's local access config, not the owner-keyed `im_channel_allowlist` table at runtime.
- `im-user-allowlist`: IM user approval is per-agent and evaluated against the agent's
  local approval store, not the owner-keyed user store at runtime.
- `im-user-mapping`: at runtime the (platform, platform_user_id)→identity resolution is
  agent-local (platform-native id or agent-local mapping), not a platform `user_store`
  read.
- `im-gateway`: `route` consults the per-agent local access gates (and local identity)
  before entering the loop, with no platform-DB lookup.

## Impact

- **Code**: `agent_config` (access block in the agent home model); a per-agent local
  access/approval store under the agent home `data/`; `normalizer.route` rewired to the
  local gates; platform authoring writes the materialized rules.
- **Prerequisite for** `agent-runtime-cli` (a standalone agent must own its access).
- **No new deps**. Migration: owner-level allowlist tables remain for the platform
  authoring side; the runtime stops reading them.
