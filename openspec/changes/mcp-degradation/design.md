## Context

`mcp_client.py` 已落地两个**正交**的「服务不可用」维度，但二者各自为政、且只作用于调用时：

1. **连接级健康（MCP3）**：`McpServerConfig._health: HealthState`（行 153），取值 `healthy` / `degraded` / `unavailable`（行 49-54），由探活/重连维护，按 server 实例隔离（D2：不进全局可变状态）。调用时 `_call_http_tool` / `_call_stdio_tool` 检查 `server._health is not HealthState.healthy` 即短路返回 `_unavailable_result(...)`（行 851-852、882-883）。`get_health(server)` 是公开读取入口（行 171-173）。
2. **认证级不可用（MCP5）**：`McpServerConfig._auth_unavailable: bool`（行 151），token 端点真认证错误时置位（行 646），由 `_clear_oauth_auth_state` 在配置重载/重新注册时清除（行 532-539）。调用时 `_call_http_tool` 检查 `server.auth_type == "oauth2" and server._auth_unavailable` 即返回「认证不可用」文本（行 875-879）。MCP5 spec 明确该标志「独立于连接级健康状态」「MUST NOT 依赖 MCP3 才能生效」。

两个维度都**只在调用发生时短路**——服务不可用时其工具仍出现在 `tool_registry.get_schemas()`（行 90-92 扁平返回 `_registry` 全部 schema）里，AI 看得见、会去调，白白消耗一轮 tool-use 才拿到「不可用」文本。docs/capabilities/mcp.md 场景 5 要求工具被「**临时移除**」出 AI 可见列表，并定义了 `degrade`/`strict`/`silent` 三种模式——这些尚未实现。

`register_all`（行 461-466）已实现启动期单服务失败降级（log warning、不阻断启动），但启动失败的服务与运行时降级的服务没有统一的「不可用」语义。

约束（CLAUDE.md）：禁止全局可变状态（状态读取按 server 实例，过滤钩子可注入）；禁止 AI 框架与 ORM；mypy strict 全注解；行长 100；TDD Hard Gate；外部 HTTP 用 `respx` mock、stdio 子进程用 `unittest.mock` mock、不发真实请求、不起真实子进程；测试隔离 tmp_path/monkeypatch；不吞异常。

## Goals / Non-Goals

**Goals:**
- 定义**单点可用性判定**，整合 MCP3 连接健康（`_health`）与 MCP5 认证不可用（`_auth_unavailable`）两正交态：任一不可用 → 服务工具整体不可用。
- 不可用服务的工具从 AI 可见 schema **临时摘除**；服务恢复后自动重新可见（不删 `tool_registry` 注册项，过滤视图）。
- 可配置降级模式 `degrade`（默认）/ `strict` / `silent`，per-server（缺省全局默认），缺省零配置即 `degrade`。
- `register_all` 启动失败降级与运行时降级统一受同一套模式与摘除约束。
- 降级期即便竞态命中调用，仍走既有 MCP3/MCP5 短路安全返回，不进真实请求、不裸抛、不卡住。

**Non-Goals:**
- 不实现/不改 MCP3 的探活、指数退避重连、永久不可用阈值（已属 MCP3）。
- 不实现/不改 MCP5 的 token 获取/刷新、`_auth_unavailable` 的置位与清除逻辑（已属 MCP5）。
- 不改 `HealthState` 三态定义、不改命名空间格式 `{server_id}__{tool_name}`。
- 不实现外部降级通知的具体投递通道（`silent` 仅定义「不通知」语义；通知通道由 observability 域负责，本 change 不引入）。

## Decisions

### D1：单点可用性判定 `is_server_available(server)` 整合两正交态
新增 `mcp_client.is_server_available(server: McpServerConfig) -> bool`：
```
return server._health is HealthState.healthy and not (
    server.auth_type == "oauth2" and server._auth_unavailable
)
```
- 连接级：复用 MCP3 的 `_health`（经 `get_health` 语义），仅 `healthy` 视为连接可用；`degraded` / `unavailable` 均不可用。
- 认证级：复用 MCP5 的 `_auth_unavailable`，仅对 `oauth2` 服务生效（与 `_call_http_tool` 行 875 的判定条件一致），`none`/`api_key` 服务无此维度。
- 两态**逻辑与**：必须连接健康**且**认证可用，工具才可用。

**为何**：两态正交（MCP5 spec 明确「认证不可用独立于连接健康、不依赖 MCP3」），但「该服务工具此刻能不能给 AI 用」需要一个**单一判定**供 schema 过滤、降级模式、调用短路共同消费，否则三处各自拼条件必然漂移。逻辑与是唯一安全选择：任一维度不可用都不该把工具暴露给 AI。判定是纯读取（读 server 实例字段），无副作用、无新全局状态。
**Alternatives**：①把认证不可用「折叠进」`_health`（认证失败也置 `degraded`）——被否，违反 MCP5「正交、不依赖 MCP3」契约，且认证不可用的恢复触发点（配置重载）与连接不可用（后台重连）完全不同，合并会污染状态机语义；②三处各自判断——被否，必然漂移，正是当前缺口。

