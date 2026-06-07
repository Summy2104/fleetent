# MCP 增强程序 2026-06 · 问题与决策记录

> 配套文档：`gap-analysis.md`（四参考项目差距分析，本程序依据）
> 执行方式：自主按 OpenSpec 工作流逐变更实施（worktree + feat 分支 + TDD 红绿 + opsx archive），经 **bb-pr 自动合并**到 main；全部完成后由张洋整体审核。
> 范围：**B**（正确性+安全硬化 + 协议广度），**不含** OAuth 富流程。
> 每节按：做了什么 / 问题 / 决策 / 改进点 / 送审点。

---

## 程序级决策（Program Decisions）

- **PD1 — 拆成 6 个聚焦变更**（而非 1 个大变更）：契合本仓把 MCP 切成 `mcp-client`/`mcp-degradation`/`mcp-http-streamable`/… 的细粒度 spec 惯例，且自动合并到 main 时单 PR blast radius 更小、便于逐个审核。顺序：低风险正确性 → 中风险功能。
- **PD2 — 范围 B，不做 OAuth 富流程**：DCR/PKCE/authorization_code/RFC 9728 discovery 工作量大且需产品决策；自托管 on-prem 场景下 `client_credentials`（机器对机器）往往才是对的模型。列为待评估。
- **PD3 — capability 文档如实化**：`docs/capabilities/mcp.md` 此前把已实现的 streamable/OAuth2/健康/会话/降级错标为「规划中」。每个变更同步修正其相关段落，避免文档与实现长期背离。
- **PD4 — 测试分层**：MCP 结果/协议逻辑为纯逻辑 + mock 边界（monkeypatch `_post_jsonrpc`、注入 fake session / `_active_sessions`），零真实 I/O，归 `tests/unit/`（与既有 `test_mcp_degradation.py` 同模式）；涉及 respx 全栈注册流的归 `tests/integration/test_mcp_client.py`。收尾跑 `scripts/check_test_layers.py`。

---

## 变更 1：mcp-result-fidelity（工具结果保真）

**做了什么**
- 新增被 stdio 与 http 两条调用路径共用的结果规范化：`_field`（dict/对象双形态字段读取）、`_approx_bytes`、`_media_marker`、`_block_to_text`、`_normalize_tool_result`。
- `_call_stdio_tool` / `_call_http_tool` 改为收集完整 `content` + `structuredContent` + `isError` 并调用规范化函数，保留既有降级/认证短路逻辑不变。
- 新增 spec `mcp-result-handling`；新增 `tests/unit/test_mcp_result_handling.py`（21 用例：规范化逻辑 9 + 各 block 形态 + 两条调用路径 mock）。
- 修正 `docs/capabilities/mcp.md` 现状/规划中/待决问题/mermaid。

**问题（修复的真实缺陷）**
- P1：两条路径都只取 `content[0].text` → 多内容块被截断。
- P2：stdio `str(result.content[0].text)` 在首块为 `ImageContent`（无 `.text`）时抛 `AttributeError` —— 返回图片的 stdio 工具直接崩溃。
- P3：`isError` 被忽略 → 工具自报错误被当成功结果交给模型。
- P4：`structuredContent` 被静默丢弃。

**决策**
- **D1 单一共用规范化函数**：消除两处重复且都写错的 `content[0]` 逻辑，单点测试。
- **D2 内容块双形态适配**：`_field` 以 `isinstance(dict)` → `.get` / else `getattr` 兼容 SDK 对象与 JSON dict，调用点无需先做对象→dict 转换。
- **D3 非文本块用 marker、不落盘**：image/audio/blob → `[image: <mime>, ~N bytes]` 等简洁标记，绝不把 base64 灌入上下文；embedded resource 带 text 则内联。二进制落盘（hermes/claude-code 做法）记为未来增强，本变更不做。
- **D4 `isError` 教学式回传**：以 `MCP tool error: ` 前缀 + 错误文本返回字符串、不抛异常，遵循「工具失败也回传给模型」哲学，便于模型自纠。
- **D5 `structuredContent` 优先级**：有内容块以内容块为主；内容块为空才 `json.dumps(structuredContent)`，避免重复又不丢结构化数据。
- **D6 向后兼容**：单文本块返回原文不变（既有 `test_call_tool_*` 断言 `"42"`/`"A"`/`"B"` 仍通过）。

