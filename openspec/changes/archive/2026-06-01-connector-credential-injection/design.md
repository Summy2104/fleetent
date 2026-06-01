## Context

`tool_registry.dispatch()`（`tool_registry.py` 行 61-82）当前：参数反序列化 → `agent_policy.check_tool_access` → `fn(**kwargs)` → 返回字符串。**没有凭证注入**。`@tool`（行 26-45）只记录 `risk_level` 到 `_risk_levels`，不接受 `connector` / `scopes`。

`docs/capabilities/tools.md` 把「connector 注入接通」列为 v1.0 规划项，并描绘了目标流程（dispatch → 声明 connector? → `connectors.get_credential` → `NeedsConsent` 短路 / `Credential` 注入隐藏 `client` 参数）。但 `src/fleetent/` 下**不存在 `connectors` 模块**——`get_credential` / `NeedsConsent` / `Credential` 仅是文档约定。注意：`im_connector_*` 系列模块是 IM 平台适配器（Slack/Telegram 连接管理），与工具凭证 connector 无关，不可混用。

`eval_logger.log_run` 经 `_serialize` 把全部 messages（含工具参数与结果）写入 JSONL trace。`_build_schema`（行 85-101）遍历 `inspect.signature`，把所有参数都列入 LLM 可见 schema——keyword-only 参数当前**也会进 schema**，需在本次确认隐藏参数过滤口径。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；禁止全局可变状态（provider / 路径可 monkeypatch 注入）；禁止云托管专有服务；新模块结构 import → 常量 → 数据类 → 函数；mypy strict；TDD Hard Gate；测试 mock 外部依赖不发真实请求。

## Goals / Non-Goals

**Goals:**
- 定义 `connectors` 模块的凭证接口契约：`Credential` / `NeedsConsent` 数据类 + `get_credential(user_id, connector, scopes)`。
- `@tool` 支持 `connector` / `scopes` 声明，记录到独立元数据表（不进 LLM schema）。
- `dispatch` 接通凭证注入：`Credential` → 注入隐藏 `client` 参数；`NeedsConsent` → 短路返回 consent URL。
- 凭证全程不泄漏：不进 LLM schema、不进 dispatch 返回值、不进 trace、不进异常文本。
- 无 connector 声明的工具行为完全不变（向后兼容）。

**Non-Goals:**
- 不实现真实 OAuth token 的存储 / 刷新 / 授权回调（后续 connector-oauth-store change 负责）——本次默认 provider 返回 `NeedsConsent`，真实凭证经可注入 provider 缝由后续提供。
- 不实现工具超时 / 参数消毒 / 结果截断（tools.md 其它规划项，各自后续）。
- 不改动 `get_schemas` / `risk_level` / 访问控制 / 既有内置工具的行为。
- 不为具体 connector（google-drive、github 等）实现 client 构造细节——client 由 provider 在 `Credential` 中提供，dispatch 只负责注入。

## Decisions

### D1：connector 元数据与 risk_level 平行存储，不混入 schema
`@tool` 新增 `connector: str | None = None`、`scopes: list[str] | None = None`，记录到 `tool_registry` 模块级 `_connectors: dict[str, tuple[str, list[str]]]`（与 `_risk_levels` 平行）。提供 `get_connector(name) -> tuple[str, list[str]] | None`。
**为何**：与既有 `_risk_levels` 模式一致，最小侵入；connector 元数据是 governance / dispatch 用的运行态，不该出现在面向 LLM 的 JSON schema 里。
**Alternatives**：①把 connector 塞进 schema 的 `function` 字段——被否，污染 LLM 可见契约且无意义；②单独 dataclass 注册表替代两张 dict——被否，与既有 `_risk_levels` 风格割裂，收益不足。

### D2：`connectors` 模块定义契约 + 可注入 provider 缝
新增 `src/fleetent/connectors.py`：
- `Credential` 数据类：携带工具执行所需的 `client`（任意已构造好的客户端对象）；secret 字段经 `repr=False` / 自定义 `__repr__` 屏蔽。
- `NeedsConsent` 数据类：携带 `consent_url: str`、`connector: str`，供 dispatch 短路时返回给 LLM。
- `get_credential(user_id, connector, scopes) -> Credential | NeedsConsent`：委派给模块级可替换的 `_provider`（默认 provider 返回 `NeedsConsent`，因为真实 OAuth 存储未实现）。提供 `set_provider()` / 模块级 `_provider` 供测试 monkeypatch。
**为何**：本 change 的范围是「接通注入路径」，不是实现 OAuth。把真实凭证来源抽象成 provider 缝，使 dispatch 可单测（注入 fake provider 返回 `Credential` / `NeedsConsent`），同时为后续 OAuth store 留下零侵入接入点。
**Alternatives**：①直接在 dispatch 里写 OAuth 逻辑——被否，超范围且无法在无外部依赖下单测；②provider 用全局可变单例——被否，违反「禁止全局可变状态」，故设计为可 monkeypatch 的模块级名字。

