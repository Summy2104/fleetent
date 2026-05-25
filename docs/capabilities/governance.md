# governance

> 写作提醒：功能描述只写可观察的行为，不写内部实现细节。验收标准只写端到端可验证的行为。

## 概述

agent 的治理层：控制谁能用哪些工具、高风险操作需要人工确认、agent 能力边界定义与分配。

**调用关系**：
- 依赖：agent_store、agent_policy、permission_gate、im_user_store
- 被依赖：agent_loop（工具访问检查、审批门）、normalizer（agent 解析）

## 现状

- ✅ **人工审批门**：高风险工具调用暂停，等待人工确认
  - medium：发起人自己确认，超时 300s
  - high：预配置 approver 确认，超时 3600s
  - 审批 ID 通过 reply_func 通知用户

- ✅ **审批命令**：用户发送 "approve {id}" / "reject {id}"，或调用 POST /approvals/{id}/resolve

- ✅ **孤儿请求清理**：server 启动时调用 cleanup_stale_approvals()，将 pending 状态重置

- ✅ **Agent 定义**：每个 agent 有 name、system_prompt、allowed_tools 白名单
  - allowed_tools 支持 fnmatch 通配符（如 `read_*`、`github__*`）

- ✅ **工具访问控制**：dispatch 时检查 tool_name 是否匹配 allowed_tools
  - 不在白名单的工具调用直接拒绝，返回错误给 LLM

- ✅ **用户-Agent 绑定**：管理员可将指定 agent 分配给指定用户
- ✅ **Channel-Agent 绑定**：管理员可将指定 agent 绑定到指定 IM channel
- ✅ **默认 Agent**：config.default_agent_name 设置全局默认，无绑定时使用

## 规划中（v1.0）

- [ ] **审批记录查询**：管理员可查询历史审批记录（发起人、工具、时间、决策）

- [ ] **工具使用审计日志**：每次工具调用记录到可查询的审计日志
  - 区别于 traces.jsonl，审计日志面向合规查询

## 验收标准

**场景 1：高风险工具触发审批**
- Given：write_file 的 risk_level="medium"
- When：agent 准备调用 write_file
- Then：执行暂停，用户收到审批通知（含 approval_id）；approve 后继续执行，reject 后取消

**场景 2：工具访问控制**
- Given：agent allowed_tools = ["read_*"]
- When：LLM 尝试调用 write_file
- Then：tool_registry 拒绝调用，返回"工具不可用"给 LLM

**场景 3：Agent 解析优先级**
- Given：channel 有绑定 agent，用户也有绑定 agent
- When：IM 消息到达
- Then：使用 channel 绑定的 agent（channel 优先于 user）

**场景 4：server 重启清理孤儿**
- Given：有 pending 状态的审批请求，server 重启
- When：server 启动完成
- Then：pending 请求状态更新为 expired，不阻塞新请求

## 待决问题

- [ ] 工具审计日志的存储格式和查询方式（负责人：待认领）