**改进/优化/新增点**
- 修复 stdio 图片崩溃（P2）这一会直接抛异常的 bug。
- 工具自报错误对模型可见（P3），提升 agent 自纠能力。
- 多块/结构化输出不再丢失，接入真实 MCP 服务更稳。

**验证**
- CI 门禁（`make test-unit-ci`）：`tests/unit` 1901 passed、coverage 76% ≥ 75%；本变更新增 21 用例。`ruff check` / `mypy` 对改动文件零问题；`check_test_layers` 未 flag 新测试。
- 环境 gotcha（与本变更无关，记录备查）：本地 shell 若设了 `FLEETENT_HOME`，会令 `test_paths_wiring`/`test_config_paths`/`test_db_session_paths`/`test_misc_config_paths` 4 个路径解析测试失败（import 期常量冻结到该目录，与 `delenv` 后的 live 解析不一致）。CI 不设 `FLEETENT_HOME` 故通过；本地复现 CI 用 `env -u FLEETENT_HOME make test-unit-ci`。

**送审点**
- marker 文本格式（`[image: <mime>, ~N bytes]`）是客户端内部约定、非 MCP 标准，仅供 LLM 阅读——如需可调。
- 空内容且无 structuredContent 时由旧的「返回整个 result 的 dict repr」改为返回 `""`（更干净）；如有依赖旧行为处需指出。
- 二进制落盘是否要在后续单独立项。

---

## 变更 2：mcp-client-compliance（协议合规与发现完整性）

**做了什么**
- **分页**：新增 `_list_all_tools_http`/`_list_all_tools_stdio`，按 `nextCursor` 取尽全部页，`_MAX_TOOL_PAGES=100` 上限保险；改造 `_register_http_server`/`_probe_http_tools`/`_register_stdio_server`/`_probe_stdio_tools` 复用之。
- **schema 净化**：新增 `_sanitize_input_schema`+`_rewrite_refs`，保证顶层 `type:object`+`properties`、`definitions`→`$defs` 并重写 `#/definitions/` 引用；在 `_register_tool_http`/`_register_tool_stdio` 注册前应用。
- **协议版本/能力捕获**：`McpServerConfig` 加 `protocol_version`/`capabilities` 运行时字段；`_open_session`（http）与 `_register_stdio_server`（stdio，经 `_init_result_to_dict`）经 `_capture_init_result` 捕获；`_base_headers` 在握手后回发 `MCP-Protocol-Version`。
- 新增 spec `mcp-client-compliance`；新增 `tests/unit/test_mcp_client_compliance.py`；更新 `docs/capabilities/mcp.md`。

**问题**
- P1：`tools/list` 不读 `nextCursor` → 多页服务工具被静默截断。
- P2：服务端 schema 原样塞 LLM → 缺 `type:object` 或用 `definitions` 的 schema 可致 provider 400。
- P3：丢弃 `initialize` 返回 → 不合 2025-06-18 的 `MCP-Protocol-Version` 回发要求；能力信息缺失，无法为 resources/prompts 门控。

**决策**
- **D1 分页助手单点化**：注册与 probe 复用同一分页逻辑；`_MAX_TOOL_PAGES` 上限 + 警告日志，防死循环游标静默截断。
- **D2 schema 净化保守化**：只做语义等价、不会破坏合法 schema 的变换（`type:object`+`properties` 兜底、`definitions`→`$defs`+ref 重写）；深拷贝、绝不抛、异常回退安全默认。**显式不做** nullable union 折叠（高风险、provider 专项）——记为待评估。理由：自动合并到 main，净化必须零破坏面。
- **D3 能力存 dict、版本头时序**：`capabilities` 统一存 dict（http 原样；stdio 经 `model_dump(exclude_none=True)`），为 Change 6 resources/prompts 门控铺路；`MCP-Protocol-Version` 仅在 `protocol_version` 置位（即握手后）才加，故首个 initialize 不带、后续带，符合规范。