### D3：dispatch 注入隐藏 `client` 参数，secret 不进序列化路径
`dispatch` 新增 `user_id: str | None = None`。流程：访问控制通过后，查 `get_connector(name)`：
- 无 connector → 现状不变（`fn(**kwargs)`）。
- 有 connector → `cred = get_credential(user_id, connector, scopes)`：
  - `NeedsConsent` → 返回固定格式提示串（含 `consent_url`），**不调用工具**。
  - `Credential` → `fn(**kwargs, client=cred.client)`，`client` 作为 keyword-only 隐藏参数注入。
`kwargs`（来自 LLM 的 `arguments_json`）**不含** `client`；注入的 `client` 不写回 `kwargs`、不进 dispatch 返回值。
**为何**：`client` 经 keyword-only 注入，工具签名 `def t(q: str, *, client)` 中 `client` 不进 `_build_schema`（D4 保证），故 LLM 不可见、不可控；secret 只存在于 client 对象内，不流经任何序列化点。
**Alternatives**：①把凭证作为普通参数注入——被否，会进 schema 且 LLM 可篡改；②dispatch 自行构造 client——被否，client 构造是 connector 专属知识，归 provider。

### D4：保证 keyword-only `client` 不进 LLM schema
确认并（如需）修正 `_build_schema`：keyword-only 参数（`param.kind == KEYWORD_ONLY`）以及名为 `client` 的注入参数**不进** `properties` / `required`。
**为何**：tools.md 验收场景 4「隐藏参数不进 schema」是硬契约；凭证注入安全性直接依赖此过滤。实现首步先用测试核实现状 `_build_schema` 是否已排除 keyword-only，未排除则补。
**Open**：现状 `_build_schema` 遍历全部 `sig.parameters`，疑似未区分 keyword-only——见 Open Questions，实现第一步核实。

### D5：凭证不泄漏到 trace / 异常文本
- `Credential` 的 secret 字段 `__repr__` / `__str__` 屏蔽为 `Credential(connector=..., client=<redacted>)` 形态。
- dispatch 注入失败（provider 抛错、client 不可用）时，错误文本**不得**包含 secret——异常归一化由 agent_loop 既有 `_safe_dispatch` 捕获，本次确保 `connectors` / dispatch 抛出的异常消息本身不含凭证。
- trace 写入的是 messages（工具 args/result），`client` 既不在 args 也不在 result，天然不入 trace；增加回归测试守卫此不变量。
**为何**：数据主权 + 避免 on-premises 部署把 OAuth token 落盘到明文 JSONL trace。
**Alternatives**：在 eval_logger 做凭证脱敏——被否，治标且易漏；从源头不让 secret 进入可序列化路径更可靠。

### D6：`user_id` 向后兼容
`dispatch(name, arguments_json, allowed_tools=None, is_sub_agent=False, user_id=None)`：`user_id` 末位 kw 默认 None。无 connector 的工具完全不读 `user_id`；有 connector 但 `user_id is None` 时，`get_credential` 按未授权处理（返回 `NeedsConsent`）。
**为何**：现有 dispatch 调用点（`agent_loop`、`sub_agent`、测试）不传 user_id 也不报错；凭证按用户隔离要求 user_id，缺失即视为无凭证，安全降级。

## Risks / Trade-offs

- [现状 `_build_schema` 可能未排除 keyword-only，导致 `client` 进 schema 泄漏] → D4 实现第一步用测试核实并修正；这是凭证不泄漏的前置硬约束。
- [`connectors` 与 `im_connector_*` 命名相近易混淆] → 模块 docstring 明确「工具 OAuth 凭证，非 IM 平台连接」；spec/design 显式区分。
- [默认 provider 永远返回 NeedsConsent，集成工具暂不可真正执行] → 本次范围即「接通路径」，真实 provider 是后续 change；provider 缝可注入保证 dispatch 路径本身已完整可测。
- [secret 经异常 / 日志意外泄漏] → D5 双保险：`Credential.__repr__` 屏蔽 + 回归测试断言 trace / 错误文本不含 secret。
- [新增 `user_id` 参数改变 dispatch 签名] → 末位 kw 默认 None，向后兼容；调用点逐一补传。

## Open Questions

- 现状 `_build_schema`（tool_registry.py 行 85-101）是否已排除 keyword-only 参数——实现第一步用 `tests/test_tool_registry.py` 针对 `def t(q, *, client)` 核实；未排除则在本次按 D4 补过滤。
- `NeedsConsent` 返回给 LLM 的提示串格式（是否含 connector 名 + scopes 列表）——以「LLM 能据此引导用户授权且不含 secret」为准，实现时定稿。
- `Credential.client` 的类型标注（`Any` vs 协议）——本次用 `Any`（client 形态因 connector 而异），后续具体 connector 落地时可收窄。
