> **[历史记录]** 本文档为 2026-05-23 MVP 设计提案，已被后续 wave 决策文档和落地代码取代。内容以 `docs/architecture/` 和 `openspec/changes/archive/` 为准。

# Lean Agent Platform — Slack/Telegram MVP 设计方案

**日期**：2026-05-23
**状态**：Brainstorming 完成，待实施计划
**前置文档**：
- [[2026-05-19-自研Agent平台战略决策]]
- [[2026-05-13-fleetent-项目设计]]

---

## 1. 背景与目标

fleetent（`~/wwwroot/repo/fleetent`）已完成技术验证（agent loop、streaming、memory、skill registry、context 压缩、HTTP server、user 管理、48 个测试）。

本文是在 fleetent 基础上扩展的 **Slack/Telegram MVP 设计方案**，目标：

- **1–2 个月**内在内部跑通 Slack + Telegram 完整链路
- 验证"可治理、可部署"的核心差异化能力
- 为后续 on-premises 商业化打基础

---

## 2. MVP 模块边界

| 模块 | 类型 | 说明 |
|------|------|------|
| IM Gateway（Slack + Telegram 完整）| 新建 | 两个平台完整实现，验证跨渠道抽象 |
| Session persistence | 新建 | 跨消息保持对话历史 |
| Sub-agent | 新建 | asyncio 并行，全新上下文 |
| 权限门 | 新建 | medium / high 两级审批 |
| 工具执行沙盒 | 新建 | microsandbox（macOS M + Linux KVM）|
| Config management | 新建 | pydantic-settings，多环境 |
| DB migration | 新建 | alembic，schema 版本管理 |
| Docker 打包 | 新建 | on-premises 单容器部署 |
| Structlog | 新建 | 结构化日志 |
| IM user → user 映射 | 新建 | 身份识别 |
| Memory layer | 复用现有 | 按 user_id 隔离，无需改动 |
| Eval/trace | 扩展 | 新增 platform / channel_id / message_id / thread_id 字段 |

**明确不在 MVP 的：**
- WhatsApp（Phase 2）
- OAuth 代理授权（留 `user_token` 接口，实现推迟）
- 管理后台 Web UI（MVP 用 CLI，数据在 DB，后续加 UI 不需要迁移）
- 沙盒 Windows 支持（降级方案：Docker + 硬化，注明限制）

---

## 3. 关键架构决策

| 决策点 | 结论 | 理由 |
|--------|------|------|
| Gateway ↔ Runtime | 同进程直调 | on-premises 单容器，运维最简；gateway 是薄适配层，无需独立进程 |
| Session 模型 | User session（DM）+ Thread session（群聊）| DM = 个人，群聊 = 团队协作，天然分工 |
| Sub-agent 通信 | 进程内 asyncio.gather() | I/O-bound 工作用 asyncio 并行有效；无需队列 |
| Sub-agent 上下文 | 全新上下文 | 防止 token 随嵌套爆炸；parent 按需摘要传递背景 |
| 沙盒方案 | microsandbox | macOS M + Linux KVM 统一方案；开发/生产行为一致 |
| 部署结构 | microsandbox 原生 + fleetent Docker | microsandbox 需直接访问 KVM/Hypervisor.framework，无法入容器 |
| 权限门级别 | medium（发起人确认）/ high（预配置 approver）| 企业合规要求"双人操作"；级别在工具注册时声明 |
| 外部系统访问 | 统一走 MCP | MCP server 自管鉴权；平台控制"用户可用哪些 MCP server" |
| 权限模型 | Agent 定义 + 用户分配 | 权限绑定 Agent 而非用户；用户通过 Agent 继承工具集 |
| 密钥安全 | env var + pydantic-settings | 密钥不进 DB，不进 system prompt，不进 git |

---

## 4. 整体架构

```
宿主机
├── microsandbox-server（原生守护进程）
│     └── 管理 per-session MicroVM workspace
└── docker-compose
      └── fleetent 容器
            ├── Slack adapter    ─┐
            ├── Telegram adapter ─┤→ normalizer → session_mgr → agent_loop
            ├── session_mgr        （查找/创建 session，加载/保存历史）
            ├── agent_loop         （while tool-use 循环）
            │     ├── sub_agent    （asyncio.gather 并行，最多两层）
            │     └── permission_gate（暂停等审批，asyncio.Event）
            ├── mcp_client         （启动时注册 MCP 工具 → tool_registry）
            ├── sandbox_client     （HTTP → microsandbox-server）
            ├── config             （pydantic-settings）
            ├── user_store         （SQLite，含 IM user 映射）
            ├── memory_layer       （复用现有）
            ├── eval_logger        （扩展 IM 字段）
            └── FastAPI server     （/chat SSE，/health）
```

**消息流：**

