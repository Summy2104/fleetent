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

- [ ] **任务类型**：支持三种触发模式
  - **一次性任务**：指定未来某个时间点触发一次，执行后自动标记为 done
  - **固定间隔任务**：每隔 N 秒 / 分钟 / 小时触发一次（如"每 30 分钟巡检一次"）
  - **Cron 任务**：标准五字段 cron 表达式，支持复杂周期（现有能力，补充到类型体系中）

- [ ] **时区支持**：任务按指定时区运行，创建时可设置 timezone
  - 默认 UTC，支持任意 IANA 时区（如 `Asia/Shanghai`）
  - list_tasks 输出中展示本地时间和时区

- [ ] **任务绑定**：每个任务记录所属上下文
  - 必填：`agent_name`（指定由哪个 agent 执行）、投递目标（主频道 channel 或私聊 DM）
  - 可选：`user_id`（标记该任务归属哪个用户，用于权限过滤和查询）、`session_id`（复用已有会话上下文，未指定时新建会话）

- [ ] **完整 CRUD 入口**：用户对话和系统命令均可创建、编辑、删除、查询定时任务
  - 对话入口：通过 schedule_task / edit_task / cancel_task / list_tasks 工具
  - 系统命令入口：`fleetent-admin task create/edit/cancel/list`
  - 编辑支持修改触发规则、消息内容、绑定 agent / 用户 / 会话，修改立即生效

- [ ] **暂停与恢复**：任务可在不删除的情况下暂停，之后可恢复
  - 对话：`pause_task` / `resume_task` 工具
  - CLI：`fleetent-admin task pause --id <task_id>` / `fleetent-admin task resume --id <task_id>`
  - 暂停期间到点不触发，恢复后按原规则继续

- [ ] **单次手动触发**：无论任务状态如何，立即触发一次执行（不影响原有调度）
  - CLI：`fleetent-admin task run --id <task_id>`
  - 对话：`run_task` 工具

- [ ] **路由预览**：创建或编辑任务后，可预览接下来 N 次触发时间
  - CLI：`fleetent-admin task preview --id <task_id> [--n 5]`
  - 输出按任务时区显示

- [ ] **任务定义存文件，Git 管理**：任务定义以 YAML 文件形式存储于 `config/tasks/`，纳入 Git 版本控制
  - 运行时状态（上次触发时间、执行次数、暂停标志）单独存 SQLite，重启不丢
  - 文件变更（新增 / 修改 / 删除）在服务启动时自动同步到调度器
  - SQLite 中的状态以 task_id 为 key 关联，文件删除后对应状态自动清理

- [ ] **结构化输出**：每次定时任务触发后，agent 回复以结构化格式写入执行记录
  - 字段：task_id、execution_id、triggered_at、finished_at、status（success / failed）、reply、error（若失败）

- [ ] **失败重试与幂等**：触发失败时按配置重试，防止重复执行
  - 支持配置最大重试次数和重试间隔
  - 每次触发携带唯一 execution_id，重复投递时幂等跳过
  - 失败超过重试上限后保留完整失败日志，不静默丢弃

- [ ] **失败兜底**：重试耗尽后触发兜底处理，确保不静默丢失
  - 兜底方式可在任务配置中选择（可组合）：
    - `fallback_channel`：将错误信息投递到指定频道或私聊
    - `dead_letter`：写入死信队列文件 `data/dead_letter.jsonl`，支持人工重放
  - 兜底触发后在执行日志中标记 `status=dead_lettered`

- [ ] **完整执行日志**：每次触发（无论成功或失败）均写入持久化日志
  - 字段：task_id、execution_id、triggered_at、finished_at、status、retry_count、reply、error
  - 支持通过 `fleetent-admin task logs --id <task_id>` 查询某任务的历史执行记录
  - 支持按状态过滤：`--status failed`

### Webhook

