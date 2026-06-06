# MCP 能力差距分析（四参考项目 → fleetent）

> 日期：2026-06-06
> 方法：深度阅读四个参考项目的 MCP 机制（各派一个 agent 通读源码/文档并结构化回传），交叉本仓 `src/fleetent/integrations/mcp/client.py` 与 OpenSpec 既有 MCP spec 核实。
> 参考项目：
> - `/opt/gopath/src/github.com/NousResearch/hermes-agent`（Python，官方 `mcp` SDK，client 重度硬化）
> - `/opt/gopath/src/github.com/anthropics/claude-code`（公开 docs + plugin skill + CHANGELOG，无 CLI 源码）
> - `/opt/gopath/src/github.com/openclaw/openclaw`（TypeScript，官方 SDK，client + 两类 server）
> - `/opt/gopath/src/github.com/anomalyco/opencode`（TypeScript/Bun，官方 SDK，client-only）
> 既有相关调研：`docs/archive/internals/{industry-survey,reference-survey-hermes,reference-survey-openclaw}.md`
> 用途：作为「MCP 增强程序 2026-06」6 个 OpenSpec 变更的依据。

## 一句话结论

fleetent 的 MCP **连接韧性在四个项目里属第一梯队**（健康状态机 + 指数退避重连 + degrade/strict/silent 降级 + agent-scoped 隔离；opencode / openclaw 根本没有重连），但**协议广度落后**（此前只支持 tools、只取单内容块、无分页、无动态刷新、无 resources/prompts），且 `docs/capabilities/mcp.md` 此前严重过时。

## fleetent MCP 现状

**已实现**：stdio + Streamable HTTP（POST：initialize 握手、Accept 协商、`Mcp-Session-Id` 会话、SSE 解析、单调 request id）、会话连续性（404→重建重试）、健康/重连状态机、degrade/strict/silent 降级 + schema 可见性过滤、OAuth2 client_credentials（缓存/刷新/sticky 不可用）、API Key + 自定义 headers、`{server}__{tool}` 命名空间、`(agent_scope, server_id)` 注册隔离、一次性连通性 `probe`。

**相对领先**：双下划线命名空间（比 hermes/opencode 单下划线更干净）、agent-scoped 注册（三参考项目均为全局配置）、显式重连状态机（opencode/openclaw 无）。

## 四参考项目要点

- **hermes-agent**：单文件 3711 行 client；专用事件循环线程 + per-server actor；**provider-agnostic schema 净化**（`definitions`→`$defs`、nullable union 折叠、`required` 修剪——防 Anthropic/Gemini/Moonshot 400）；`tools/list_changed` 用独立 task + per-server RPC 锁 + identity guard（规避 stdio 流 wedge）；resources/prompts 作为 **capability-gated 合成工具**；server→LLM **sampling**；circuit breaker（含给 LLM 的「勿重试」提示）；idle keepalive；OAuth 2.1 PKCE + DCR + 跨进程 token disk-watch + 401 dedup；子进程 env 白名单、凭据脱敏、URL 校验、OSV 恶意包检查、orphan-PID 回收。
- **claude-code（docs/CHANGELOG）**：`.mcp.json` 多 scope；list_changed 动态刷新；resources(@提及)/prompts(slash)/**elicitation**/progress；**拒绝的工具在送模型前剔除**（schema 期 enforce）；**MCP 工具按上下文预算延迟加载**（MCPSearch auto:N）+ 描述 2KB 上限；per-server 5s 连接上限 + 非阻塞启动；SSE 中断不再永久挂起；**structuredContent + 多块错误内容**；二进制落盘而非 base64 入上下文；OAuth RFC 9728 + DCR + step-up；首次连接 per-server 信任弹窗。
- **openclaw**：官方 SDK；stdio/SSE/HTTP；**`tools/list` 完整游标分页**；命名 64 字符上限 + 确定性排序（稳定 prompt cache）；TypeBox 校验净化 schema；结果保留 `isError`/`structuredContent`；**跨域重定向剥离 Authorization** + URL 脱敏；子进程 dangerous-env 剥离 + SIGTERM→SIGKILL 进程树；config-fingerprint 失效 + idle GC。无重连、无 OAuth client、tools-only。
- **opencode**：官方 SDK；StreamableHTTP→SSE 自动回退；**typed status 状态机**（connected/disabled/failed/needs_auth/needs_client_registration）；`tools/list_changed` + identity guard；`resetTimeoutOnProgress`；富结果（text/image→data-URL/resource→附件）；prompts→slash、resources→@提及；OAuth DCR+PKCE+CSRF + 0600 URL-bound token store；resource-safe connect + stdio PID-tree 回收；每个 MCP 调用走审批 + 会话级 auto-approve 缓存。无重连/健康检查。

## 差距表（按主题；✓=该项目优于 fleetent）

| 主题 | fleetent 此前 | hermes | claude-code | openclaw | opencode | 性质 |
|---|---|---|---|---|---|---|
| 工具结果（多块/图片/embedded/`structuredContent`/`isError`） | 仅 `content[0].text`，图片崩溃，isError 忽略 | ✓ | ✓ | ✓ | ✓ | 🔴真 bug + 一致共识 |
| `tools/list` 分页 | 无 | — | — | ✓ | — | 🔴正确性 |
| stdio 子进程 env 隔离 | 透传整个平台 env | ✓ | ✓(scrub) | ✓ | — | 🔴安全 |
| 输入 schema 净化 | 原样透传 | ✓ | — | ✓ | — | 🟠provider 400 |
| 协议版本回发 header | 无 | ✓ | — | (server 协商) | — | 🟠合规 |
| per-server 超时 + 进度重置 | 写死 10s/30s | ✓ | ✓ | ✓ | ✓ | 🟡韧性 |
| `tools/list_changed` 动态刷新 | 无 | ✓ | ✓ | — | ✓ | 🟡功能 |
| resources / prompts | 无 | ✓ | ✓ | — | ✓ | 🟡功能扩展 |
| OAuth 富流程（DCR/PKCE/authz_code） | 仅 client_credentials | ✓ | ✓ | — | ✓ | 🟡需产品决策 |
| 自动重连/健康 | ✓ 有 | ✓ | ✓ | ✗ | ✗ | fleetent 领先 |
| agent-scoped 隔离 | ✓ 有 | toolset 窄化 | — | 部分 | ✗ | fleetent 领先 |

注：跨域重定向泄露 Authorization——openclaw/hermes 手写 fetch 故需手动剥离；fleetent 用 httpx，其默认在跨 origin 重定向时剥离 `Authorization`，故非 fleetent bug（将以测试核实而非假设）。

## 6 变更程序映射（范围 B：正确性+安全 + 协议广度，不含 OAuth 富流程）

1. `mcp-result-fidelity`（本变更）：工具结果多块/非文本/`isError`/`structuredContent`。🔴含真 bug。
2. `mcp-client-compliance`：`tools/list` 分页 + 输入 schema 净化 + 协议版本 header/能力捕获。
3. `mcp-stdio-isolation`：stdio 子进程 env 白名单。🔴安全。
4. `mcp-per-server-timeout`：per-server 超时 + `resetTimeoutOnProgress`。
5. `mcp-list-changed`：`tools/list_changed` 动态刷新（独立 task + RPC 锁）。
6. `mcp-resources-prompts`：capability-gated resources/prompts 合成工具。

**显式不在本程序**：OAuth 富流程（DCR/PKCE/authorization_code/RFC 9728）——自托管场景下 client_credentials 往往已足够，列为待产品决策；二进制结果落盘——本程序用文本 marker，落盘为未来增强。
