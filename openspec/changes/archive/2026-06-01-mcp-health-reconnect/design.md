## Context

MCP1（mcp-http-streamable，已合入）建立 HTTP/stdio 连接并注册工具；`register_all`（mcp_client.py 行 117）只在启动时连一次，连后不再监测。运行时工具调用经 `_call_http_tool`（行 312）/ `_call_stdio_tool`（行 302）；HTTP 每次新建 `httpx.AsyncClient`，stdio 复用 `_active_sessions[server_id]` 的 `ClientSession`。断连时这两个函数会抛出 httpx 连接错误 / stdio EOF，错误裸露给调用方，每次调用重复撞墙。

AR5（error-classification，已合入，`src/fleetent/error_classifier.py`）已预留分类码 `mcp_disconnect`：`CLASSIFICATION_TABLE[ErrorCategory.mcp_disconnect] = ErrorClassification(category=mcp_disconnect, should_retry=True, should_compress=False, should_switch_model=False)`（error_classifier.py 行 91）。AR5 design D3 明确：「`mcp_disconnect`：should_retry=True（尝试重连，失败降级——重连动作由 mcp_client 侧后续实现）」。但 AR5 的 `classify()` 当前**不主动返回** `mcp_disconnect`（其守卫测试 `test_classify_never_yields_reserved` 断言主循环可达的 LLM 异常不产出预留码）——预留码定义齐全，等待本 change 在 mcp_client 侧接通。

docs/capabilities/mcp.md 规划项与场景 3：服务运行中断开 → 工具返回「服务暂时不可用」→ 后台指数退避重连（1s→2s→4s→…→60s）→ 多次失败标记永久不可用 → 恢复后自动启用。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；**禁止全局可变状态**（健康状态/退避计数须按 server 隔离、可注入/重置）；外部 HTTP 用 respx mock、stdio 用 unittest.mock，不发真实请求、不起真实子进程；测试用短退避/短间隔，不真实长 sleep；MCP 工具名双下划线；行长 100；mypy strict；TDD Hard Gate；测试落在 `tests/test_mcp_client.py`。

## Goals / Non-Goals

**Goals:**
- 把 AR5 预留的 `mcp_disconnect` 路径接通：断连异常 → mcp_client 侧判定为 `mcp_disconnect` → 直接读 `CLASSIFICATION_TABLE` 取 `should_retry=True`（不经 `classify()`，详见 D1）→ 重连/降级。
- 为每个服务维护连接健康状态（healthy / degraded / unavailable），按 server 隔离。
- 周期探活：HTTP ping / stdio 子进程存活检查。
- 指数退避重连（1s→2s→4s→…→60s）；连续失败达阈值标记永久不可用、需手动重连；恢复后自动重新启用。
- 降级期工具调用返回「服务暂时不可用」，不裸抛、不卡住；不影响其他服务。

**Non-Goals:**
- 不实现**会话级过期重建**（404 → 重新 initialize 同请求重试）——MCP2 的职责，与本 change 的连接级断连正交。
- 不实现 **OAuth2 / Token 刷新**——MCP5。
- 不实现**完整 degrade/strict/silent 降级模式切换**——本 change 仅做默认的「单服务降级、工具不可用、不阻断平台」；模式化降级策略属后续 change（docs/capabilities/mcp.md 仍列规划）。
- 不改 AR5 分类表的标志位定义（只消费，不修改）。
- 不改 stdio/HTTP 在服务健康时的正常注册/调用、命名空间、认证。

## Decisions

### D1：断连异常由 mcp_client 侧映射到 AR5 `mcp_disconnect`（直接读 `CLASSIFICATION_TABLE`，**不经 `classify()`**），读 should_retry 决定重连
**事实核实**（error_classifier.py 行 97-119）：AR5 的 `classify()` 是纯表查找——`_categorize()` 只识别 `APIStatusError`（按状态码归 `rate_limit` / `auth_failed` / `context_overflow`），**其余一律落到 `unknown`**。它**没有**从 httpx `ConnectError` / `ConnectTimeout` / `ReadError` 或 stdio EOF 产出 `mcp_disconnect` 的路径，且返回的是已查好表的 `ErrorClassification`（不可再 re-key）。因此把断连异常**喂给 `classify()` 只会得到 `unknown`**，拿不到 `mcp_disconnect`。