- [ ] **官方平台 Webhook 适配**：内置对主流平台官方 Webhook 格式的解析与验签，开箱即用
  - **Slack**：支持 Slack Events API（`X-Slack-Signature` + `X-Slack-Request-Timestamp` 验签）和 Slash Command；自动处理 URL verification challenge
  - **GitHub**：支持所有 GitHub Webhook 事件（`X-Hub-Signature-256` 验签）；event type 通过 `X-GitHub-Event` 头路由，可在配置中按 event 筛选触发
  - 每个平台作为独立 source type，在 `config/webhooks.yaml` 中声明 `type: slack` / `type: github`，由框架自动套用对应解析逻辑，无需手动写 message_template

- [ ] **请求携带标识字段**：每条 Webhook 请求包含 task_id、session_id、user_id
  - task_id 用于关联执行记录；session_id 用于上下文追踪；user_id 用于权限路由

- [ ] **异步处理**：收到请求立即返回 202 Accepted，agent 执行在后台进行
  - 不阻塞调用方，主流程不受 agent 执行时长影响

- [ ] **多种认证方式**：来源认证支持三种方式，按来源配置选择
  - HMAC-SHA256 签名验证（现有，增强为可配置算法）；官方平台适配器使用各自签名规范
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

- [ ] **失败兜底**：重试耗尽后触发兜底处理，确保不静默丢失
  - 兜底方式可在来源配置中选择（可组合）：
    - `fallback_channel`：将原始 payload 和错误信息投递到指定频道或私聊
    - `fallback_webhook`：转发到另一个 Webhook URL（如告警系统）
    - `dead_letter`：写入死信队列文件 `data/dead_letter.jsonl`，支持人工重放
  - 兜底触发后在执行日志中标记 `status=dead_lettered`

- [ ] **路由预览**：在不实际触发 agent 的情况下，验证 Webhook 配置是否正确
  - CLI：`fleetent-admin webhook preview --source <source_id> --payload <file.json>`
  - 输出：匹配的 source、认证方式、提取的消息内容、将触发的 agent，以及若配置有误的具体原因
  - 用于上线前验证配置，排查 message_template 提取逻辑是否符合预期

- [ ] **双向回调**：agent 执行完成后主动回调调用方
  - 来源配置中指定 callback_url；回调携带 task_id、status、reply
  - 回调失败时记录日志，不影响本次执行结果

## 验收标准

### 现状

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

### 规划

**场景 5：一次性任务**
- Given：用户对话"明天下午 3 点提醒我开会"
- When：agent 调用 schedule_task 工具，type=once，at=明天 15:00
- Then：到时触发一次，执行后状态变为 done，不再触发

**场景 5a：固定间隔任务**
- Given：用户对话"每 30 分钟检查一次服务状态"
- When：agent 调用 schedule_task 工具，type=interval，every=30m
- Then：每隔 30 分钟触发，list_tasks 可查到下次触发时间

**场景 5b：时区运行**
- Given：创建任务 cron="0 9 * * 1"，timezone=Asia/Shanghai
- When：北京时间周一 09:00
- Then：任务触发；UTC 时间 01:00 不触发

**场景 5c：任务绑定用户和 agent**
- Given：创建任务时指定 user_id=alice、agent_name=support-bot、target=dm
- When：任务触发
- Then：support-bot 执行，归属用户=alice，消息投递到 alice 私聊

**场景 5d：任务绑定频道**
- Given：创建任务时指定 channel_id=C123、target=channel
- When：任务触发
- Then：执行结果投递到频道 C123，不发私聊

**场景 5e：暂停与恢复**
- Given：task_id=t001 每天 9 点触发
- When：执行 `fleetent-admin task pause --id t001`，等待过了 9 点
- Then：该时间点不触发；执行 `resume` 后恢复，下次到时间正常触发

**场景 5f：单次手动触发**
- Given：task_id=t001 处于暂停状态
- When：执行 `fleetent-admin task run --id t001`
- Then：立即触发一次执行；任务仍保持暂停状态，原调度不受影响

**场景 5g：路由预览**
- Given：task_id=t001，cron="0 9 * * 1-5"，timezone=Asia/Shanghai
- When：执行 `fleetent-admin task preview --id t001 --n 5`
- Then：输出接下来 5 次触发的北京时间，格式清晰