```
Slack/Telegram 事件
  → adapter（归一化 → 统一消息格式）
  → im_users 查找（platform_user_id → 内部 user_id）
  → session_mgr.load(session_id)
  → agent_loop.run(messages=历史 + 新消息)
      → 工具调用 → sandbox_client → MicroVM 执行
      → 高风险工具 → permission_gate → 暂停，IM 消息等确认
      → sub-agent → asyncio.gather(agent_loop.run(...), ...)
  → session_mgr.save(session_id, updated_messages)
  → adapter 回写 Slack/Telegram（thread-first）
```

### 4.1 MCP 工具注册机制

启动时，`mcp_client` 连接 `config/mcp.yaml` 中配置的所有 MCP Server，发现工具列表后注册进 `tool_registry`。`agent_loop` 和 LLM 看不到工具来源，本地工具和 MCP 工具完全透明。

```
服务启动
  → mcp_client.register_all(servers)
      → 连接各 MCP Server（HTTP/SSE）
      → 拉取 tools/list
      → tool_registry.register(name="{server_id}__{tool_name}", handler=mcp_call)
        示例：github__create_issue、linear__create_ticket

agent_loop 调用工具
  → tool_registry.dispatch(tool_name, args)
      → 本地工具：直接执行
      → MCP 工具（名称含 __）：mcp_client.call_tool(server_id, tool_name, args, user_id)
```

模块接口：
- `register_all(servers: list[McpServerConfig], user_id: str)` — 启动时调用
- `call_tool(server_id: str, tool_name: str, args: dict, user_id: str)` — dispatch 层调用

---

## 5. 数据模型

### 5.1 SQLite 表（动态运行时状态 + 管理配置）

```sql
-- 现有，不改
users (id, name, api_key, created_at)

-- 新增：IM 用户映射
im_users (
  id               INTEGER PRIMARY KEY,
  platform         TEXT,              -- "slack" | "telegram"
  platform_user_id TEXT,
  user_id          TEXT,              -- → users.id
  created_at       DATETIME,
  UNIQUE(platform, platform_user_id)
)

-- 新增：Agent 定义
agents (
  id            INTEGER PRIMARY KEY,
  name          TEXT UNIQUE,
  system_prompt TEXT,
  allowed_tools TEXT,                -- JSON 数组：["mcp__github__*", "shell"]
  created_at    DATETIME
)

-- 新增：用户 → Agent 分配
user_agents (
  user_id   TEXT,                    -- → users.id
  agent_id  INTEGER,                 -- → agents.id
  PRIMARY KEY (user_id, agent_id)
)

-- 新增：权限门审批记录
approvals (
  id               INTEGER PRIMARY KEY,
  session_id       TEXT,
  requester_user_id TEXT,            -- → users.id
  risk_level       TEXT,             -- "medium" | "high"
  tool_name        TEXT,
  tool_args        TEXT,             -- JSON
  status           TEXT,             -- "pending" | "approved" | "rejected" | "timeout"
  approver_user_id TEXT,             -- → users.id，可为空（medium 级由发起人确认）
  created_at       DATETIME,
  resolved_at      DATETIME
)
```

### 5.2 文件（大块内容，按 session 隔离）

```
data/
  sessions/{session_id}.json        # 完整对话历史（JSON，context 压缩后覆写）
  users/{user_id}/memories.jsonl    # 跨会话记忆（现有）
  traces.jsonl                      # eval 追踪（现有，扩展 IM 字段）
```

### 5.3 配置文件（静态，admin 手动维护）

```
config/
  mcp.yaml          # MCP server 连接信息（endpoint，凭证，gitignored）
  settings.yaml     # 可选覆盖（permission timeout 等）
```

---

## 6. IM Gateway 设计

### 6.1 统一消息格式

```python
@dataclass
class NormalizedMessage:
    platform:      str            # "slack" | "telegram"
    session_id:    str            # "user:{id}" | "thread:{id}"
    user_id:       str            # 内部 user_id
    text:          str
    attachments:   list           # 文件/图片（可选）
    reply_func:    Callable       # async (text: str) -> None
```

### 6.2 Slack Adapter

- **连接方式**：Socket Mode（出站 WebSocket，不需要公网 URL，on-premises 友好）
- DM → `session_id = "user:{slack_user_id}"`
- Thread 回复 → `session_id = "thread:{thread_ts}"`
- 无 thread 的群聊消息 → bot 自动在 thread 里回复（强制 thread-first）

### 6.3 Telegram Adapter

- **连接方式**：Long polling（不需要公网 URL，on-premises 友好）
- 私聊 → `session_id = "user:{telegram_user_id}"`
- 群组 reply chain → `session_id = "thread:{message_id}"`

---

## 7. Session Persistence

```
消息到达
  → session_mgr.load(session_id)
      → data/sessions/{session_id}.json 存在 → 读取历史
      → 不存在 → 空历史，新 session
  → agent_loop.run(messages=历史 + 新消息)
      → context_mgr 按需压缩（现有逻辑复用）
  → session_mgr.save(session_id, updated_messages)
      → 覆写 data/sessions/{session_id}.json
```

- 格式：整个历史一次性 JSON 写入（非 append），支持 context 压缩后覆写
- 同一 session 消息顺序处理，不需要加锁

---

## 8. 权限门流程

