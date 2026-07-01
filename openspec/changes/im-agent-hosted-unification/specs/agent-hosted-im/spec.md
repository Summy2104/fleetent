## ADDED Requirements

### Requirement: agent 全模式自持 IM 连接

agent 运行时 SHALL 在 standalone 与 node-managed **两种模式下均在 agent 进程内**启动自己的 Slack/Telegram supervisor 并持有活连接（Slack Socket Mode / Telegram 轮询），token 从 agent 进程环境变量读取（`agent.yaml` 的 `im.*_env` 指向的名字，由 node materialize 写入 agent `.env`）。managed 模式 SHALL NOT 再向 agent 传 `--no-im`，agent 的 IM 收发路径 SHALL 与 standalone 完全一致。

#### Scenario: managed 下 agent 自起 supervisor
- **WHEN** node 拉起一个声明了 `im.slack` 且其 `*_env` 在 agent `.env` 有值的 agent
- **THEN** 该 agent 进程启动自己的 Slack supervisor 并建立 Socket Mode 连接，入站消息在 agent 进程内经 `normalizer.route` 处理

#### Scenario: 未配置 IM 的 agent 不起连接
- **WHEN** 一个 agent 的 `im.*` token 环境变量未解析（缺值）
- **THEN** supervisor 跳过该 agent、不建立连接、不报错（与 standalone 行为一致）

### Requirement: node 退出 IM 数据面

在 node-managed 部署下，node SHALL NOT 持有任何 IM 接收连接（不启动 Slack/Telegram supervisor）、SHALL NOT 提供 `/im/route` 入站转发、SHALL NOT 运行 IM 出站 drain。node 在 IM 上 SHALL 仅保留 **agent-facing 的 identity/address loopback 代理端点** 与既有进程监督/ materialize 职责。系统 SHALL NOT 让 node 与 agent 同时持有同一 token 的接收连接。

#### Scenario: node 不建立 IM 接收连接
- **WHEN** node reconcile 一批含 IM 声明的 agent
- **THEN** node 自身不打开任何 Slack Socket Mode / Telegram 轮询连接（连接均由各 agent 进程持有）

#### Scenario: 入站不经 node 转发
- **WHEN** 一条 Slack 消息到达某 agent 的连接
- **THEN** 它由该 agent 进程直接接收处理，不经过 node 的 `/im/route`

### Requirement: 单一 managed 运行时判定信号

系统 SHALL 用**单一且确证已投递到 agent 进程**的信号判定 node-managed 运行时；该信号 SHALL 为 agent `.env` 中的 `FLEETENT_NODE_LOOPBACK_URL`。判定 helper SHALL 是全局唯一来源，出站连接器解析、身份 resolver 注入等 SHALL 复用它。系统 SHALL NOT 再用未投递到容器 agent `.env` 的 `FLEETENT_NODE_ID`/`FLEETENT_NODE_PLATFORM_URL`/`FLEETENT_NODE_SERVICE_KEY` 组合来判定 managed。

#### Scenario: 容器 agent 正确识别为 managed
- **WHEN** 容器后端拉起的 agent（`.env` 含 `FLEETENT_NODE_LOOPBACK_URL`、不含 node 三件套）
- **THEN** managed 判定为真，出站与身份注入按 managed 生效

#### Scenario: standalone 判定为非 managed
- **WHEN** `agent run`（无 `FLEETENT_NODE_LOOPBACK_URL`）
- **THEN** managed 判定为假，走 standalone 直路、不注入 loopback resolver

### Requirement: 出站经活连接器直发

在两种模式下，出站投递（文本回复、`send_file`、审批提示）SHALL 经 agent 进程持有的活连接器直发（Slack/Telegram Web API），不经出站队列或 node drain。supervisor SHALL 把活连接器注入 `NormalizedMessage.outbound_connectors`，出站连接器解析 SHALL 在其非空时直接使用。

#### Scenario: send_file 经活连接器交付
- **WHEN** managed agent 生成产物并调用 `send_file` 发回当前对话
- **THEN** 文件经 agent 活连接器以附件形式投递到当前对话（频道线程 / DM），对话中出现可下载文件

#### Scenario: 审批提示经活连接器投递
- **WHEN** managed agent 触发一次中风险审批
- **THEN** 审批提示（含 approve/reject）经 agent 活连接器投递，approve/reject 回复由同一 agent 连接接收并关联回该审批

### Requirement: 出站连接器解析 fail-fast

出站连接器解析 SHALL NOT 在"判定为 managed 却拿不到目标平台连接器"时静默返回空并让交付无声失败。该情形下系统 SHALL 记录 error 级日志（含 platform、agent、managed 信号状态）并使调用方得到明确的失败结果（`send_file` 等工具返回带诊断的错误文案）。

#### Scenario: 缺连接器时显式报错而非静默
- **WHEN** 一次出站在 managed 下解析不到目标平台的活连接器
- **THEN** 记录 error 日志，调用方收到明确失败（非"看似成功但无投递"）

### Requirement: 身份/地址 resolver 经 node loopback 注入 agent

managed 模式下 agent SHALL 经 **node loopback**（`FLEETENT_NODE_LOOPBACK_URL`，以 agent 自身的 `FLEETENT_TUI_TOKEN` 鉴权）调用身份解析与地址反查，agent SHALL NOT 直接持有 node service key、SHALL NOT `import fleetent.platform.*`。node SHALL 暴露 `POST /agent/{name}/identity/resolve` 与 `POST /agent/{name}/identity/addresses`，node 侧补 service key 转发到 platform 对应端点。standalone 模式 SHALL 不注入该 resolver（身份解析退化为使用平台原生 id）。

#### Scenario: managed 入站身份经 loopback 解析
- **WHEN** managed agent 收到入站消息，需要把 `platform_user_id` 解析为内部 `user_id`
- **THEN** agent 经 node loopback `/agent/{name}/identity/resolve`（TUI token 鉴权）取回 `user_id`，node 转发时补 service key 调 platform

#### Scenario: directed-reach 地址经 loopback 反查
- **WHEN** managed agent 调 `notify_user(user_id, ...)`
- **THEN** agent 经 node loopback `/agent/{name}/identity/addresses` 反查该用户全部绑定地址

#### Scenario: agent 不持 service key
- **WHEN** 审计 managed agent 进程环境
- **THEN** 其不含 node service key；对 node 的调用仅用 `FLEETENT_TUI_TOKEN`

### Requirement: managed 与 standalone 行为契约

系统 SHALL 提供契约测试锁定 **managed 行为等价于 standalone**：相同输入下，入站处理、文本回复、`send_file` 交付、审批 approve/reject 往返、directed-reach fan-out 的可观测结果一致。此契约 SHALL 防止两种模式行为再次分叉。

#### Scenario: 交付契约等价
- **WHEN** 在 managed 与 standalone 分别跑同一"生成文件并 send_file"用例
- **THEN** 两者都产出可下载文件交付（无一方静默失败）

#### Scenario: 审批往返契约等价
- **WHEN** 在 managed 与 standalone 分别触发同一中风险审批并 approve
- **THEN** 两者的审批提示投递与批准后续跑行为一致
