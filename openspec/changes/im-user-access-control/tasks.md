## 1. im_user_store — allowlist 字段与 migration

- [x] 1.1 Write failing tests for `allowed` field: `get_or_create` returns `allowed=False` for new users, `approve_user()` sets `allowed=True`, `block_user()` sets `allowed=False`, `list_pending()` returns only unapproved users
- [x] 1.2 Add `allowed BOOLEAN DEFAULT 0` column to `im_users` schema in `_init_db()`, migrate existing rows to `allowed=1`, implement `approve_user(im_user_id)`, `block_user(im_user_id)`, `list_pending()` in `im_user_store.py`

## 2. agent_store — channel_agents 表与 default agent

- [x] 2.1 Write failing tests for `channel_agents`: `assign_channel()`, `unassign_channel()`, `get_agent_for_channel()` returns correct agent or None; and for `get_default_agent()` returning agent by `Settings.default_agent_name` or None
- [x] 2.2 Add `channel_agents` table to `_init_db()`, implement `assign_channel(platform, channel_id, agent_id)`, `unassign_channel(platform, channel_id)`, `get_agent_for_channel(platform, channel_id)`, `get_default_agent()` in `agent_store.py`

## 3. config — default_agent_name 设置

- [x] 3.1 Write failing tests: `Settings` loads `default_agent_name` from env/yaml; defaults to `None` when unset
- [x] 3.2 Add `default_agent_name: str | None = None` to `Settings` in `config.py`

## 4. normalizer — 准入检查 + 新 agent 查找顺序

- [x] 4.1 Write failing tests for normalizer: allowed=False user gets rejection response and does not call agent_loop; agent lookup follows channel → user → default → bare run order
- [x] 4.2 In `normalizer.py`, add allowed check after `get_or_create`; extract `get_agent_for_context(platform, channel_id, user_id)` helper that queries channel → user → default; apply result to `agent_loop.run()` call

## 5. server.py — /chat 接口同步 agent 查找逻辑

- [x] 5.1 Write failing tests: `/chat` with `x-platform` + `x-channel-id` headers uses channel agent when bound
- [x] 5.2 In `server.py`, reuse `get_agent_for_context()` (or replicate lookup) for `/chat` endpoint; accept optional `x-platform` and `x-channel-id` request headers

## 6. admin CLI — 新增命令

- [x] 6.1 Write failing tests for new admin commands: `list-pending` output, `approve-user`, `block-user`, `assign-channel`, `unassign-channel`, `set-default-agent`
- [x] 6.2 Implement `list-pending`, `approve-user --im-user-id`, `block-user --im-user-id` in `admin.py` (calls `im_user_store`)
- [x] 6.3 Implement `assign-channel --platform --channel-id --agent-name`, `unassign-channel --platform --channel-id` in `admin.py` (calls `agent_store`)
- [x] 6.4 Implement `set-default-agent --agent-name` / `--clear` in `admin.py` (reads/writes `config/settings.yaml` via pyyaml)

## 7. 验证

- [x] 7.1 Run full test suite (`uv run pytest -x -q`), confirm all tests pass
- [ ] 7.2 Manual smoke test: new IM user gets rejected; after `approve-user`, same user can chat; `assign-channel` routes group messages to correct agent
