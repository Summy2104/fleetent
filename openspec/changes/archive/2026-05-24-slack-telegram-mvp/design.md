## Context

fleetent 已实现：agent loop、streaming、memory、skill registry、context 压缩、HTTP server、user 管理、48 个测试。核心 300 行直接调 SDK，无 LangChain/框架依赖。

本次扩展将 fleetent 从单用户 CLI/HTTP 工具升级为多用户 IM 原生服务，验证"可治理、可部署"核心差异化，为 on-premises 商业化打基础。目标：**1–2 个月内跑通 Slack + Telegram 完整链路**。

## Goals / Non-Goals

**Goals:**
- Slack（Socket Mode）+ Telegram（Long Polling）完整实现，验证跨渠道抽象
- Session 持久化，跨消息保持对话历史
- Sub-agent 并行执行
- 权限门：访问控制（agent.allowed_tools）+ 人工审批（medium/high 两级）
- 工具执行沙盒（microsandbox MicroVM）
- MCP client，透明注册外部工具
- on-premises 单容器部署包

**Non-Goals:**
- WhatsApp（Phase 2）
- OAuth 代理授权（保留接口，实现推迟）
- 管理后台 Web UI（MVP 用 CLI，数据在 DB，后续加 UI 不需要迁移）
- Windows 沙盒支持（降级：Docker + gVisor + seccomp，注明限制）
- 多租户 / SaaS 部署（on-premises 单容器优先）

## Decisions

### 1. Gateway ↔ Runtime：同进程直调

**选择**：IM adapter 作为薄适配层，同进程直接调用 agent_loop，无消息队列。

**理由**：on-premises 单容器，运维最简。gateway 是无状态适配层，I/O 流量远低于 LLM 调用延迟，无需独立进程。消息并发量在企业内网场景不需要 broker。

**舍弃方案**：独立进程 + Redis 队列 — 引入运维复杂度，on-premises 客户安装负担加重。

### 2. Session 模型：User session + Thread session

**选择**：DM → `session_id = "user:{id}"`；群聊 thread → `session_id = "thread:{thread_id}"`。Bot 强制 thread-first 回复。

**理由**：DM 是个人助理上下文，群聊 thread 是团队协作上下文，天然分工。无 thread 的群聊消息由 bot 自动创建 thread 并回复，确保上下文隔离。

**舍弃方案**：群聊全局 session — 多用户混合上下文，历史噪声过大，实用性低。

### 3. Sub-agent：进程内 asyncio.gather

**选择**：`asyncio.gather(*[agent_loop.run(...)])` 并行，无队列，无跨进程通信。

**理由**：工具调用和 LLM 请求是 I/O-bound，asyncio 并行有效。进程内直调无序列化开销，调试简单。

**约束**：Child 使用全新上下文（防 token 随嵌套爆炸），最多两层（防无限嵌套），child 不能再派生 sub-agent。

### 4. 权限门：两层分离

**选择**：Layer 1（访问控制）在 `tool_registry.dispatch()` 层，检查 `agent.allowed_tools`，未授权直接 PermissionError；Layer 2（人工审批门）在 dispatch 通过后，按 risk_level 决定是否等待人工确认。

**理由**：两层职责不同——访问控制是静态配置判断，审批门是动态运行时等待。分层使两者可独立演进。

**审批机制**：`asyncio.Event` 等待 IM 回调，medium（5min 默认）等发起人确认，high（60min 默认）等预配置 approver。超时自动拒绝。

### 5. 沙盒：microsandbox（MicroVM）

**选择**：microsandbox-server 作为宿主机原生守护进程（非 Docker），fleetent 通过 HTTP 连接 `host.docker.internal`。

**理由**：microsandbox 需直接访问 KVM（Linux）或 Hypervisor.framework（macOS M），无法入容器。MicroVM 提供强隔离（内核级），每 session 独立 workspace，跨步骤共享文件。

**降级方案**：客户环境无 KVM 时，Docker + gVisor runtime + seccomp profile，注明安全级别较低。

**舍弃方案**：Docker sidecar / DinD — 容器逃逸风险高，无法提供 per-session 隔离；gVisor 单容器 — 无法在 Docker 内运行，macOS 不支持。

### 6. MCP 工具透明注册

**选择**：启动时 `mcp_client.register_all()` 将 MCP 工具注册进 `tool_registry`，命名 `{server_id}__{tool_name}`（双下划线）。agent_loop 和 LLM 无法区分工具来源。

**理由**：工具来源透明化，agent_loop 无需感知 MCP 协议细节。双下划线前缀避免与本地工具命名冲突，并携带来源信息。

### 7. 数据存储：SQLite + 文件混合

**选择**：SQLite 存关系型运行时数据（users, im_users, agents, user_agents, approvals）；文件存大块内容（sessions JSON, memories JSONL, traces JSONL）；YAML 存静态配置（MCP server 连接信息）。

**理由**：session 历史需要整体读写（context 压缩后覆写），不适合行式存储。agent 配置放 SQLite 支持后续管理后台查询。密钥不进 DB，不进 git。

### 8. 配置：pydantic-settings + env var

**选择**：`config/settings.yaml` + `.env.production`（gitignored），pydantic-settings 类型安全合并。

**理由**：on-premises 多环境部署必备，env var 可覆盖任何 yaml 值，密钥通过 env 注入不触碰文件系统。

## Risks / Trade-offs

- **asyncio 并发安全**：同一 session 的消息必须顺序处理，多 session 可并发。session_mgr 需确保同一 session_id 不并发执行 → 用 `asyncio.Lock` per session_id 保护。
- **microsandbox 依赖宿主机**：客户环境必须支持 KVM 或 Hypervisor.framework；否则降级 gVisor，但安全性降低 → 安装文档明确说明环境要求。
- **MCP server 启动失败**：某个 MCP server 不可达时不应阻塞启动 → 逐个连接，失败的 server 记录警告日志，跳过注册，不中断服务启动。
- **权限门 asyncio.Event 泄漏**：long-running approval 超时后 event 需正确清理 → 用 `asyncio.wait_for` 包装，超时自动取消。
- **Session 文件并发写**：同一 session 的连续消息快速到来时，第一条未保存，第二条已加载 → session 级 Lock 解决，同时 session 内消息顺序处理。

## Open Questions

1. **老板口风**：on-premises 是否正式立项？影响投入节奏和后续资源。
2. **目标服务器 KVM 支持**：第一个内部部署环境是否有 KVM？决定沙盒方案选择。
3. **SaaS 团队技术栈**：确认后决定 memory/eval 共享层的 HTTP API 设计方式。
