## ADDED Requirements

### Requirement: 工具三态模型与默认划分

agent 运行时 SHALL 将每个对 LLM 可见的工具归入三态之一：**hot**（完整 schema 常驻每轮 `tools=` 数组）、**deferred**（仅以「工具名 + 一行描述」出现在目录文本中，完整 schema 不进 `tools=`）、**activated**（本次 run 中经检索取回 schema、已并入 `tools=`）。默认划分 SHALL 为：所有内置工具（builtin）为 hot；所有 MCP 工具为 deferred，除非被 `hot_mcp_servers` 提升。`tool_search` 工具自身 SHALL 恒为 hot。

#### Scenario: 内置工具默认 hot
- **WHEN** 一个未配置 `hot_mcp_servers` 的 agent 初始化会话
- **THEN** 所有内置工具的完整 schema 出现在首轮 `tools=` 数组中

#### Scenario: MCP 工具默认 deferred
- **WHEN** 一个未配置 `hot_mcp_servers` 的 agent 连接了暴露 MCP 工具的 server
- **THEN** 这些 MCP 工具的完整 schema 不出现在首轮 `tools=` 数组中，而是以「名 + 一行描述」出现在 deferred 目录文本中

#### Scenario: tool_search 恒在场
- **WHEN** agent 初始化任意会话
- **THEN** `tool_search` 的完整 schema 出现在每轮 `tools=` 数组中

### Requirement: deferred 目录文本注入

agent 运行时 SHALL 把当前所有 deferred（未 activated、未提升为 hot）工具以文本块形式注入到模型上下文，每个工具一行，格式为「工具名 + 一行极简描述」。一行描述 SHALL 取自工具 schema 的 description 首行并在过长时截断。目录 SHALL 仅包含经 `allowed_tools` 过滤后放行的工具；被 `allowed_tools` 拒绝的工具既不进 `tools=`，也不出现在目录中。目录文本 SHALL 在单次 run 内构建一次并复用，不在每轮重算。

#### Scenario: 目录仅列放行工具
- **WHEN** agent 的 `allowed_tools` 模式排除了某 MCP server 的全部工具
- **THEN** 该 server 的工具既不在 `tools=` 中，也不出现在 deferred 目录文本中

#### Scenario: 一行描述截断
- **WHEN** 某 deferred 工具的 description 首行超过约定长度上限
- **THEN** 目录中该工具的描述被截断为单行，不包含换行符

#### Scenario: 已 activated 工具移出目录
- **WHEN** 某 deferred 工具在本 run 中已被检索 activated
- **THEN** 后续轮次它出现在 `tools=` 中，且不再重复出现在 deferred 目录文本里

### Requirement: tool_search 检索与直选

`tool_search` 工具 SHALL 支持两种 query 形态：（1）**关键词**——对 deferred 工具的「工具名 + 一行描述」做词法模糊匹配并打分，返回排序后 top-N（默认 N=10）工具的**完整 schema**；（2）**`select:name1,name2`**——按精确工具名直选，返回这些工具的完整 schema。检索 SHALL 仅在 deferred 工具集合（经 `allowed_tools` 放行）内进行；hot 工具与不存在的名字 SHALL 不被命中。`tool_search` SHALL 不依赖任何 provider 专有特性或向量/embedding 基础设施。

#### Scenario: 关键词匹配返回 top-N
- **WHEN** 模型以关键词 query 调用 `tool_search`，匹配到的 deferred 工具数超过 N
- **THEN** 仅返回打分最高的 N 个工具的完整 schema

#### Scenario: select 精确直选
- **WHEN** 模型以 `select:crm__create_lead,jira__create_issue` 调用 `tool_search`
- **THEN** 返回这两个工具的完整 schema，不返回其它工具

#### Scenario: 不存在的工具名
- **WHEN** 模型 `select:` 一个不存在或被 `allowed_tools` 拒绝的工具名
- **THEN** 该名字不出现在返回结果中（不报错使整轮失败，结果中标明未命中）

### Requirement: activated 工具晋升与会话内驻留

