## Context

agent 运行时在每轮 LLM 调用前于 `runtime/loop.py` 的 `_policy_chat`（约 1940-1968 行）拼装 `tools=` 数组：`get_schemas()` 取全量 → `is_tool_visible(allowed_tools)` 过滤 → outbound/sandbox/skill 几个门 → `project_schemas` 名投影。结果是**所有放行工具的完整 schema 每轮全量发送**。内置工具 ~27 个，MCP 工具随 server 数线性膨胀，单工具 schema 约 500–2000 字节，多 server 部署下工具 schema 可占约 90% 上下文。除静态 `allowed_tools` 白名单外无任何按需机制。

关键既有设施可复用：
- `ToolContext` 是 dispatch 时注入的 run 作用域 out-of-band 对象（`tools/registry.py:288`），工具声明 `tool_context` 形参即可接收（`_accepts_tool_context`）。两处 run 入口创建它（`loop.py:1994`、`:2576`）。
- `governance/agent_policy.is_tool_visible` 已实现 fnmatch 放行 + opt-in 排除。
- `integrations/mcp` 持有 canonical 工具元数据（`_mcp_tool_meta`），可提供 deferred 目录所需的「名 + 描述」。

## Goals / Non-Goals

**Goals:**
- 把所有 MCP 工具默认从「全量 schema 常驻」改为 deferred（仅目录文本露出名 + 一行描述），将工具 schema 的上下文占用从 3 万–10 万 token 量级降到 ~3–7k。
- 提供 `tool_search`（词法匹配 + `select:` 直选）让模型按需取回完整 schema 并在本 run 内驻留可调。
- 提供 `hot_mcp_servers`（fnmatch）让 agent 把核心 MCP server/工具提升回 hot，常用路径零额外往返。
- 不改变 governance、provider 行为与既有过滤层语义。

**Non-Goals:**
- 不做语义/embedding 检索（留作后续增量，本次纯词法）。
- 不持久化 activated 集合到 session 文件（resume 后重搜）。
- 不改 `allowed_tools` / `tool-availability` / `tool-schema-builder` 的既有要求。
- 不改 MCP 连接、发现、名投影机制本身。

## Decisions

### D1：三态以「集合 + 配置」表达，不引入新工具状态字段
工具仍统一注册在 `tr._registry`。三态是**组装时的视图**，而非注册时的属性：
- **hot 判定**：内置工具恒 hot；MCP 工具当其 canonical 名匹配 `hot_mcp_servers` 任一 fnmatch 模式时为 hot。
- **deferred**：放行但非 hot、非 activated 的工具。
- **activated**：`ToolContext.activated_tools: set[str]`（canonical 名）中的工具，run 作用域。

*备选*：在 registry 给每个工具打 persist 状态标签——否决，污染注册层、且状态本质是 per-run 而非 per-tool。

### D2：deferred 目录走文本块，不进 `tools=`
目录在单次 run 内构建一次（与系统提示同期），作为独立上下文块注入，每行「`canonical_name` — 一行描述」。描述取工具 schema `description` 首行、截断为单行。目录内容 = 放行工具 − hot 工具（activated 的工具在组装时从目录动态剔除，因其已在 `tools=`）。这是省 token 的核心：名 + 描述每行 ~10–20 token，全量 schema 每个 ~150–600 token。

*备选*：把目录塞进 `tool_search` 的 description——否决，description 过长本身又成上下文负担且不利模型扫描。

### D3：`tool_search` 经 `ToolContext` 回写 activated
`tool_search` 是内置工具（恒 hot），声明 `tool_context` 形参。命中工具时把 canonical 名写入 `tool_context.activated_tools`，并把这些工具的完整 schema 作为工具结果文本返回。`_policy_chat` 每轮读取同一 `activated_tools` 集合，把其中工具的完整 schema 并入 `tools=`。因此 search 那轮模型仅在结果里看到 schema，**下一轮**该工具才在 `tools=` 中可调——与既有「工具结果 → 下一轮决策」节奏一致，无需特殊处理。

*备选*：search 同轮即把工具塞进当前 `tools=`——否决，`tools=` 在 LLM 调用前已定，同轮注入需重入 LLM，复杂且无收益。

### D4：组装顺序——deferred 裁剪插在 allowed_tools 之后、其余门之前
在 `_policy_chat` 现有管线里，`is_tool_visible` 过滤之后插入一步「deferred 裁剪」：保留 hot + `tool_search` + activated，移除其余 MCP deferred 工具。后续 outbound/sandbox/skill 门与 `project_schemas` 不变地作用于裁剪后的集合。这样既有过滤语义全部保留，deferred 只是更早地缩小集合。

### D5：词法匹配算法
对每个候选「`name` + 描述」做大小写不敏感的 token 包含计分（query 词命中名/描述各计权，名命中权重更高），返回 top-N（默认 10）。`select:` 形态直接按 canonical 名精确取，绕过打分。无第三方依赖、确定性、可审计。

## Risks / Trade-offs

- **发现性下降（模型漏看工具）** → 缓解：目录带一行描述（非纯名）；`tool_search` 词法对名+描述双字段匹配；`hot_mcp_servers` 让高频 server 免搜。
- **多一次往返（search → 下一轮调用）** → 缓解：activated 整 run 驻留，重复调用只摊一次；内置工具与 pin 的 server 走 hot 不经 search。
- **目录与 `tools=` 双重维护可能不一致**（同一工具既在目录又在 `tools=`）→ 缓解：组装时以 activated/hot 集合为唯一真相，目录构建动态剔除 hot/activated，单一来源避免分叉。
- **resume 后模型需重搜** → 接受：换取实现简单、不持久化 schema；目录在新 run 仍在场，重搜成本低。
- **`get_schemas()` 仍每轮被调** → 顺带优化：deferred 目录文本缓存到 run 作用域只构建一次；`tools=` 组装仍每轮跑（必要，因 activated 会变），但集合已显著变小。

## Migration Plan

纯新增能力，无数据迁移、无 schema 变更。`hot_mcp_servers` 缺省即空列表（全 deferred）。回滚 = 移除 deferred 裁剪步骤与 `tool_search` 注册，`tools=` 组装恢复原样，旧 agent.yaml 不受影响（多余字段被忽略）。

## Open Questions

- top-N 默认值 10 是否合适，是否暴露为 `tool_search` 入参由模型自调（倾向：暴露可选 `limit`，默认 10）。
- 一行描述截断长度上限（倾向：~80 字符）。
