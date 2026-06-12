# im-gateway

> 写作提醒：功能描述只写可观察的行为，不写内部实现细节。验收标准只写端到端可验证的行为。

## 概述

负责多 IM 平台的接入、消息归一化和用户身份映射。将各平台差异屏蔽在 gateway 层，上层只处理 NormalizedMessage。

**负责**：多 IM 平台接入（Slack / Telegram）、NormalizedMessage 消息归一化、(platform, platform_user_id) → 内部 User 身份映射、Allowlist 审批检查、agent 解析优先级（channel → user → default → 裸跑）、审批命令直接路由。

**不负责**：agent 逻辑与工具调用（→ agent_loop）、用户账号管理（→ user_store）、消息持久化（→ session_mgr）、session 生命周期（→ session）。

**调用关系**：
- 依赖：im_user_store、agent_store、agent_loop、`fleetent.governance.permission_gate`
- 被依赖：无（入口层）

## 现状

- ✅ **NormalizedMessage 归一化**：统一消息格式，包含 platform、session_id、user_id、text、channel_id、reply_func
  - reply_func 是平台相关的回写函数，agent_loop 不感知平台细节

- ✅ **Slack Socket Mode 适配器**：slack-bolt 接入，实时接收消息
  - 支持 DM 和频道消息
  - `session_id` 推导：DM → `"user:{slack_user_id}"`；有 thread_ts 的群聊 → `"thread:{thread_ts}"`；无 thread 的频道消息 → `"user:{slack_user_id}"`（bot 强制在 thread 中回复）

- ✅ **Telegram polling 适配器**：python-telegram-bot 接入
  - `session_id` 推导：私聊 → `"user:{telegram_user_id}"`；群组 reply chain → `"thread:{message_id}"`

- ✅ **IM 用户身份映射**：
  - managed 模式：platform 在 startup 注入 resolver，把 `(platform, platform_user_id)` 归并到内部 `users.id`；首次见到自动创建 `users` + `im_users` 绑定，同一 `(platform, platform_user_id)` 跨 connector 复用同一 internal user
  - standalone 模式：不注入 resolver，恒等透传渠道原生 id；行为与受管模式显式区分

- ✅ **Allowlist 检查**：收到消息时校验用户是否已允许
  - IM 身份默认 `allowed=1`；准入主要由 channel allowlist 控制
  - 被 block 的 IM 身份请求不进入 agent_loop
  - HTTP API 用户（无 im_users 记录）默认放行

- ✅ **Agent 解析优先级**：channel → user → default → 裸跑
  - 裸跑：使用默认 system prompt，全部工具可用

- ✅ **审批命令路由**：用户发送 "approve {id}" 或 "reject {id}"
  - 直接路由到 `fleetent.governance.permission_gate.resolve()`，不经过 agent_loop

- ✅ **HTTP API channel 绑定**：透传 x-platform / x-channel-id 请求头
  - 支持通过 HTTP API 模拟 IM 场景的 channel 绑定

## 数据模型

```sql
im_users (
  id               INTEGER PRIMARY KEY,
  owner_id         TEXT,              -- connector identity（当前为 agent_name）
  platform         TEXT,              -- "slack" | "telegram"
  platform_user_id TEXT,
  user_id          TEXT,              -- → users.id
  allowed          BOOLEAN,
  created_at       DATETIME,
  UNIQUE(owner_id, platform, platform_user_id)
)
```

## 规划中（v1.0）


### 入站消息模型

- [ ] **被回复消息回填**：用户引用某条历史消息时，把被引用消息的文本作为上下文一起送进 agent_loop

- [ ] **聊天元数据**：消息携带 chat_type（dm / group / channel / thread）、chat_name、user_name、guild_id、thread_id、message_id、原始消息引用

- [ ] **Agent 控制命令**：支持 hermes 风格的会话控制命令（/new 重置 session、/stop 停止当前工作、/retry、/undo、/resume 恢复历史 session、/approve、/deny 审批、/status、/help 等），由统一命令注册表管理，gateway 直接分发不进 agent_loop，便于将来同步到平台原生 slash UI

### 出站能力

- [ ] **发送结果对象**：reply_func 返回 SendResult（带 message_id、success、error），供后续编辑、撤回、reaction 使用

- [ ] **消息编辑**：agent 可改写自己刚发出的消息（错答订正、状态更新）

- [ ] **消息撤回**：agent 可删除自己发出的消息

