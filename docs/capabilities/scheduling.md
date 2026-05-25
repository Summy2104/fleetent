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

## 规划中

### 定时任务

- [ ] **完整 CRUD 入口**：用户对话和系统命令均可创建、编辑、删除、查询定时任务
  - 对话入口：通过 schedule_task / edit_task / cancel_task / list_tasks 工具
  - 系统命令入口：`fleetent-admin task create/edit/cancel/list`
  - 编辑支持修改 cron 表达式、消息内容、绑定 agent，修改立即生效

- [ ] **结构化输出**：每次定时任务触发后，agent 回复以结构化格式写入执行记录
  - 字段：task_id、triggered_at、status（success / failed）、reply、error（若失败）

- [ ] **失败重试与幂等**：触发失败时按配置重试，防止重复执行
  - 支持配置最大重试次数和重试间隔
  - 每次触发携带唯一 execution_id，重复投递时幂等跳过
  - 失败超过重试上限后保留完整失败日志，不静默丢弃

- [ ] **完整执行日志**：每次触发（无论成功或失败）均写入持久化日志
  - 字段：task_id、execution_id、triggered_at、finished_at、status、retry_count、reply、error
  - 支持通过 `fleetent-admin task logs --id <task_id>` 查询某任务的历史执行记录
  - 支持按状态过滤：`--status failed`

### Webhook

- [ ] **请求携带标识字段**：每条 Webhook 请求包含 task_id、session_id、user_id
  - task_id 用于关联执行记录；session_id 用于上下文追踪；user_id 用于权限路由

- [ ] **异步处理**：收到请求立即返回 202 Accepted，agent 执行在后台进行
  - 不阻塞调用方，主流程不受 agent 执行时长影响

- [ ] **多种认证方式**：来源认证支持三种方式，按来源配置选择
  - HMAC-SHA256 签名验证（现有，增强为可配置算法）
  - API Token：请求头携带 `X-Api-Token`，与来源配置中的 token 比对
  - IP 白名单：来源配置中指定允许的 IP 或 CIDR，不在名单内返回 403

- [ ] **失败重试与幂等**：与定时任务共享机制
  - Webhook 请求携带 `X-Idempotency-Key`，相同 key 的重复请求幂等跳过
  - agent 执行失败时按配置重试，超限后记录失败日志

- [ ] **结构化输出**：agent 执行结果以结构化格式记录
  - 字段：source_id、task_id、session_id、received_at、status、reply、error（若失败）

- [ ] **完整执行日志**：每条 Webhook 请求（无论成功或失败）均写入持久化日志
  - 字段：source_id、task_id、session_id、received_at、finished_at、status、retry_count、reply、error
  - 支持通过 `fleetent-admin webhook logs --source <source_id>` 查询某来源的历史请求记录
  - 支持按状态过滤：`--status failed`

- [ ] **双向回调**：agent 执行完成后主动回调调用方
  - 来源配置中指定 callback_url；回调携带 task_id、status、reply
  - 回调失败时记录日志，不影响本次执行结果

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

## 验收标准（规划）

**场景 5：对话创建定时任务**
- Given：用户对话"每周一早上 8 点提醒我写周报"
- When：agent 调用 schedule_task 工具
- Then：任务创建成功，list_tasks 可查到，server 重启后仍存在

**场景 6：系统命令编辑定时任务**
- Given：已存在 task_id=t001，cron 为每天 9 点
- When：`fleetent-admin task edit --id t001 --cron "0 10 * * *"`
- Then：下次触发时间变为每天 10 点，无需重启服务

**场景 7：定时任务失败重试**
- Given：任务配置最大重试 3 次，第 1 次执行因 API 超时失败
- When：自动重试
- Then：最多重试 3 次；全部失败后失败日志保留，包含 execution_id、error、每次重试时间

**场景 8：定时任务幂等**
- Given：相同 execution_id 的触发请求因网络抖动被投递两次
- When：第二次投递到达
- Then：第二次被幂等跳过，agent 仅执行一次

**场景 9：Webhook 请求字段**
- Given：来源配置了 user_id=alice、agent_name=ops-bot
- When：POST /webhook/{source_id} 请求到达
- Then：执行记录中包含 task_id、session_id、user_id=alice

**场景 10：Webhook 异步返回**
- Given：agent 执行预计耗时 5 秒
- When：POST /webhook/{source_id}
- Then：立即返回 202 Accepted，不等待 agent 执行完成

**场景 11：API Token 认证**
- Given：来源配置 auth=api_token，token=secret123
- When：请求头携带 `X-Api-Token: secret123`
- Then：认证通过，agent 被触发；token 错误返回 403

**场景 12：IP 白名单认证**
- Given：来源配置 auth=ip_whitelist，允许 192.168.1.0/24
- When：来自 192.168.1.50 的请求到达
- Then：认证通过；来自 10.0.0.1 的请求返回 403

**场景 13：Webhook 幂等**
- Given：调用方携带 `X-Idempotency-Key: evt-abc123` 重发同一请求
- When：第二次请求到达
- Then：返回 202，agent 不重复执行

**场景 14：双向回调**
- Given：来源配置了 callback_url=https://example.com/hook
- When：agent 执行完成
- Then：向 callback_url POST 请求，body 包含 task_id、status=success、reply 内容

**场景 15：结构化执行记录**
- Given：Webhook 触发一次成功执行
- When：查询执行记录
- Then：记录包含 source_id、task_id、session_id、received_at、status=success、reply

**场景 16：定时任务完整执行日志**
- Given：task_id=t001 历史触发 5 次，其中第 3 次失败并重试 2 次后成功
- When：`fleetent-admin task logs --id t001`
- Then：输出 5 条记录，每条含 execution_id、triggered_at、finished_at、status、retry_count；第 3 条 retry_count=2、含 error 字段

**场景 17：定时任务日志按状态过滤**
- Given：task_id=t001 历史有 10 次执行，3 次失败
- When：`fleetent-admin task logs --id t001 --status failed`
- Then：仅返回 3 条失败记录

**场景 18：Webhook 完整执行日志**
- Given：source_id=github 历史收到 20 条请求，4 条执行失败
- When：`fleetent-admin webhook logs --source github`
- Then：输出 20 条记录，每条含 task_id、session_id、received_at、finished_at、status、retry_count

**场景 19：Webhook 日志按状态过滤**
- Given：source_id=github 历史 20 条请求中有 4 条失败
- When：`fleetent-admin webhook logs --source github --status failed`
- Then：仅返回 4 条失败记录，每条含 error 字段

## 待决问题

- [ ] 失败日志的保留策略：条数上限还是时间上限？（负责人：待认领）
- [ ] 双向回调失败是否重试？重试策略与主任务是否共用？（负责人：待认领）
- [ ] task_id 的生成方式：服务端生成还是调用方传入？（负责人：待认领）