**改进/优化/新增点**
- 多页工具不再丢失（P1）；问题 schema 不再触发 provider 400（P2）；HTTP 合 2025-06-18 版本头（P3）；能力捕获为后续 resources/prompts 打基础。

**验证**
- `make test-unit-ci`（含合并 main 后回归）全绿、coverage ≥ 75%；改动文件 ruff/mypy 零问题；`check_test_layers` 未 flag 新测试。

**送审点**
- `_MAX_TOOL_PAGES=100`（约上限 100 页工具）是否合适。
- `definitions`→`$defs` 重写：当同层已有 `$defs` 时不动以避免覆盖（罕见边界）。
- nullable union 折叠未做——若实际接入的服务/provider 需要，再单独立项。

---

## 变更 3：mcp-stdio-isolation（stdio 子进程环境隔离 · 安全）

**做了什么**
- 新增 `_SAFE_ENV_KEYS_POSIX`/`_SAFE_ENV_KEYS_WIN` 白名单、`_safe_base_env()`、`_subprocess_env(server)`。
- `_register_stdio_server` 与 `_probe_stdio_tools` 的子进程 env 由 `{**os.environ, **server.env} if server.env else None` 改为 `_subprocess_env(server)`（= 安全白名单 + server 显式 env）。
- 新增 spec `mcp-stdio-isolation`；新增 `tests/unit/test_mcp_stdio_isolation.py`；更新 `docs/capabilities/mcp.md`。

**问题**
- P1（安全）：server 声明任意 env 时，`{**os.environ, ...}` 把整个平台环境（`DATABASE_URL`/`ANTHROPIC_API_KEY`/各类 token）透传给第三方 stdio MCP 子进程。接线红测的报错直接显示真实 `ATLASSIAN_API_TOKEN_ADMIN` 等被泄漏——确证漏洞。

**决策**
- **D1 自带白名单、不依赖 SDK 私有 API**：镜像 MCP SDK `DEFAULT_INHERITED_ENV_VARS` 并补 locale/temp 等运行必需项，避免 import SDK 内部 `get_default_environment`。
- **D2 单点 `_subprocess_env` + 始终传 dict**：register 与 probe 一致；旧的「空 env→None→SDK 默认」与新「空 env→白名单」等价安全，非空 env 由泄漏全环境改为仅白名单（修复）。
- **D3 显式转发模型**：`server.env` 对同名键覆盖白名单；需把宿主密钥传入子进程时在 `env` 显式声明（安全、可审计）。**不新增** `env_passthrough` 配置字段以保持本变更收敛在 client.py（记为未来增强）。

**改进/优化/新增点**
- 关闭「第三方 stdio MCP 子进程可读平台所有密钥」这一数据主权风险。
- register/probe 行为一致化（始终传受控 env）。

**验证**
- 接线红测先暴露真实泄漏，再改为白名单后转绿；`make test-unit-ci` 全绿、coverage ≥ 75%；改动文件 ruff/mypy 零问题。

**送审点（行为变化，非缺陷）**
- 此前依赖**隐式继承**白名单外宿主变量的 stdio 服务，需改为在 `server.env` 显式声明——这是修复的安全意图。若有此类部署，部署时需补 `env`。
- 白名单集合（POSIX/WIN）是否需要按实际接入的服务再补项。

---

## 变更 4：mcp-per-server-timeout（per-server 可配超时）

**做了什么**
- `McpServerConfig` 加 `connect_timeout`（默认 10.0）/`call_timeout`（默认 30.0）。
- client.py 5 处 httpx 用点改 per-server：`_probe_once`/`_fetch_client_credentials_token`/`_register_http_server`/`_probe_http_tools` 用 `connect_timeout`，`_call_http_tool` 用 `call_timeout`；`_close_http_sessions` 保持固定。
- `config.McpServerSettings` 加同名可选字段；`agent_app` 的 `McpServerConfig(...)` 映射透传——agent.yaml 的 `mcp_servers` 条目可声明 per-server 超时。
- 新增 spec `mcp-per-server-timeout`；新增 `tests/unit/test_mcp_per_server_timeout.py`；更新 `docs/capabilities/mcp.md`。

**问题**
- P1：所有 HTTP 超时写死（连接 10s / 调用 30s）。企业内网 MCP 服务快慢差异大，慢服务被 30s 硬切、快服务想更紧超时——应 per-server 可配。