实现口径：工具调用捕获连接级断连异常（httpx `ConnectError`/`ConnectTimeout`/`ReadError` 等、stdio 会话失活/EOF）后，**由 mcp_client 侧直接把该异常判定为 `ErrorCategory.mcp_disconnect`，并直接读 `error_classifier.CLASSIFICATION_TABLE[ErrorCategory.mcp_disconnect]`** 取得其 `ErrorClassification`（`should_retry=True`），据 `should_retry` 进入重连/降级路径。**不要**接一条「经 `classify()` 取分类」的路径——那是会得到 `unknown` 的死分支。
**为何**：AR5 已把「该不该重试」收口为标志位（`mcp_disconnect.should_retry=True`），本 change 复用这层**只读契约**（读 `CLASSIFICATION_TABLE` 的 `should_retry`），而非在 mcp_client 里另写「断连要不要重连」的判断——与 AR5「消费方只读标志位、不改表」的设计一致；同时绕开 `classify()` 不识别断连异常这一事实。这正是 AR5 design D3 所指的「`mcp_disconnect` 重连动作由 mcp_client 侧后续实现」。断连异常类型属 mcp_client 领域知识，由 mcp_client 判定分类码、再读表取标志位，最内聚且不改 AR5。
**Alternatives**：①mcp_client 自己 isinstance 判断断连并硬编码「重连」布尔——被否，重复 AR5 已定义的策略，违背「分类层是标志位单一事实来源」；②扩展 AR5 `classify()`/`_categorize()` 让它直接吃 httpx/stdio 异常并返回 `mcp_disconnect`——被否（本 change 不改 AR5），断连异常类型属 mcp_client 领域知识，放 mcp_client 判定更内聚，AR5 表保持只读不变；③把断连异常喂 `classify()`——被否，只会得到 `unknown`（见上方事实核实）。

### D2：连接健康状态机（healthy / degraded / unavailable），按 server 隔离
每个服务维护连接健康状态：
- `healthy`：连接正常，工具可调用。
- `degraded`：检测到断连、正在后台重连；工具调用返回「服务暂时不可用」。
- `unavailable`：连续重连失败达阈值，标记永久不可用、停止自动重连；工具调用返回「服务暂时不可用」，需手动触发重连。
状态按 server 实例持有（沿用 MCP2/MCP1 的「状态落在 server 而非模块级全局」原则），可注入/重置以便测试。
**为何**：三态足以表达 docs 场景 3 的「暂时不可用→重连→恢复」与「多次失败→永久不可用→手动重连」；按 server 隔离满足「禁止全局可变状态」与测试隔离。
**Alternatives**：①布尔 healthy/unhealthy 两态——被否，无法区分「正在退避重连」与「已放弃需手动」；②模块级 `dict[str, Status]`——被否，全局可变状态违反 CLAUDE.md。

### D3：探活——HTTP 轻量请求 / stdio 子进程存活
后台周期探活：HTTP 服务发轻量请求（复用 `tools/list` 或 initialize 级 ping）判活；stdio 服务检查 `_active_sessions` 会话/子进程是否存活。探活失败把服务转 `degraded` 并触发重连。探活间隔为可注入参数（默认值内置，测试用短值）。
**为何**：场景 3 要求「断开后用户触发相关调用」即返回不可用并后台重连——探活让平台不必等用户撞墙就能先发现断连。HTTP/stdio 探活机制不同（docs 待决问题也提到「是否同频率」），统一为可注入间隔，默认可同频。
**Alternatives**：①只在工具调用失败时被动发现断连，不主动探活——被否，docs 明列「定期探活」，被动发现会让降级反馈滞后到下一次调用；②对 HTTP 用专门 ping 协议——被否，MCP 无标准 ping，复用 `tools/list` 最省且无新依赖。

### D4：指数退避重连，阈值后永久不可用
重连退避序列 1s→2s→4s→8s→…→上限 60s（封顶后保持 60s）。连续失败次数达阈值（默认值内置，可注入）后转 `unavailable`，停止自动重连。重连成功 → 状态回 `healthy`、退避计数清零、工具自动重新可用。退避基数、上限、阈值均为可注入参数（测试用短值，不真实长 sleep）。
**为何**：与 docs/capabilities/mcp.md 明列的 1s→2s→4s→60s 一致；指数退避避免对不可达服务高频重连打爆；阈值上限避免无限重连。可注入参数使测试无需真实等待。
**Alternatives**：①固定间隔重连——被否，docs 明确要求指数退避；②永不放弃——被否，docs 要求达阈值标记永久不可用、需手动重连。

### D5：降级反馈——工具返回「服务暂时不可用」
服务处于 `degraded` / `unavailable` 时，对其工具的调用不进入实际网络/子进程调用，直接返回明确的「服务暂时不可用」结果文本（工具结果是字符串，与现有 `_call_*_tool` 返回类型一致），不抛异常、不卡住。其他服务工具不受影响。
**为何**：场景 3 要求「该工具返回『服务暂时不可用』」；返回字符串而非抛异常，让 agent_loop 能把它当工具结果交给 LLM，不中断整个对话；与 MCP1 `register_all` 的「单服务降级不阻断平台」一致地，做到「单服务降级不阻断对话」。
**Alternatives**：①抛异常交上层——被否，会中断 agent 循环且不符合场景 3 的「返回」语义；②静默返回空——被否，docs 明确「不静默卡住」，需明确不可用信号。

### D6：探活后台任务接入 server.py lifespan，调度复用既有能力
探活/重连后台任务在 `server.py` lifespan 启动（与 `mcp_client.register_all` 同处），关停时随 `mcp_client.close()` 取消。实现为 **MCP 域内自持的 `asyncio` 后台任务**（`asyncio.create_task`，循环内 `await asyncio.sleep(探活间隔)`），不引入新调度依赖。

