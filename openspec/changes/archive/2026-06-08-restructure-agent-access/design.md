## Context

当前 `agent.yaml` 中存在三个访问控制相关配置块：

- `connectors.slack.channels` / `connectors.telegram.channels`：connector 层的第一道频道过滤（Slack SDK 级别直接丢弃）
- `bindings`：多 agent HTTP 路由表，记录 channel→agent / user→agent 映射。在 per-agent connector 模式下，IM 消息的 agent 由连接本身确定，此字段对 IM 路径完全无效
- `access`：顶层访问策略（`allow_channels`、`allow_users`、`require_approval`），全平台共用

`bindings` 的 `by_channel`/`by_user` 路由仅在 `msg.agent_name` 为空时才被调用，而所有 per-agent Slack/Telegram 连接均在消息上打好了 `agent_name`，路由代码永不执行。

## Goals / Non-Goals

**Goals:**
- 删除 `AgentBindings` 及所有依赖它的路由代码
- 用 `ConnectorAccess` 统一封装 per-platform 访问策略，嵌入各 connector
- 删除 `connector.channels` 字段（频道过滤归入 `access.allow_channels`）
- 删除顶层 `AgentAccess` 和 `AgentFile.access` 字段
- 访问控制行为保持完全不变，只改配置读取路径

**Non-Goals:**
- 不引入新的访问控制语义（`allow_all_users`、channel 授权用户等新功能留给 Change 2）
- 不改动 HTTP `/chat` API 路由逻辑（`get_agent_for_context` 简化后仅返回 default agent，不影响现有 API 行为）
- 不改动 `LocalApprovalStore` 的存储结构

## Decisions

### D1：删除 `connectors.<platform>.channels`，频道过滤统一由 `access.allow_channels` 承担

**当前问题**：`connector.channels` 和 `access.allow_channels` 语义重叠，用户需要在两处配置同一频道 ID。

**决策**：删除 `connector.channels`，`normalizer.py` 的频道门控（`channel_allowed`）读取 `connector.access.allow_channels`，替代原来两层过滤。第一层 SDK 级过滤（slack_bolt 直接忽略事件）随之消除——影响是所有频道的消息都会进入 normalizer，但 access gate 会立即拒绝不在允许列表内的频道，额外开销可忽略。

**备选方案**：保留 `connector.channels` 作为性能优化的第一层，`access.allow_channels` 作为第二层。否决原因：两个字段同时存在会导致持续的配置混乱，用户无法直觉地知道应配置哪个。

### D2：引入 `ConnectorAccess` 复用模型，而非在每个 connector 中平铺字段

**决策**：

```python
class ConnectorAccess(BaseModel):
    allow_channels: list[str] = Field(default_factory=list)
    allow_users: list[str] = Field(default_factory=list)
    require_approval: bool = True

class SlackConnector(BaseModel):
    bot_token_env: str
    app_token_env: str
    access: ConnectorAccess = Field(default_factory=ConnectorAccess)

class TelegramConnector(BaseModel):
    bot_token_env: str
    access: ConnectorAccess = Field(default_factory=ConnectorAccess)
```

**理由**：
- `access.py` 的门控函数签名只需改一次（`ConnectorAccess` 替代 `AgentAccess`）
- 未来新增平台（WhatsApp 等）只需新建 connector + 内嵌 `access: ConnectorAccess`，无需改门控逻辑
- YAML 结构清晰：凭证与访问策略分层，同一 connector 块内可见

**备选方案**：字段平铺进 connector（无嵌套）。否决原因：读写代码需要针对每个 connector 单独处理字段，且难以传递给 `access.py` 的通用函数。

### D3：`normalizer.py` 按 `msg.platform` 动态读取 access config

**决策**：

```python
def _get_connector_access(agent: AgentFile | None, platform: str) -> ConnectorAccess:
    if agent is None:
        return ConnectorAccess()
    if platform == "slack" and agent.connectors.slack:
        return agent.connectors.slack.access
    if platform == "telegram" and agent.connectors.telegram:
        return agent.connectors.telegram.access
    return ConnectorAccess()  # default closed
```

**理由**：访问策略与平台绑定，函数式无状态，易于测试和扩展。

### D4：`get_agent_for_context()` 简化为仅返回 default agent

**决策**：移除 `by_channel`/`by_user` 查找，保留函数签名不变（避免影响外部调用），实现简化为：

```python
def get_agent_for_context(platform: str, channel_id: str, user_id: str) -> AgentFile | None:
    index = agent_config.current()
    name = index.default_agent()
    return None if name is None else index.get(name)
```

**理由**：`bindings` 路由路径在现有部署模式下永不执行，移除不影响任何实际行为。

## Risks / Trade-offs

- **[风险] 删除 `connector.channels` 后，所有频道消息都进入 normalizer**  
  → 缓解：`channel_allowed` 在 normalizer 入口即拒绝，开销极小；若日志量增加可观测到

- **[风险] 现有 `agent.yaml` 文件在升级后因字段不兼容而加载失败**  
  → 缓解：`AgentFile` 使用 `extra="forbid"`，已有 `bindings`/`access` 字段的 yaml 会立即报错，失败快速、明确；`agent.yaml.example` 同步更新为新格式作为迁移参考

- **[风险] `runtime/snapshot.py` 中的 `agent_for_channel`/`agent_for_user` 调用被移除后行为变化**  
  → 缓解：snapshot 路径同样是 IM per-agent 模式下永不被调用的分支（`agent_name` 已确定），移除不影响实际功能

## Migration Plan

1. 更新 `agent_config.py`（模型变更 + 路由删除）
2. 更新 `access.py` 签名
3. 更新 `normalizer.py`（新的 `_get_connector_access` + 简化路由）
4. 更新 `snapshot.py`
5. 更新 `agent.yaml.example`
6. 全量跑测试，修复因参数签名或字段变更而失败的用例

无需数据库迁移，无需停机，不影响 HTTP API。
