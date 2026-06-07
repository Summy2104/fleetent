## 1. 测试先行（红）

- [x] 1.1 改 `tests/integration/test_blocklist.py`：级联/unblock/batch 三个用例改调 `block_service.block_user/unblock_user/batch_block`，`is_registration_blocked`/重复注册拦截仍走 `blocklist`；fixture 增加 monkeypatch `block_service` 模块（如需）。运行 `uv run pytest tests/integration/test_blocklist.py -x -q` **必须红**（`block_service` 不存在）
- [x] 1.2 改 `tests/unit/test_governance_imports.py`：`blocklist` 公共 API 集合更新为 `{DB_PATH, is_registration_blocked, ban_registration, _init_db}`，新增断言 `fleetent.governance.blocklist` 源码不含 `import fleetent.platform`。运行 `uv run pytest tests/unit/test_governance_imports.py -x -q` **必须红**

## 2. 实现（绿）

- [x] 2.1 新建 `src/fleetent/platform/user_management/block_service.py`：搬入 `block_user`/`unblock_user`/`batch_block`，import `user_store`、`governance.audit_log`、`governance.blocklist`（调 `ban_registration`）、`api_key_store`、`im_gateway_management`
- [x] 2.2 收窄 `src/fleetent/governance/blocklist.py`：删 `block_user`/`unblock_user`/`batch_block`/`_disable_im_accounts`，将 `_ban_registration` 提升为 public `ban_registration`，保留 `is_registration_blocked`/`_init_db`/`DB_PATH` re-export；确认零 `fleetent.platform` import
- [x] 2.3 改 `src/fleetent/platform/user_management/user_admin_api.py`：`blocklist.block_user`→`block_service.block_user`、`blocklist.unblock_user`→`block_service.unblock_user`，更新 import（去 `blocklist`，加 `block_service`）
- [x] 2.4 运行 `uv run pytest tests/integration/test_blocklist.py tests/unit/test_governance_imports.py -x -q` **必须绿**

## 3. 收尾

- [x] 3.1 `uv run ruff format src tests && uv run ruff check src tests` + `uv run mypy src`
- [x] 3.2 `env -u FLEETENT_HOME uv run pytest -x -q` 全绿 + `uv run python scripts/check_test_layers.py`
