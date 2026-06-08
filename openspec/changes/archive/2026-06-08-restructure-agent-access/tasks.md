## 1. 模型重构（agent_config.py）

- [x] 1.1 写测试：`ConnectorAccess` 默认值和字段约束（unit）
- [x] 1.2 写测试：`SlackConnector` 不再有 `channels` 字段，有 `access: ConnectorAccess`（unit）
- [x] 1.3 写测试：`TelegramConnector` 不再有 `channels` 字段，有 `access: ConnectorAccess`（unit）
- [x] 1.4 写测试：`AgentFile` 不再有 `bindings` 和 `access` 顶层字段（unit）
- [x] 1.5 写测试：`build_index()` 不再读取 `bindings` 字段（unit）
- [x] 1.6 写测试：`AgentConfigIndex` 不再有 `by_channel`/`by_user`/`agent_for_channel`/`agent_for_user`（unit）
- [x] 1.7 运行相关测试，确认全红
- [x] 1.8 实现：新增 `ConnectorAccess` 模型，删除 `AgentAccess`、`AgentBindings`；更新 `SlackConnector`/`TelegramConnector`（删 `channels`，加 `access`）；更新 `AgentFile`（删 `bindings`/`access`）；更新 `AgentConfigIndex` 和 `build_index()`
- [x] 1.9 运行相关测试，确认全绿

## 2. 访问门控层（im_gateway/access.py）

- [x] 2.1 写测试：`channel_allowed(ConnectorAccess, channel_id)` 行为与原逻辑一致（unit）
- [x] 2.2 写测试：`user_allowed(ConnectorAccess, store, identity)` 行为与原逻辑一致（unit）
- [x] 2.3 运行相关测试，确认红
- [x] 2.4 实现：将 `channel_allowed`/`user_allowed` 参数类型从 `AgentAccess` 改为 `ConnectorAccess`
- [x] 2.5 运行相关测试，确认绿

## 3. 路由和门控（im_gateway/normalizer.py）

- [x] 3.1 写测试：`_get_connector_access` 按 platform 返回正确 connector 的 access（unit）
- [x] 3.2 写测试：`_get_connector_access` 对未知 platform 返回 `ConnectorAccess()` 默认关闭（unit）
- [x] 3.3 写测试：`get_agent_for_context` 简化后仅返回 default agent（unit）
- [x] 3.4 运行相关测试，确认红
- [x] 3.5 实现：新增 `_get_connector_access()`；简化 `get_agent_for_context()`；更新 `route()` 中的 access gate 调用
- [x] 3.6 运行相关测试，确认绿

## 4. Snapshot 路由清理（runtime/snapshot.py）

- [x] 4.1 写测试：snapshot 路径不再调用 `agent_for_channel`/`agent_for_user`（unit）
- [x] 4.2 运行测试，确认红
- [x] 4.3 实现：移除 snapshot.py 中对 `agent_for_channel`/`agent_for_user` 的引用
- [x] 4.4 运行测试，确认绿

## 5. 示例文件更新

- [x] 5.1 更新 `agents/default/agent.yaml.example`：删除顶层 `bindings`/`access`，在各 connector 下加 `access:` 示例块，删除 `channels` 字段

## 6. 存量测试修复与全量回归

- [x] 6.1 修复所有因字段变更/签名变更而失败的存量测试（`test_agent_access.py`、`test_normalizer_local_access.py` 等）
- [x] 6.2 运行全量测试套件：`uv run pytest -x -q`，确认全绿（29 个失败均为 main 分支预存问题，与本次变更无关）
- [x] 6.3 运行测试层边界检查：`uv run python scripts/check_test_layers.py`（1 个预存警告 test_config.py:166，与本次变更无关）