- [ ] **Typing indicator**：长时间工具调用期间，向用户持续展示"输入中"状态

- [ ] **富媒体发送**：可回发图片、视频、音频、语音、文档、动画

- [ ] **多图相册**：一次发送多张图片作为一组

- [ ] **Ephemeral 消息**：仅当前用户可见的临时消息（错误提示、帮助、调试信息）

- [ ] **交互按钮 / 卡片**：发送带按钮或卡片的消息，供审批、选择、确认场景使用

- [ ] **Reaction**：对消息添加 emoji 反应，可作为审批 / 确认的轻量 UI

- [ ] **长消息分片**：超过平台单条上限时按 word 或代码块边界自动分片，附带 (1/N) 续标

- [ ] **连贯性**：回复总是回复到消息列里，不要回复到公屏（可配置）。

### 流式输出

- [ ] **增量回复**：agent_loop 在工具调用中间就把已生成内容推到 IM，用户不必等到整轮结束才看到第一行

- [ ] **工具进度可见性**：工具调用开始 / 进行中 / 结束作为可观察事件呈现给用户（占位 + 编辑或独立消息）

- [ ] ～～**Flood-control 退避**：编辑频率过高时自适应降频，避免被平台限流～～

- [ ] **思考标签过滤**：模型 `<think>` / `<reasoning>` 等内部段不流式给用户

### 会话与线程语义

- [ ] **chat_type 分支策略**：dm / group / channel / thread 分别有独立的 session 派生与回复策略

- [ ] **群内多用户隔离**：公屏session/ 消息列session/ dm session 3个级别。

- [ ] **群聊触发策略**：群里默认仅在 @bot 或回复 bot 时响应，可按 channel 配置

### 身份、权限、审批

- [ ] **Pairing 自助申请**：用户发申请码自助请求接入，带 TTL、频控、连续失败 lockout

- [ ] **Slash 命令分级权限**：区分 admin / 普通用户 / 按命令白名单，DM 与群聊各有策略

### 运维与可观测

- [ ] **平台连接状态可观测**：/health 或专用接口暴露各平台 bot 的连接 / 断开 / fatal 状态与最近错误

- [ ] **致命错误捕获**：适配器层捕获不可恢复错误并上报，区分可重试与需人工介入

- [ ] **断线重连退避**：流式连接断开后按指数退避 + 抖动重连，并在状态中体现

- [ ] **频道目录缓存**：定期刷新可达频道 / DM 列表，主动外发与 cron 可按名字反查 chat_id

- [ ] **跨通道 mirror**：出站消息可写入对应 session 的 transcript，cron / 外部触发的回复也能被会话历史看到

- [ ] **敏感 ID 脱敏**：日志中的手机号、token、邮箱、平台用户 ID 按统一规则脱敏

- [ ] **平台代理配置**：每个适配器可独立配置 HTTP / SOCKS 代理与 NO_PROXY 白名单

- [ ] **入站媒体 SSRF 防护**：下载入站媒体前校验 URL，拦截回环 / 私网 / 云元数据地址，并对重定向链复核

- [ ] **平稳停机 / takeover**：进程退出或被替换时不丢正在处理的消息，重启后能恢复未完成的会话

- [ ] **卡死 session 检测**：超过阈值仍未完成的会话被识别并安全释放，避免 IM 永远卡在"输入中"

### 生命周期与扩展点

- [ ] **WhatsApp 适配器**：接入 whatsapp-cloud-api，复用上述抽象与 normalizer pipeline

## 验收标准

**场景 1：新用户首次发消息（managed）**
- Given：一个从未发过消息的 Slack 用户
- When：用户发送任意消息
- Then：gateway 解析到内部 `users.id`，自动创建 `im_users` 绑定，消息继续按 channel allowlist 规则处理

**场景 1b：新用户首次发消息（standalone）**
- Given：一个 standalone agent 上从未发过消息的 Telegram 用户
- When：用户发送任意消息
- Then：`user_id` 直接等于渠道原生 id，不读取 platform 身份表

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

**场景 5：平台不支持某能力时自动降级**
- Given：一个声明不支持 reaction 的平台
- When：`fleetent.governance.permission_gate` 试图用 reaction 审批
- Then：自动降级到按钮或纯文字 approve，不抛出 SDK 异常

**场景 6：agent 主动向指定频道发消息**
- Given：bot 已加入名为 #ops 的频道，且无历史会话
- When：cron 任务调用 send_message 工具，target 指向 #ops
- Then：消息抵达 #ops 频道，且在该会话历史中可见

