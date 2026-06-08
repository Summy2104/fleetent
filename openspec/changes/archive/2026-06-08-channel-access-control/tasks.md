## 1. 模型扩展（agent_config.py）

- [ ] 1.1 写测试：`ConnectorAccess` 新增 `allow_all_users` 字段，默认 `false`（unit）
- [ ] 1.2 运行测试，确认红
- [ ] 1.3 实现：`ConnectorAccess` 添加 `allow_all_users: bool = False`
- [ ] 1.4 运行测试，确认绿

## 2. 访问门控逻辑（normalizer.py）

- [ ] 2.1 写测试：频道在 `allow_channels` 中时，用户门控被跳过（unit）
- [ ] 2.2 写测试：`allow_channels` 为空时，用户门控不跳过（unit）
- [ ] 2.3 写测试：`allow_all_users: true` 时，用户门控被跳过（unit）
- [ ] 2.4 写测试：`allow_all_users: false`（默认）时，用户门控保持不变（unit）
- [ ] 2.5 运行测试，确认全红
- [ ] 2.6 实现：`route()` 中计算 `skip_user_gate` 并更新门控逻辑
- [ ] 2.7 运行测试，确认全绿

## 3. 全量回归

- [ ] 3.1 运行全量测试套件：`uv run pytest -x -q`，确认全绿
- [ ] 3.2 运行测试层边界检查：`uv run python scripts/check_test_layers.py`
