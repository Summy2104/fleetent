## Why

每次 agent 会话初始化时，所有 MCP 工具的完整 schema（name + description + parameters）会被全量拼装进 `tools=` 数组，并在**每一轮** LLM 调用时重复发送。在配置了较多 MCP server 的部署里，工具 schema 可占用约 90% 的上下文窗口（实测量级 3 万–10 万 token），挤压了对话历史、KB 检索结果与 skill 的可用空间。当前除静态 `allowed_tools` 白名单外，没有任何按需加载机制——绝大多数工具在单次会话中根本不会被调用，却始终常驻。

## What Changes

- 引入工具「三态模型」：**hot**（全量 schema 常驻 `tools=`）/ **deferred**（仅以「工具名 + 一行描述」文本块注入，不进 `tools=`）/ **activated**（本会话经检索取回 schema、已晋升进 `tools=`）。
- 默认划分：~27 个内置工具常驻 **hot**；所有 MCP 工具默认 **deferred**。
- 新增内置工具 `tool_search`（常驻 hot）：接受关键词（对「工具名 + 描述」词法模糊匹配，返回 top-N 完整 schema）或 `select:name1,name2`（精确直选）；命中工具加入本会话 activated 集合，**下一轮**进入 `tools=` 即可调用。
- 新增 `agent.yaml` 字段 `hot_mcp_servers`（fnmatch 模式列表，可选）：把指定 MCP server / 工具提升为 hot，跳过 deferred。零配置即用：不写 = 所有 MCP 全 deferred。
- deferred 目录文本整会话构建一次（替代当前 `get_schemas()` 每轮重算的浪费）。
- governance 与 provider 行为不变：deferred 目录只列 `allowed_tools` 放行的工具；permission gate 仍在调用时触发；`tool_search` 是普通内置工具，不依赖任何 provider 特性。

## Capabilities

### New Capabilities
- `deferred-tool-loading`: 工具三态模型（hot/deferred/activated）、deferred 目录文本注入、`tool_search` 词法检索与 `select:` 直选、activated 会话内驻留、`hot_mcp_servers` 配置驱动的 hot 提升，以及每轮 `tools=` 的组装规则。

### Modified Capabilities
<!-- 无：tool-access-control 的 allowed_tools 语义不变（deferred 目录复用其放行结果）；tool-availability、tool-schema-builder 的要求不变。 -->

## Impact

- **owning package**：`tools/`（新增 `tool_search` 工具 + deferred 目录构建）
- **public API surface**：`tools.registry` 新增「构建 deferred 目录文本」与「按词法/精确检索工具 schema」的函数；`tool_search` 工具注册
- **cross-module dependencies**：
  - `runtime/loop.py:1941-1968` 的每轮 `tools=` 组装逻辑改为「hot + tool_search + 本会话 activated」，deferred 不进数组
  - `agent_config.py` 新增 `hot_mcp_servers` 字段（fnmatch）
  - `integrations/mcp/` 提供 deferred 工具元数据（名 + 一行描述）来源
  - 复用 `governance/agent_policy.is_tool_visible`（allowed_tools 过滤）对目录做同样过滤
- **owned tables**：无
- **config namespace**：`agent.yaml` 新增 `hot_mcp_servers`
- **migration / shim plan**：纯新增能力，无数据迁移；旧 agent.yaml 不含 `hot_mcp_servers` 时默认空列表（全 deferred）
- **架构约束**：改动全在 agent 运行时侧（`tools/`、`runtime/`、`integrations/mcp/`、`agent_config.py`），不触碰 `platform.*`，符合单向依赖契约
- **activated 持久化**：仅内存内、单次 run 有效；会话 resume 后需重新检索（不持久化 schema 到 session 文件）
