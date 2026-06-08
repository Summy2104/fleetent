## Why

当前 `ConnectorAccess` 的访问控制逻辑是全用户门控：任何用户都必须在 `allow_users` 中或经动态审批才能与 bot 交互。这在两个常见场景下造成运营摩擦：

1. **群频道 bot**：管理员已将 bot 加入受控 Slack/Telegram 频道，频道成员资格本身即是隐性授权，逐一添加 `allow_users` 不切实际
2. **开放 DM**：部分 bot 需要对所有用户开放私聊，无法通过 `allow_users` 枚举

## What Changes

- **`allow_channels` 授权语义增强**：当消息来自明确列在 `allow_channels` 中的频道时，跳过用户门控——频道列入白名单即隐式授权该频道内所有用户；`allow_channels` 为空（允许所有频道）时用户门控保持不变
- **新增 `allow_all_users: bool = False`**：在 `ConnectorAccess` 中新增此字段；为 `true` 时跳过用户门控，允许所有人（包括 DM）；`require_approval` 在此模式下无效
- 以上两个新语义在 `normalizer.route()` 的门控逻辑中统一实现

## Capabilities

### New Capabilities

_无（增强现有访问控制能力，不引入独立新能力）_

### Modified Capabilities

- `per-agent-im-access`：新增两种跳过用户门的触发条件：(1) 消息所在频道在 `access.allow_channels` 中；(2) `access.allow_all_users: true`

## Impact

- `src/fleetent/agent_config.py`：`ConnectorAccess` 新增 `allow_all_users: bool = False`
- `src/fleetent/im_gateway/normalizer.py`：`route()` 中用户门控逻辑更新
- 测试：新增 unit 测试覆盖两种跳过场景及其边界条件
