# scheduling

> 写作提醒：功能描述只写可观察的行为，不写内部实现细节。验收标准只写端到端可验证的行为。

## 概述

主动触发机制：定时任务（Cron）和外部事件驱动（Webhook）。让 agent 不只是被动响应，也能主动发起任务。

**调用关系**：
- 依赖：schedule_store、agent_loop、webhook_router、normalizer
- 被依赖：server.py（Webhook 路由）、APScheduler（Cron 触发）

## 现状

- ✅ **APScheduler 定时任务**：server 启动时初始化，支持 cron 表达式
  - schedule_task 工具：创建定时任务，指定 cron 表达式、agent、消息内容
  - cancel_task 工具：取消指定任务
  - list_tasks 工具：查看当前所有任务

- ✅ **定时任务持久化**：任务定义存 SQLite，server 重启后自动恢复

- ✅ **Webhook 接入**：POST /webhook/{source_id} 接收外部事件
  - 来源配置：config/webhooks.yaml，支持 id、user_id、secret、agent_name、message_template

- ✅ **HMAC-SHA256 签名验证**：防止伪造请求
  - 来源未配置 secret 时跳过验签，直接放行（信任内网来源）
  - 签名不匹配返回 403

- ✅ **消息提取**：支持 message_template 从 payload 中提取字段
  - 模板提取失败时降级为 JSON 序列化整个 payload

## 规划中（v1.0）

- [ ] **Webhook 来源热重载**：修改 webhooks.yaml 后无需重启服务即可生效

- [ ] **定时任务执行历史**：记录每次触发的执行时间、结果、是否成功
  - 支持通过 admin CLI 查询历史

## 验收标准

**场景 1：创建定时任务**
- Given：agent 支持 schedule_task 工具
- When：用户请求"每天早上 9 点发送日报"
- Then：任务创建成功，server 重启后仍然存在，到时间自动触发

**场景 2：Webhook 触发 agent**
- Given：配置了来源 id=github，secret=xxx，agent_name=dev-bot
- When：GitHub 发送 POST /webhook/github，签名正确
- Then：dev-bot 收到提取后的消息内容，执行并回写结果

**场景 3：签名验证失败**
- Given：来源配置了 secret
- When：请求的签名不正确
- Then：返回 403，不触发 agent

**场景 4：无 secret 来源**
- Given：来源未配置 secret（内网服务）
- When：发送 POST /webhook/{source_id}
- Then：跳过签名验证，直接触发 agent

## 待决问题

- [ ] 定时任务执行历史的保留策略（条数上限 or 时间上限）（负责人：待认领）
