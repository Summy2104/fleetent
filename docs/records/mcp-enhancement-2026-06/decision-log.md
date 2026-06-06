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
