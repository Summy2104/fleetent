## Context

`ConnectorAccess` 已在 Change 1（restructure-agent-access）中建立，访问门控逻辑在 `normalizer.route()` 中按以下顺序执行：

```
channel_allowed(access_cfg, channel_id) → 否则拒绝
user_allowed(access_cfg, store, user_id)  → 否则拒绝（require_approval 时加入 pending）
→ 进入 agent loop
```

当前 `user_allowed` 逻辑：`identity in allow_users OR store.is_approved(identity)`，没有任何"跳过"路径。

## Goals / Non-Goals

**Goals:**
- 当消息频道在 `allow_channels` 中时，跳过 `user_allowed` 检查
- 当 `allow_all_users: true` 时，跳过 `user_allowed` 检查（任何人均可）
- `allow_channels` 为空时（允许所有频道但无显式授权），用户门控维持不变

**Non-Goals:**
- 不改变 `channel_allowed` 的语义（empty = allow all 保持不变）
- 不改变 `LocalApprovalStore` 的存储结构
- DM 通道不在 `allow_channels` 范围内（DM channel_id 无法预配置），需通过 `allow_all_users: true` 或 `allow_users` 开放

## Decisions

### D1：门控短路逻辑位于 `normalizer.route()`，不修改 `access.py` 函数

在 `normalizer.route()` 中，获取 `access_cfg` 后直接判断是否需要用户门控，而非修改 `user_allowed()` 本身。这样 `user_allowed()` 保持纯粹的"静态白名单+动态审批"语义，短路逻辑集中在调用处。

```python
# 新逻辑（伪代码）
channel_explicitly_allowed = bool(access_cfg.allow_channels) and msg.channel_id in access_cfg.allow_channels
skip_user_gate = access_cfg.allow_all_users or channel_explicitly_allowed

if not access.channel_allowed(access_cfg, msg.channel_id):
    await msg.reply_func(_REJECTION_MSG)
    return
if not skip_user_gate and not access.user_allowed(access_cfg, store, msg.user_id):
    if access_cfg.require_approval:
        store.add_pending(msg.user_id)
    await msg.reply_func(_REJECTION_MSG)
    return
```

**理由**：`access.py` 的函数签名简洁，职责单一。短路逻辑依赖 `allow_channels` 的"是否显式列出"语义，而 `channel_allowed()` 已将空列表处理为"allow all"，两者语义不同，不宜混用。

### D2：`allow_all_users` 字段加在 `ConnectorAccess` 上

与 `allow_users`/`allow_channels`/`require_approval` 同级，保持 per-platform 访问策略的完整性。

### D3：`allow_channels` 为空时不触发频道授权跳过

`allow_channels: []` 含义是"允许 connector 收到事件的所有频道"，不等于"显式授权所有频道"。只有非空 `allow_channels` 中明确列出的频道才触发用户门跳过。

## Risks / Trade-offs

- **[风险] 用户误以为 `allow_channels: []`（空）也能跳过用户门**  
  → 缓解：`agent.yaml.example` 中注释明确说明空列表不触发频道授权

- **[风险] `allow_all_users: true` 完全绕过访问控制**  
  → 这是设计意图，适用于内部工具场景；`require_approval` 默认为 `true`，`allow_all_users` 默认 `false`，不会意外开放