**决策**
- **D1 两个 per-server 字段 + 用点映射**：连接类（发现/探活/OAuth/注册）用 `connect_timeout`，工具调用用 `call_timeout`；`_close_http_sessions` 单 client 服务全部、无单一 server 归属，保持固定。
- **D2 经 agent.yaml 直达、不碰 DB 迁移**：`McpServerSettings` 加可选字段（默认等于现状，向后兼容）+ `agent_app` 透传，agent 运行时即可 per-server 调超时。DB/admin 持久化（store 加列 + 迁移 + admin API）记为未来机械跟进。
- **D3 不做 `resetTimeoutOnProgress`**：fleetent HTTP 传输为非流式请求/响应（读完整 body），进度重置需流式读改造，宜与未来「Streamable HTTP 流恢复」一并做。

**改进/优化/新增点**
- 消除 6 处魔法数字超时；慢/快 MCP 服务可分别调；默认零行为变化。

**验证**
- `make test-unit-ci` 全绿、coverage ≥ 75%；改动文件 ruff/mypy 零问题。

**送审点**
- per-server 超时仅经 agent.yaml 可设；DB authoring 路径暂用默认（需要时补 store 列 + 迁移）。
- 默认 10s/30s 是否合适；`_close_http_sessions` 固定 10s 是否需可配。

---

## 变更 5：mcp-list-changed（stdio `tools/list_changed` 动态刷新）

**做了什么**
- `McpServerConfig` 加 `_list_refresh_lock`（去重锁）。
- 新增 `_is_tools_list_changed`（按 `root.method` 检测）、同步原子的 `_reregister_stdio_tools`（删 `{id}__*` + 重注册，仅 scope=None）、`_refresh_stdio_tools`（identity guard + 锁去重 + 原地重注册）、`_make_message_handler`（检测 list_changed → `asyncio.create_task` 独立刷新）。
- `_register_stdio_server` 给 `ClientSession` 传 `message_handler=_make_message_handler(server, scope)`。
- 新增 spec `mcp-dynamic-tools`；新增 `tests/unit/test_mcp_list_changed.py`；更新 `docs/capabilities/mcp.md`。

**问题**
- P1：stdio 服务运行时增删工具并发 `tools/list_changed`，fleetent 抓静态列表后忽略通知 → 工具变更需重启才反映。

**决策**
- **D1 独立任务刷新，绝不内联**：handler 内 `create_task`（同 `_schedule_reconnect` 的 fire-and-forget），避免在 handler 占用 stdio 读循环时向同一流发请求（hermes 实测 wedge）。
- **D2 identity guard + 去重锁**：会话被替换（重连）后的陈旧通知忽略；锁 locked 即返回，合并通知风暴；锁内再校验 identity。
- **D3 原地重注册、同步原子**：`_reregister_stdio_tools` 无 await，单线程协作调度下与 `get_schemas` 等同步读不交错——无 dict-changed-during-iteration 竞态。工具 call 闭包调用时动态查 `_active_sessions`，替换条目不破在途调用。
- **D4 仅 stdio**：HTTP 无持久 server→client 通道（需 GET 流/流恢复），list_changed 不适用，记为与未来流恢复一并做。检测用 `method` 字符串、不硬绑 SDK 类型。

**改进/优化/新增点**
- stdio 工具变更可在不重启下反映到 agent 工具表，且并发安全。

**验证**
- `make test-unit-ci` 全绿、coverage ≥ 75%；改动文件 ruff/mypy 零问题；全链路（handler→任务→刷新）测试覆盖。

**送审点**
- 仅刷新 scope=None 共享注册表；agent-scoped 动态刷新记为后续（与现有 agent-scoped 注册局限一致）。
- prompts/resources 的 list_changed（Change 6 的合成工具）其动态刷新可后续。
- handler 中 `create_task` fire-and-forget（与既有 reconnect 一致，未存 task 引用）。

---

## 变更 6：mcp-resources-prompts（resources/prompts 合成工具）