**场景 5h：任务定义 Git 管理**
- Given：在 config/tasks/ 新增一个 YAML 文件定义任务，提交到 Git
- When：服务重启
- Then：新任务自动加载并开始调度，无需手动创建

**场景 5i：运行状态重启不丢**
- Given：task_id=t001 已执行 10 次，最后触发时间为 T
- When：服务重启
- Then：list_tasks 仍显示执行次数=10、最后触发时间=T，任务恢复调度

**场景 5j：对话创建定时任务**
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

**场景 7a：定时任务失败兜底——投递到频道**
- Given：任务配置 fallback_channel=C-alert，最大重试 3 次
- When：agent 执行连续失败 3 次，重试耗尽
- Then：错误信息投递到频道 C-alert；执行日志 status=dead_lettered

**场景 7b：定时任务失败兜底——写入死信队列**
- Given：任务配置 fallback=dead_letter，重试耗尽
- When：agent 执行失败超过上限
- Then：`data/dead_letter.jsonl` 新增一条记录，包含 task_id、execution_id、error

**场景 8：定时任务幂等**
- Given：相同 execution_id 的触发请求因网络抖动被投递两次
- When：第二次投递到达
- Then：第二次被幂等跳过，agent 仅执行一次

**场景 8：官方平台 Webhook 适配——概述**
- Given：配置文件中声明 `type: slack` 或 `type: github`
- When：服务启动
- Then：对应平台的签名验证和消息解析逻辑自动加载，无需手动配置 message_template

**场景 8a：Slack Events API**
- Given：配置 type=slack，secret=xxx；Slack 发送 `app_mention` 事件
- When：POST /webhook/{source_id}，携带正确 `X-Slack-Signature`
- Then：验签通过，agent 收到提取后的消息文本，正常触发；签名错误返回 403

**场景 8b：Slack URL verification**
- Given：首次配置 Slack Events API，Slack 发送 challenge 请求
- When：POST /webhook/{source_id}，body 含 `type=url_verification`
- Then：自动返回 `{"challenge": "..."}` ，无需额外配置

**场景 8c：GitHub Webhook 触发**
- Given：配置 type=github，secret=xxx，event_filter=push
- When：GitHub 推送代码，发送 `X-GitHub-Event: push`，签名正确
- Then：agent dev-bot 被触发，收到 push 事件的结构化摘要

**场景 8d：GitHub 事件过滤**
- Given：配置 event_filter=push，收到 `X-GitHub-Event: pull_request`
- When：请求到达
- Then：返回 200 但不触发 agent（事件类型不匹配，静默忽略）

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

**场景 13a：失败兜底——投递到频道**
- Given：来源配置 fallback_channel=C-alert，最大重试 3 次
- When：agent 执行连续失败 3 次，重试耗尽
- Then：原始 payload 和错误信息投递到频道 C-alert；执行日志 status=dead_lettered

**场景 13b：失败兜底——写入死信队列**
- Given：来源配置 fallback=dead_letter，重试耗尽
- When：agent 执行失败超过上限
- Then：`data/dead_letter.jsonl` 新增一条记录，包含 source_id、task_id、payload、error

**场景 13c：路由预览——配置正确**
- Given：source_id=github，配置 type=github，event_filter=push，agent_name=dev-bot
- When：`fleetent-admin webhook preview --source github --payload push_event.json`
- Then：输出 source=github、auth=hmac、提取的消息摘要、将触发 agent=dev-bot，无报错

**场景 13d：路由预览——配置有误**
- Given：source_id=ops，message_template 引用了 payload 中不存在的字段
- When：`fleetent-admin webhook preview --source ops --payload sample.json`
- Then：输出提取失败原因（字段不存在），并提示将降级为 JSON 序列化全量 payload

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
- [ ] config/tasks/ YAML 文件变更检测方式：仅启动时扫描，还是支持运行时热重载？（负责人：待认领）
- [ ] session_id 绑定语义：复用已有会话上下文，还是每次触发新建会话但注入历史摘要？（负责人：待认领）
