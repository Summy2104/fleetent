# Permission Design

## 核心原则

Agent 实际能做的事 = Agent 权限 ∩ 用户权限（取交集）。

用户没有的权，Agent 不可能代替用户获得。超出两者权限范围的操作直接拒绝，不存在"等管理员审批"的场景。

## 两层权限模型

### Layer 1：Agent 服务账号权限

Agent 在各外部系统（Google Workspace、Slack、数据库等）拥有独立的服务账号，在系统创建时配置好基础权限。

- 权限在各系统里直接管理，不在代码里维护
- 遵循最小权限原则，只给 Agent 完成日常任务必需的权限
- MCP Server 是权限边界的实现位置：创建 MCP Server 时把相关权限配置好

### Layer 2：用户临时委托（OAuth 2.1）

当用户要求 Agent 访问用户自己的私有数据时，用户通过 OAuth 2.1 把自己的权限临时委托给 Agent。

**触发条件**：所需资源属于用户本人，但 Agent 服务账号无权访问（例如：用户的个人日历、个人文件、个人邮件）。

**流程**：
```
Agent 发现需要访问用户私有资源
  → 引导用户完成 OAuth 2.1 授权（PKCE flow）
  → 用户 grant scopes
  → Agent 获得 scoped access token
  → 用 token 调用 MCP Server 访问资源
  → 会话结束，token 失效
```

**不适用的场景**：用户自己也没有的权限，直接返回"无权限"，不走 OAuth 流程。

## 授权协议选择

| 协议 | 结论 |
|------|------|
| OAuth 2.1 | 当前选择。满足用户委托场景，工具链成熟 |
| GNAP | 暂不需要。适合多跳委托链和跨组织场景，当前不涉及 |

OAuth 2.1 vs 2.0 的关键区别：PKCE 强制要求、删除 Implicit Flow 和 Password Flow、Refresh token 轮换。

## 模块设计

### agent_policy.py

定义每个 Agent 的能力集合（Layer 1 的代码侧映射）：

```python
# 示例：某个 agent 被允许使用的工具和 MCP server
AGENT_POLICIES = {
    "hr-agent": {
        "tools": ["search_employee", "read_policy_doc"],
        "mcp_servers": ["hr-system", "confluence"],
    },
    "finance-agent": {
        "tools": ["read_financial_data", "generate_report"],
        "mcp_servers": ["finance-db"],
    },
}
```

### user_grant.py

管理用户的 OAuth 委托（Layer 2）：

- 存储每个用户对每个 MCP server 的 access token（按 user_id 隔离）
- 判断是否需要发起 OAuth 流程（token 不存在或已过期）
- token refresh 逻辑

## 运行时流程

```
用户请求 → agent_policy 检查工具是否在 Agent 能力集内
              ↓ 是
           user_grant 检查是否需要用户授权
              ↓ 有 token 或不需要授权
           dispatch 工具 / 调用 MCP Server
```

## 多用户数据隔离

token 按 user_id 存储：

```
data/users/{user_id}/grants/{mcp_server_id}/token.json
```

每个用户的授权完全隔离，不同用户的 token 不互相可见。