`tool_search` 命中的工具 SHALL 被加入本次 run 的 activated 集合；自**下一轮** LLM 调用起，这些工具的完整 schema SHALL 进入 `tools=` 数组并可被模型调用。activated 集合 SHALL 在单次 run 内持续有效（取回一次后续轮次一直可调），仅存于内存、不持久化到 session 文件；会话 resume 为新 run 时 activated 集合 SHALL 重新从空开始（模型需重新检索）。

#### Scenario: 检索后下一轮可调
- **WHEN** 模型在第 k 轮调用 `tool_search` 命中工具 T
- **THEN** 第 k 轮的 `tools=` 不含 T（本轮仅返回 schema），第 k+1 轮起 `tools=` 含 T 且模型可直接调用

#### Scenario: 会话内驻留
- **WHEN** 工具 T 在第 k 轮被 activated，之后若干轮模型未再检索
- **THEN** 这些后续轮次的 `tools=` 仍含 T

#### Scenario: resume 后重置
- **WHEN** 一次 run 结束后会话被 resume 为新 run
- **THEN** 新 run 的 activated 集合为空，先前 activated 的工具回到 deferred 状态

### Requirement: hot_mcp_servers 提升

`agent.yaml` SHALL 支持可选字段 `hot_mcp_servers`：一个 fnmatch 模式列表，匹配到的 MCP 工具（按工具名 `{server_id}__{tool_name}` 匹配）SHALL 被提升为 hot，跳过 deferred、完整 schema 常驻每轮 `tools=`。该字段缺省或为空列表时 SHALL 等价于「所有 MCP 工具全 deferred」。`hot_mcp_servers` 的匹配 SHALL 在 `allowed_tools` 放行的工具集合内生效（被 `allowed_tools` 拒绝的工具不会因 `hot_mcp_servers` 而出现）。

#### Scenario: 整 server 提升
- **WHEN** agent 配置 `hot_mcp_servers: ["crm__*"]`
- **THEN** 所有 `crm__*` MCP 工具的完整 schema 常驻每轮 `tools=`，不出现在 deferred 目录中；其它 server 的 MCP 工具仍为 deferred

#### Scenario: 工具级提升
- **WHEN** agent 配置 `hot_mcp_servers: ["jira__create_*"]`
- **THEN** 仅匹配的 `jira__create_*` 工具为 hot，同一 server 下其它 `jira__*` 工具仍为 deferred

#### Scenario: 缺省全 deferred
- **WHEN** agent.yaml 不含 `hot_mcp_servers` 字段
- **THEN** 所有 MCP 工具为 deferred，行为等价于空列表

#### Scenario: hot 提升不越过 allowed_tools
- **WHEN** 某工具被 `allowed_tools` 拒绝，但匹配 `hot_mcp_servers` 模式
- **THEN** 该工具既不进 `tools=` 也不进目录（allowed_tools 优先）

### Requirement: 每轮 tools= 组装规则

agent 运行时在每轮 LLM 调用前 SHALL 按如下规则组装 `tools=` 数组：hot 工具（内置 + `hot_mcp_servers` 提升的 MCP，经 `allowed_tools` 放行）+ `tool_search` + 本 run 已 activated 的工具的完整 schema。deferred 且未 activated 的工具 SHALL NOT 进入 `tools=`。既有过滤层（`allowed_tools` 可见性、可用性谓词、sandbox/outbound/skill 门、MCP 名投影）SHALL 继续作用于最终进入 `tools=` 的工具，行为不变。

#### Scenario: 组装只含 hot + search + activated
- **WHEN** 一个 agent 有内置 hot 工具、若干 deferred MCP 工具、其中 T 已 activated
- **THEN** 该轮 `tools=` 恰好包含「内置 hot 工具 + tool_search + T」，不含其它 deferred MCP 工具

#### Scenario: 既有过滤层仍生效
- **WHEN** sandbox 关闭使 `run_code` 应被过滤、且某内置工具属 hot
- **THEN** `run_code` 仍按既有规则从 `tools=` 移除，deferred 机制不改变该过滤结果