**与（已暂缓的）cron 调度器解耦（负责人确认）**：本探活任务是 **MCP 基础设施的内部健康维护**，**MUST NOT** 走 `cron_scheduler` / APScheduler（那是张亮 scheduling 域的用户级定时任务功能，roadmap 已决定 cron 触发器暂缓）。探活属服务级常驻 asyncio task，与"定时任务"功能正交、互不依赖——这样 MCP3 自包含在 MCP 域内，既不被"调度器暂缓"波及，也不给 scheduling 域增加耦合。
**为何**：探活是长生命周期后台行为，lifespan 是既有的服务级启停钩子；用裸 asyncio task 即可，零新依赖、零跨域耦合。CLI 一次性 `run()` 不需要常驻探活（与 skill scan 同理，仅服务端常驻）。
**CLI 降级行为澄清**：CLI `run()` 无常驻探活意味着 CLI 进程内的健康状态不会被后台 prober 主动填充（服务默认 `healthy`、不会预先转 `degraded`）。因此 CLI 下的工具调用**总是走 live 路径**直接发起真实网络/子进程调用；若此时服务已断连，则**依赖调用时的断连映射**（D1：捕获断连异常 → 判定 `mcp_disconnect` → 读 `should_retry`）来触发降级/重连，而非依赖事先的探活降级。换言之：服务端常驻探活提供「调用前即知不可用、直接返回不可用」的提前量；CLI 无此提前量，断连在首次调用时被发现并按 D1 处理。两者最终行为一致，差别仅在「何时发现断连」。
**Alternatives**：①把探活挂到 `cron_scheduler` / APScheduler——被否，那是 scheduling 域的用户级定时任务功能（已暂缓），跨域耦合且会被"调度器暂缓"波及；裸 asyncio task 已够、零依赖、自包含在 MCP 域；②在每次工具调用同步探活——被否，探活应与调用解耦、周期化。

### D7：与 MCP2 / AR5 的边界（连接级 vs 会话级）
- MCP2 处理**会话级过期**：连接仍在、服务端判 `Mcp-Session-Id` 失效（HTTP 404），同一请求内重新 initialize 重试，不经 AR5、不归 `mcp_disconnect`。
- MCP3（本 change）处理**连接级断连**：服务不可达 / 子进程死 / 探活失败，归 AR5 `mcp_disconnect`，触发后台重连与降级。
- 顺序：工具调用失败时，先按 MCP2 判会话过期（404→重建一次）；若是连接级断连（非 404 的连接错误，或会话重建后仍连不上），则按 MCP3 归 `mcp_disconnect` 走重连/降级。
**为何**：两个 change 都涉及「失败后恢复」，需明确分层避免重复/冲突——会话过期归 MCP2 协议重建（无感知），连接断开归 MCP3 + AR5（降级 + 后台重连）。

## Risks / Trade-offs

- [MCP2 会话重建与 MCP3 连接重连职责重叠] → D7 明确分层：404=会话级（MCP2 协议重建，不归 mcp_disconnect）；连接级断连=MCP3（归 AR5 mcp_disconnect）。加用例区分 404（不进 MCP3 降级）与连接错误（进 MCP3 降级）。
- [断连异常未被 classify() 归为 mcp_disconnect（经核实确实不会）] → D1：mcp_client 侧把断连异常判定为 `ErrorCategory.mcp_disconnect`、直接读 `CLASSIFICATION_TABLE[mcp_disconnect]` 取标志位（不经 `classify()`、不改 AR5 表标志位）；加用例断言 mcp_client 对断连异常取到的 category 为 `mcp_disconnect` 且 `should_retry` 为真，并（守卫用例）断言 `classify(断连异常)` 仍为 `unknown`，证实不依赖 `classify()`。
- [探活/重连后台任务在测试中真实 sleep 拖慢测试] → 退避基数、上限、阈值、探活间隔全部可注入，测试用极短值（如基数 0.01s）或直接驱动退避计算函数，不真实长 sleep（参考 permission_gate 测试用短超时）。
- [永久不可用后无人手动重连，服务长期不可用] → 提供手动触发重连入口；并发探活不再对 `unavailable` 服务自动重连（避免无效高频）。阈值与手动入口在 spec/tasks 覆盖。
- [并发工具调用同时触发对同一断连服务的重连] → 重连应幂等/去重（同一服务同一时刻至多一个在途重连）；列为实现注意点，必要时按 server 加重连锁（仿 session_mgr per-session Lock）。

## Open Questions

- 探活间隔：HTTP（轻量请求）与 stdio（子进程存活）是否使用相同频率（docs/capabilities/mcp.md 待决问题原样保留）——实现时按目标 server 行为定，默认可同频，间隔可注入。
- 永久不可用阈值：连续失败几次后标记 `unavailable`、如何重置（docs/capabilities/mcp.md 待决问题原样保留）——默认值内置、可注入；重置由成功重连或手动触发清零。
- 是否需要 per-server 重连锁以避免并发重复重连——本次按「重连幂等、至多一个在途」实现，高并发实测出现重复重连再加锁。
- 部署级可调参数是否进 `config/mcp.yaml`（per-server 或全局）——本次以可注入参数 + 内置默认为先，零配置可用；如客户需调再加可选字段。