### D2：schema 摘除为「过滤视图」，不删注册项
`tool_registry.get_schemas()` 返回前过滤掉「属于不可用 MCP server」的工具 schema：
- MCP 工具名形如 `{server_id}__{tool_name}`（双下划线分隔）。给定一个工具名，解析其 `server_id`、查 `_server_registry` 拿 server、用 D1 判定可用性；不可用则该 schema 不出现在返回列表。
- 非 MCP 工具（无对应 server）一律保留。
- 摘除是**过滤视图**：`tool_registry._registry` 的注册项**不删**。服务恢复后（MCP3 重连成功 reset 为 `healthy` / MCP5 清除 `_auth_unavailable`），同一判定自然再次返回可用，工具重新出现在 schema——无需重新注册、无副作用。

**为何**：删注册项会让「恢复」变成「需重新 `register_all` 拉取 tools」，既重又易错（恢复路径与启动路径分叉）；过滤视图让恢复=判定翻真，零额外动作，天然满足 docs「服务恢复后自动重新启用」。MCP 工具名的 `server_id` 可从名字解析（双下划线），不需额外索引表。
**Alternatives**：①调用时才发现不可用、不动 schema（现状）——被否，AI 仍看得见、白调一轮、污染上下文，正是 docs 场景 5 要修的；②真删 `_registry` 条目并在恢复时重注册——被否，恢复路径复杂、易与启动路径不一致。

### D3：降级模式 `degrade` / `strict` / `silent`，per-server 默认 `degrade`
`McpServerConfig` 增加 `degrade_mode: str = "degrade"`（取值 `degrade` / `strict` / `silent`，与 `auth_type` 同风格的字符串字段；非法值在加载时回退 `degrade` 并 log，不静默接受）：
- `degrade`（默认）：D2 摘除该服务工具，其余服务与当前对话正常进行。
- `strict`：该服务不可用时，当前 agent 运行 MUST 以**明确错误**终止，不静默继续。终止信号形式：mcp_client 暴露一个查询「是否存在 strict 且不可用的 server」的判定（全局视角），由 agent_loop 在组装 schema / 进入循环前消费并以明确错误终止（具体 agent_loop 集成点为实现细节；本 change 钉死「strict 不可用 → 明确错误终止、非静默」语义与可被消费的判定入口）。
  - **「agent 绑定某 server」的定义**：agent 是否绑定某 MCP server = 其 `allowed_tools` 白名单（fnmatch）是否覆盖该 server 的 `{server_id}__*` 工具命名空间。mcp_client 的判定只回答「是否存在 strict 且不可用的 server」（全局，不感知具体 agent），而「这个 agent 是否用到该 server」这半由 agent_loop 在运行前据该 agent 的 `allowed_tools` 与该 strict-且-不可用 server 的 `{server_id}__*` 工具命名空间是否相交来判定。**strict 终止仅作用于 `allowed_tools` 覆盖了该 strict-且-不可用 server 工具的 agent**；未绑定该 server（`allowed_tools` 与其命名空间不相交）的 agent 不受该 server 的 strict 终止影响。
- `silent`：与 `degrade` 同样 D2 摘除工具，但**仅记录日志**、不产生面向用户/外部的降级通知（通知通道本 change 不实现，见 Non-Goals）。silent 与 degrade 的**唯一差异**就是「不发面向用户/外部的降级通知」；由于该通知通道属 observability 域、本 change 不落地，**在通知通道落地之前 `silent` 的可观察行为等同于 `degrade`**（都摘除工具 + 记日志）。silent 在此仅作为为将来通知能力预留的**前向声明**模式，现阶段不应被理解为与 degrade 已存在行为差异。

**为何**：三种模式直接对应 docs/capabilities/mcp.md 已定义的语义，是客户对「单服务故障影响范围」的策略选择——数据分析 agent 可容忍工具暂缺（`degrade`），而强一致流程宁可整体停（`strict`），噪声敏感环境要静默（`silent`）。per-server 粒度因为同一 agent 可能挂多个 server、故障容忍度不同；默认 `degrade` 保证零配置即「最小惊扰」行为，与 docs「默认 degrade」一致。
**Alternatives**：①只做全局单一模式——被否，多 server 场景容忍度天然不同；②`strict` 实现为「调用时抛异常」——被否，工具已被 D2 摘除、AI 根本不会调，抛点应在「发现不可用」时（组装 schema / 循环前），而非「调用时」；故 strict 的终止判定独立于调用路径。

### D4：tool_registry 过滤经可注入钩子，避免分层倒置
`tool_registry` 是底层执行层，不应反向依赖 `mcp_client` 的内部状态。`get_schemas()` 的过滤经一个**可注入的过滤谓词**实现：
- `tool_registry` 暴露一个模块级可注入钩子（默认 `None`，即不过滤——保持现状/非 MCP 场景零影响），形如 `_schema_visibility_filter: Callable[[str], bool] | None`。
- `mcp_client` 在注册 MCP 工具时（或 server lifespan 启动时）设置该钩子为「按工具名判定其所属 server 是否可用」的函数；钩子按 server 实例读取状态（D1），不持有可变全局态。
- 钩子可在测试中 monkeypatch 注入/清除，隔离测试。

