## 1. 删死 wrapper get_or_create_im_user

- [ ] 1.1 grep 全仓（src/scripts/tests）再确认 `get_or_create_im_user` 无调用方（仅护栏注释提及）
- [ ] 1.2 删 `user_store.py` 的 `get_or_create_im_user`（及其 `from fleetent.platform import im_gateway_management` 懒加载）

## 2. migrate_api_keys 移到 platform.user_management

- [ ] 2.1 写测试（integration）：`platform.user_management` 暴露的 migrate 函数把 legacy `users.api_key` 迁入 `api_keys`（scope `["*"]`、无 expiry、同 user），行为与原 `user_store.migrate_api_keys` 等价 —— 见红
- [ ] 2.2 把 `migrate_api_keys` 实现移到 `platform.user_management`：读 legacy `users.api_key` 经 user_store 公开读（或最小只读查询）、写 `api_key_store`；删 user_store 内的 `migrate_api_keys`（及其 `from fleetent.platform.user_management import api_key_store` 懒加载） —— 见绿
- [ ] 2.3 `tests/integration/test_api_key_auth.py`：迁移测试改用 `platform.user_management` 的新路径

## 3. user_store 零 platform import + 棘轮清零

- [ ] 3.1 grep 自查：`user_store.py` 无任何 `fleetent.platform` import（顶层 + 函数内）
- [ ] 3.2 `tests/unit/test_module_dependency_guardrails.py`：从 `_KNOWN_TRANSITIVE_PLATFORM_LEAKS` 移除 `fleetent.user_store`（集合变空）；更新 stale 注释（删除"authenticate hard-import"等已不成立的描述）
- [ ] 3.3 跑护栏测试见绿：棘轮空，user_store 无传递泄漏；任何新 platform 传递泄漏仍会 fail

## 4. 收尾

- [ ] 4.1 验证基线：`fleetent agent run`（无 platform）bearer-auth 路径不传递触及 platform；user_store 相关单测/集成无新增失败
- [ ] 4.2 change 收尾：`make test-pr` 全绿 + `uv run pytest tests/integration -q`（对照 main 基线，无新增失败）
