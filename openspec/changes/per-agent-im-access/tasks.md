## 1. Agent-home access config

- [x] 1.1 Write failing unit tests: `agent.yaml` `access` block parses
  (`allow_channels`/`allow_users`/`require_approval`); absent block → safe default
  (no implicit allow, approval required); inline secret rules still rejected.
- [x] 1.2 Add the `access` model to the agent home schema in `agent_config`. Make 1.1 green.

## 2. Agent-local approval store

- [x] 2.1 Write failing unit tests: local approval store under agent home `data/` —
  add/approve/list/contains; survives reload; isolated per agent (tmp home).
- [x] 2.2 Implement the agent-local approval store (json under home `data/`, injectable
  path). Make 2.1 green.

## 2b. Local IM user identity (no platform user_store)

- [x] 2b.1 Write failing tests: the agent runtime resolves a stable per-agent identity
  for an incoming IM message with the platform `user_store` rigged to raise (no
  `get_or_create`/user-DB read); identity is the platform-native id or an agent-local
  mapping.
- [x] 2b.2 Make IM adapters / route resolve identity locally (drop the platform
  `user_store.get_or_create` from the agent runtime path). Make 2b.1 green.

## 3. Local, zero-DB route gate

- [x] 3.1 Write failing tests: `normalizer.route` allows a user in `allow_users` /
  approved-locally; blocks a disallowed user when `require_approval`; channel filter via
  `allow_channels`; with the platform allowlist/user-store rigged to raise, routing still
  decides (zero-DB proof).
- [x] 3.2 Rewire `route` channel/user gates to the local access config + approval store;
  remove the owner-keyed `im_channel_allowlist`/user-store reads from the runtime path.
  Make 3.1 green.

## 4. Migrate + closeout

- [x] 4.1 Migrate existing allowlist/route tests to the per-agent local model.
- [x] 4.2 `uv run ruff format src tests && uv run ruff check src tests` and
  `uv run mypy src` (no new errors over baseline).
- [x] 4.3 Full suite `uv run pytest -x -q` green (3115 passed; 4 pre-existing baseline
  failures unrelated to this change, confirmed failing on the base branch).