**为何**：CLAUDE.md 模块边界清晰、禁止全局可变状态。让 `tool_registry` 直接 `import mcp_client` 并读其 `_server_registry`/`_health` 会造成底层依赖上层、且把 MCP 健康态泄进通用执行层。可注入钩子使 `tool_registry` 只认「一个判定工具是否可见的谓词」，MCP 细节留在 mcp_client；默认 `None` 保证非 MCP 部署与现有测试零回归。钩子本身是「注入点」非「可变业务状态」，判定每次实时读 server 实例，符合「无全局可变状态」。
**Alternatives**：①`tool_registry` 直接读 `mcp_client._server_registry`——被否，分层倒置 + 跨模块读内部状态；②每次调 `get_schemas` 传入 server 列表参数——被否，`get_schemas` 调用方（agent_loop）不应被迫感知 MCP，钩子更内聚。

### D5：register_all 启动失败 = 不可用态，统一受降级模式约束
`register_all`（行 461-466）启动期单服务连接失败已 log warning 且不阻断启动。本 change 明确其与运行时降级统一：
- 启动失败的服务**未进入 `_server_registry`**（`_register_server` 抛出后 `register_all` 跳过）——其工具从未注册，故天然不在 schema 中（等价于「摘除」效果）。这与运行时降级（已注册但不可用 → D2 过滤）殊途同归，对 AI 表现一致：工具不可见。
- `silent`：启动失败仅 log（已是现状），不额外通知。
- `strict`：若一个 `strict` 服务**启动**即失败，design 取向为——记录明确错误并使该 server 标记为不可用，由 agent_loop 在该 agent 绑定了该 strict server 时以明确错误拒绝运行（与运行时 strict 同一判定入口 D3）。启动期 strict **不阻断整个平台启动**（其他 agent / 其他 server 不受牵连），仅影响绑定该 strict server 的 agent 运行。

**为何**：「对 AI 表现一致」是降级策略的核心目标——无论服务是启动就连不上还是运行中掉线，AI 都不该看到其工具。启动失败「未注册=不可见」与运行时「已注册但过滤=不可见」对 AI 等效，无需为启动失败单独造路径。strict 启动失败不炸平台，是因为 docs 的 `strict` 约束的是「stop 整个 agent」而非「stop 整个平台」——影响范围限定在绑定该 server 的 agent。
**Alternatives**：①启动失败的服务也塞进 registry 并标 `unavailable`——可选实现细节，但「未注册」已达成不可见效果，无需为统一语义强行注册一个连不上的 server；本 change 只要求「对 AI 表现一致」，不强制其内部表示。

## Risks / Trade-offs

- [schema 摘除与一次调用之间的竞态（摘除后、LLM 已基于旧 schema 发起调用）] → 沿用 MCP3/MCP5 既有调用短路（`_call_*_tool` 行 851/875/882）兜底：即便竞态命中，调用仍返回不可用结果、不进真实请求；spec 用 scenario 断言「竞态调用仍安全返回」。
- [`tool_registry` 过滤钩子被误置为持有可变全局状态] → D4 明确钩子是「注入点」，判定每次实时读 server 实例、不缓存；默认 `None` 零影响；测试可 monkeypatch 注入/清除。
- [`strict` 模式终止范围被误解为「停整个平台」] → design D3/D5 钉死：`strict` 影响范围是「绑定该 server 的 agent 运行」，非平台；spec scenario 限定终止范围。
- [非法 `degrade_mode` 配置值] → 加载时校验：非法值 log 后回退 `degrade`，不静默接受、不吞异常；spec scenario 覆盖。
- [认证不可用（oauth2）与连接不可用同时命中导致重复降级] → D1 逻辑与天然幂等：任一为真即不可用，schema 只摘一次；恢复需两态都恢复（连接 healthy 且认证清除）才重新可见，符合预期。

## Open Questions

- `strict` 模式下「终止 agent 运行」的确切错误呈现（返回给用户的措辞 / 是否计入 trace）：本 change 定义语义与判定入口，呈现细节可在 agent_loop 集成时定。
- `silent` 的「不外部通知」是否需要与 observability 域（如降级事件 trace）协调一个「记日志但不告警」的标准级别？本 change 仅定义「不外部通知」语义，trace 级别留待 observability。
- 降级模式是否需要全局默认（`config/mcp.yaml` 顶层）叠加 per-server 覆盖，还是仅 per-server？本 change 默认 per-server（缺省 `degrade`），全局默认为可选增强。
- 是否需要 admin CLI / `/health` 暴露各 server 当前可用性（连接态 + 认证态 + 生效降级模式）便于运维核对？