工具注册时声明 risk level：

```python
@tool(risk_level="high")
def delete_table(name: str) -> str: ...

@tool(risk_level="medium")
def send_email(to: str, body: str) -> str: ...
```

**访问控制（在 `tool_registry.dispatch()` 层，早于 risk 判断）：**

```
tool_registry.dispatch(tool_name, args, agent_id)
  → agent_policy 检查：tool_name ∈ agent.allowed_tools？
      → 否 → 抛出 PermissionError，agent 收到错误，不进入审批流程
      → 是 → 继续 risk_level 判断
```

审批流程：

```
agent 准备调用工具
  → risk_level == "none"   → 直接执行
  → risk_level == "medium" → 私信发起人，附「允许」「拒绝」按钮
                              写 approvals（status=pending）
                              asyncio.Event 等待
  → risk_level == "high"   → 私信预配置 approver
                              同时通知发起人"等待管理员审批"
                              写 approvals（status=pending）
                              asyncio.Event 等待

用户点击按钮 → IM 回调
  → approval.resolve(decision)
      → 更新 approvals 表
      → event.set() 唤醒 agent_loop
          → approved → 执行工具
          → rejected → 告知用户"操作已取消"
```

**超时配置**（pydantic-settings，env var 可覆盖）：

```yaml
permission_gate:
  medium_timeout_seconds: 300    # 默认 5 分钟
  high_timeout_seconds: 3600     # 默认 60 分钟
```

---

## 9. Sub-agent

```python
# parent agent 调用 sub_agent 工具
results = await sub_agent.run(tasks=[
    {"name": "task_1", "prompt": "分析这份文件..."},
    {"name": "task_2", "prompt": "查询这个数据..."},
])

# 内部实现
async def run(tasks):
    return await asyncio.gather(*[
        agent_loop.run(
            messages=[{"role": "user", "content": t["prompt"]}],
            user_id=parent_user_id,   # 权限继承自发起人
        )
        for t in tasks
    ])
```

- Child 使用全新上下文，不继承 parent 对话历史
- Child 不能再派生 sub-agent（最多两层，防止无限嵌套）
- Child eval trace 记录 `parent_session_id`，方便追踪调用链

---

## 10. 沙盒架构

```
宿主机
├── microsandbox-server（原生，pip install microsandbox）
│     ├── /dev/kvm（Linux）或 Hypervisor.framework（macOS M）
│     └── HTTP API：POST /workspace, POST /workspace/{id}/exec, DELETE /workspace/{id}
└── fleetent 容器
      └── sandbox_client
            └── HTTP → host.docker.internal → microsandbox-server
```

**生命周期**：

```
session 开始 → sandbox_client.create_workspace(session_id)
工具调用     → sandbox_client.exec(session_id, command)
session 结束 → sandbox_client.destroy_workspace(session_id)
```

会话内状态持久（文件跨步骤共享），会话间完全隔离。

**降级方案（客户环境无 KVM）**：Docker 容器 + gVisor runtime + seccomp profile，注明安全级别较低。

---

## 11. 部署结构

**安装步骤（on-premises）：**

```bash
# 1. 安装 microsandbox（宿主机，一次性）
pip install microsandbox
microsandbox server start

# 2. 启动服务
cp .env.example .env.production  # 填入 Slack/TG token、LLM key 等
docker-compose up -d
```

**docker-compose.yml 结构：**

```yaml
services:
  fleetent:
    image: fleetent:latest
    env_file: .env.production
    extra_hosts:
      - "host.docker.internal:host-gateway"  # Linux 访问宿主机
    volumes:
      - ./data:/app/data
      - ./config:/app/config
```

---

## 12. 错误处理

| 失败点 | 处理方式 |
|--------|---------|
| agent_loop 异常 | adapter 捕获，回复用户"处理失败，请重试" |
| 沙盒启动失败 | 工具返回错误，agent 决定是否重试或告知用户 |
| 权限门超时 | 自动拒绝，通知发起人，approvals 表记录为 timeout |
| Sub-agent child 失败 | parent 收到部分结果 + 失败原因，由 parent 决定是否继续 |
| IM SDK 断连 | Socket Mode / polling 自动重连 |

---

## 13. 测试策略

沿用 TDD + monkeypatch 模式，新增 mock 模式：

```python
# mock IM 事件
fake_slack_event(text="hello", user="U123", thread_ts="T456")

# mock microsandbox
monkeypatch.setattr(sandbox_client, "_client", FakeSandboxClient())

# mock IM 回写
reply_calls = []
async def fake_reply(text): reply_calls.append(text)

# mock 权限门审批
monkeypatch.setattr(permission_gate, "wait_for_approval",
                    AsyncMock(return_value="approved"))
```

---

## 14. 待决问题

1. **老板口风**（战略文档 §9）：on-premises 是否正式立项？影响投入节奏
2. **目标服务器 KVM 支持**：第一个内部部署环境是否有 KVM？决定沙盒方案
3. **SaaS 团队技术栈**：确认后决定共享层（memory/eval）的 API 设计
