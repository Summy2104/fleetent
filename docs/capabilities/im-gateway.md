# im-gateway

> 写作提醒：功能描述只写可观察的行为，不写内部实现细节。验收标准只写端到端可验证的行为。

## 概述

负责多 IM 平台的接入、消息归一化和用户身份映射。将各平台差异屏蔽在 gateway 层，上层只处理 NormalizedMessage。

**调用关系**：
- 依赖：im_user_store、agent_store、agent_loop、permission_gate
- 被依赖：无（入口层）

## 现状

- ✅ **NormalizedMessage 归一化**：统一消息格式，包含 platform、session_id、user_id、text、channel_id、reply_func
  - reply_func 是平台相关的回写函数，agent_loop 不感知平台细节

- ✅ **Slack Socket Mode 适配器**：slack-bolt 接入，实时接收消息
  - 支持 DM 和频道消息
  - session_id = "slack-{channel_id}"

- ✅ **Telegram polling 适配器**：python-telegram-bot 接入
  - session_id = "telegram-{chat_id}"

- ✅ **IM 用户身份映射**：(platform, platform_user_id) → 内部 User
  - 新用户自动创建，默认 allowed=0（待审批）
  - get_or_create() 幂等，不重复创建

- ✅ **Allowlist 检查**：收到消息时校验用户是否已审批
  - 未审批用户收到提示消息，请求不进入 agent_loop
  - HTTP API 用户（无 im_users 记录）默认放行

- ✅ **Agent 解析优先级**：channel → user → default → 裸跑
  - 裸跑：使用默认 system prompt，全部工具可用

- ✅ **审批命令路由**：用户发送 "approve {id}" 或 "reject {id}"
  - 直接路由到 permission_gate.resolve()，不经过 agent_loop

- ✅ **HTTP API channel 绑定**：透传 x-platform / x-channel-id 请求头
  - 支持通过 HTTP API 模拟 IM 场景的 channel 绑定

## 规划中（v1.0）

- [ ] **WhatsApp 适配器**：接入 whatsapp-cloud-api
  - 与 Slack/Telegram 共用 normalizer pipeline
  - session_id = "whatsapp-{phone_number}"

## 验收标准

**场景 1：新用户首次发消息**
- Given：一个从未发过消息的 Slack 用户
- When：用户发送任意消息
- Then：im_user_store 自动创建记录（allowed=0），用户收到"请联系管理员审批"提示

**场景 2：已审批用户正常对话**
- Given：allowed=1 的 Slack 用户
- When：用户发送消息
- Then：消息进入 agent_loop，回复正常返回给用户

**场景 3：channel 绑定 agent**
- Given：channel #ops 已绑定 agent "ops-bot"
- When：任何用户在 #ops 发送消息
- Then：使用 ops-bot 的 system_prompt 和 allowed_tools 处理

**场景 4：审批命令**
- Given：有一个 pending 状态的 approval_id
- When：用户发送 "approve {id}"
- Then：对应的 tool 调用继续执行，用户收到执行结果

## 待决问题

- [ ] WhatsApp 接入时间节点（负责人：待认领）