**场景 7：入站图片被工具读取**
- Given：已审批用户在 IM 发送一张图片
- When：agent 调用 vision 工具引用该附件
- Then：NormalizedMessage 标记为 photo 类型，工具能从本地路径读取图片并返回分析结果

**场景 8：被回复消息上下文回填**
- Given：用户引用一条历史消息发送新内容
- When：agent_loop 收到该消息
- Then：被引用消息文本作为上下文出现在 agent 看到的对话中

**场景 9：群里仅 @bot 触发（可配置）**
- Given：群聊配置为"仅 @bot 才响应"
- When：群内出现非 @bot 的普通消息
- Then：bot 不进入 agent_loop，不产生回复；@bot 的消息进入 agent_loop 后 @bot 字样从 text 中剥离

**场景 10：/new 重置 session**
- Given：用户和 bot 已有多轮对话
- When：用户发送 /new
- Then：当前 session 被清空，下一条消息开启新 session；本条命令不触发 LLM 调用

**场景 11：/stop 停止当前工作**
- Given：agent 正在执行长工具调用
- When：用户发送 /stop
- Then：当前工具被中断，agent 立即停止，并向用户确认已停止

**场景 12：agent 编辑已发消息**
- Given：agent 已发出占位消息"思考中…"
- When：工具结果就绪，agent 调用编辑接口
- Then：原消息内容被替换为最终回复，不产生新消息

**场景 13：agent 撤回已发消息**
- Given：agent 发出消息后判定内容有误
- When：agent 调用撤回
- Then：用户侧该消息消失或显示为"已撤回"

**场景 14：长任务展示 typing**
- Given：agent 在执行一个超过 5 秒的工具调用
- When：工具执行期间
- Then：用户在 IM 持续看到"输入中"提示，直到最终回复发出

**场景 15：agent 回发媒体**
- Given：agent 调用 send_image / send_document 工具
- When：工具执行成功
- Then：用户在 IM 收到对应附件，而非附件 URL 文本

**场景 16：ephemeral 消息仅发送者可见**
- Given：agent 在群里触发 ephemeral 帮助提示
- When：消息发出
- Then：仅触发的用户能看到，群内其他成员不可见

**场景 17：按钮审批**
- Given：agent 触发 medium 风险工具
- When：`fleetent.governance.permission_gate` 等待审批
- Then：审批人收到带"批准/拒绝"按钮的消息，点击后工具继续或中止；不需要打字 approve

**场景 18：长消息分片**
- Given：agent 输出超过平台单条上限的回复，且含大量 emoji（按 Python len 未超限但 UTF-16 超限）
- When：消息发送
- Then：自动按词或代码块边界拆成 N 条消息，附带 (1/N) 续标，无单条被平台拒绝

**场景 19：增量流式回复**
- Given：agent 正在生成一段较长的回复
- When：模型流式输出
- Then：用户在生成结束前就能看到部分内容，最终消息平滑收尾，过程中不出现重复或跳变

**场景 20：模型 think 段不流给用户**
- Given：模型输出包含 `<think>…</think>` 段
- When：流式呈现到 IM
- Then：用户看到的内容不含 think 标签及其内部文字

**场景 21：thread 内共享 session**
- Given：用户在 Slack / Telegram 某个 thread 内多轮对话
- When：thread 内继续发消息
- Then：所有 thread 内消息共享同一 session，与频道顶层及其他 thread 互不串扰

**场景 22：/health 暴露平台运行状态**
- Given：多个平台适配器在运行，其中一个平台 token 无效
- When：访问 /health
- Then：返回每个平台的 ok/fail

**场景 23：断线后指数退避重连**
- Given：平台网络瞬断
- When：适配器检测到断线
- Then：按指数退避 + 抖动重连，恢复后状态变回 connected，期间不刷屏报错

**场景 24：频道目录按名字反查**
- Given：bot 已加入多个频道，目录已刷新
- When：agent 调用 send_message_tool 指定 target="#ops"
- Then：工具从目录解析出对应 chat_id 并发送成功

**场景 25：SIGTERM 不丢消息**
- Given：进程正在处理一条消息
- When：收到 SIGTERM 或被新进程替换
- Then：该消息处理完后再退出，新进程不会重复处理这条消息

## 待决问题

- [ ] WhatsApp 接入时间节点（负责人：待认领）