**做了什么**
- 新增 `_UTILITY_METHODS`/`_UTILITY_TOOL_SPECS`、`_utility_params`、`_jsonify`、`_call_http_utility`/`_call_stdio_utility`/`_call_utility`、`_register_utility_tool`/`_register_utility_tools`。
- 对 advertised `resources`/`prompts` 的服务注册 `{id}__list_resources`/`__read_resource`、`__list_prompts`/`__get_prompt` 合成工具；调用分派到 MCP 方法（http JSON-RPC / stdio SDK），结果经 `_jsonify` JSON 文本化。
- 在 `_register_http_server`/`_register_stdio_server`/`_reregister_stdio_tools` 末尾调用 `_register_utility_tools`（刷新后保留）。
- 新增 spec `mcp-resources-prompts`；新增 `tests/unit/test_mcp_resources_prompts.py`；更新 `docs/capabilities/mcp.md`。

**问题**
- P1：fleetent 只暴露 MCP tools，resources/prompts 无法被 agent 使用，尽管服务已 advertise。

**决策**
- **D1 合成工具、不改 agent_loop**：resources/prompts 暴露为普通工具（`{id}__*` 命名空间），agent 经既有工具机制访问；无需新概念。
- **D2 capability 门控**：仅 advertised 对应 capability 才注册，不给不支持的服务注册无效工具；仅 scope=None 进共享表（与现有一致）。
- **D3 统一分派 + auth/health 短路**：`_call_utility` 复用 `_call_*_tool` 同款短路；http 用 `call_timeout`+disconnect 处理，stdio 按 util_name 调 SDK 方法；结果 `_jsonify`（pydantic model_dump / dict → JSON）。
- **D4 与刷新/降级一致**：刷新（Change 5）末尾重注册合成工具避免丢失；降级经 `{id}__*` 前缀的 schema 可见性过滤自动隐藏，无需额外处理。

**改进/优化/新增点**
- fleetent 首次具备 resources/prompts 访问能力（此前仅 tools）。

**验证**
- `make test-unit-ci` 全绿、coverage ≥ 75%；改动文件 ruff/mypy 零问题。

**送审点**
- resources/prompts 结果统一 JSON 文本化（对 LLM 足够；更精细呈现可后续）。
- resources/prompts 的 list_changed 动态刷新未做（本程序只对 tools）。
- 仅 scope=None 注册；agent-scoped 合成工具记为后续。

---

## 程序总结（MCP 增强程序 2026-06 · 范围 B 全部完成）

6 个聚焦 OpenSpec 变更已全部 TDD 实施、归档、并经 bb-pr 自动合并到 `main`（每个均 `make test-unit-ci` 全绿 + coverage ≥ 75% + 改动文件 ruff/mypy 干净）：

| # | change | PR | 性质 |
|---|---|---|---|
| 1 | mcp-result-fidelity | #142 | 🔴 真 bug（stdio 图片崩溃、isError 被吞）+ 多块/structuredContent |
| 2 | mcp-client-compliance | #145 | 🔴 分页正确性 + 🟠 schema 净化/协议版本合规 + 能力捕获 |
| 3 | mcp-stdio-isolation | #148 | 🔴 安全（堵住平台密钥透传第三方子进程）|
| 4 | mcp-per-server-timeout | #152 | 🟡 per-server 可配超时 |
| 5 | mcp-list-changed | #154 | 🟡 stdio 动态工具刷新（并发安全）|
| 6 | mcp-resources-prompts | (本变更) | 🟡 resources/prompts 合成工具 |

**fleetent MCP 现已具备**：完整结果保真、分页/schema/协议版本合规、能力捕获、安全 stdio 隔离、per-server 超时、stdio 动态刷新、resources/prompts——叠加既有的双传输/会话连续性/健康重连/三档降级/OAuth2/agent-scoped，达到四参考项目中第一梯队的 MCP 客户端成熟度。

**显式延后（未来，需要时再单独立项）**：OAuth 富流程（DCR/PKCE/authorization_code/RFC 9728）；Streamable HTTP 流恢复（GET 流 + Last-Event-ID）+ 其上的 HTTP list_changed、进度重置超时；schema nullable-union 折叠；per-server 超时与 MCP server 定义的 DB/admin 持久化；二进制结果落盘；resources/prompts 的 @mention/slash 一等公民 UX 与其 list_changed。
