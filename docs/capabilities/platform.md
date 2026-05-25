# platform

> 写作提醒：功能描述只写可观察的行为，不写内部实现细节。验收标准只写端到端可验证的行为。

## 概述

多用户管理、API 认证和管理员操作。是 fleetent 作为多租户平台的基础层。

**调用关系**：
- 依赖：user_store、im_user_store、agent_store、config
- 被依赖：server.py（认证）、normalizer（用户查找）、admin CLI

## 现状

- ✅ **Bearer token 认证**：Authorization: Bearer ma-\<64hex\>
  - ma- 前缀区分服务 key 与模型 API key
  - get_by_api_key() 查 SQLite，无外部 IdP

- ✅ **用户管理 CLI**：
  - create-user --name：创建用户，生成 API key
  - list-users：列出所有用户
  - rotate-key --user-id：重置 API key

- ✅ **IM 用户管理 CLI**：
  - approve-user --im-user-id：审批 IM 用户
  - block-user --im-user-id：封禁 IM 用户
  - list-pending：列出待审批用户

- ✅ **Agent 管理 CLI**：
  - assign-channel --platform --channel-id --agent-name：绑定 channel
  - unassign-channel --platform --channel-id：解绑 channel
  - set-default-agent --agent-name：设置默认 agent

## 规划中（v1.0）

- [ ] **API key 权限 scope**：不同 key 可限制可访问的 endpoint 或 agent
  - 场景：只读 key 用于监控，读写 key 用于正常对话

- [ ] **用量配额**：per-user token 用量上限，超限后拒绝请求

## 验收标准

**场景 1：API key 认证**
- Given：有效的 Bearer token
- When：POST /chat
- Then：请求通过认证，正常处理

**场景 2：无效 token**
- Given：错误或过期的 Bearer token
- When：POST /chat
- Then：返回 401

**场景 3：创建用户**
- Given：管理员执行 create-user --name "Alice"
- When：命令执行成功
- Then：输出 API key，Alice 可立即用该 key 调用 /chat

**场景 4：IM 用户审批流程**
- Given：新 Slack 用户发消息（allowed=0）
- When：管理员执行 approve-user --im-user-id {id}
- Then：该用户后续消息正常进入 agent_loop

## 待决问题

- [ ] API key scope 的粒度设计（endpoint 级 vs agent 级）（负责人：待认领）
