## Why

`tool_registry.dispatch()` 当前只做「访问控制 → 调用 → 返回结果」，**凭证注入路径尚未打通**（见 `docs/capabilities/tools.md` 规划项「connector 注入接通」）。`@tool` 装饰器目前仅接受 `risk_level`，不接受 `connector` / `scopes`；而 `src/fleetent/` 下并不存在 `connectors` 模块——`get_credential` / `NeedsConsent` / `Credential` 仅在文档里出现，代码侧完全缺失。

后果是：任何依赖外部 connector（如 google-drive、github）的工具，无法在执行时拿到已授权的 client。工具作者只能把 token 当成 LLM 可见参数手动传递——既不安全（token 进入 LLM schema 与 trace），也无法走统一的「未授权 → 返回 consent URL 短路」流程。这是 v1.0 工具生态的地基缺口：connector 凭证注入是所有外部集成工具的前置依赖。

## What Changes

- 新增 **connectors 凭证接口**（`src/fleetent/connectors.py`）：定义 `Credential` / `NeedsConsent` 数据类与 `get_credential(user_id, connector, scopes) -> Credential | NeedsConsent` 入口；本次提供接口契约与一个可注入的 provider 缝（默认 provider 返回 `NeedsConsent`，真实 OAuth 存储/刷新是后续 change）。
- 扩展 **`@tool` 装饰器**：新增 `connector: str | None` 与 `scopes: list[str] | None` 声明；记录到独立的 connector 元数据表（不进入 LLM 可见 schema）。
- 在 **`dispatch` 中接通凭证注入**：声明了 connector 的工具，dispatch 先调 `connectors.get_credential`；
  - 返回 `Credential` → 将构造好的 client 作为**隐藏 keyword-only 参数 `client`** 注入工具调用（不出现在 LLM schema）；
  - 返回 `NeedsConsent` → **短路**，工具不执行，返回 consent URL 提示给 LLM。
- **凭证不泄漏**：注入的 `client` / `Credential` 中的 secret 绝不进入 dispatch 返回值、`eval_logger` trace、异常文本或 LLM schema；为此约束 dispatch 不把 `client` 计入序列化参数，且 `Credential` 的 `repr` / `str` 屏蔽 secret。
- `dispatch` 新增 `user_id` 参数（凭证按用户隔离），向后兼容（无 connector 的工具行为不变）。

## Capabilities

### New Capabilities
- `connector-credential-injection`: 在 `tool_registry.dispatch` 中接通 connector 凭证注入——`@tool` 声明 connector/scopes、dispatch 调用 `connectors.get_credential`、`Credential` 注入隐藏 `client` 参数、`NeedsConsent` 短路返回 consent URL，且凭证全程不泄漏到 LLM schema / trace / 异常文本。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。tool_registry 既有的注册/schema/访问控制行为保持不变；本次新增的是凭证注入这一新行为。 -->

## Impact

- **代码**：
  - 新增 `src/fleetent/connectors.py`（`Credential` / `NeedsConsent` 数据类 + `get_credential` + 可注入 provider 缝）。
  - 修改 `src/fleetent/tool_registry.py`：`@tool` 接受 `connector` / `scopes` 并记录到 `_connectors` 元数据表；`dispatch` 新增 `user_id` 参数，声明 connector 时走 `get_credential` → 注入 `client` 隐藏参数 / `NeedsConsent` 短路；`_build_schema` 已天然排除 keyword-only `client`（保证不进 LLM schema）。
  - `src/fleetent/agent_loop.py` 的 `_safe_dispatch` 调用处补传 `user_id`。
- **配置**：无新增 env 字段；真实 OAuth provider 的存储/凭证由后续 change 引入（本次 provider 缝可 monkeypatch 注入测试 fake）。
- **测试**：新增 `tests/test_connectors.py`、`tests/test_tool_registry.py` 补充 connector 注入用例；`connectors.get_credential` provider 按规范 mock（monkeypatch provider，不发真实 OAuth 请求）。
- **不影响**：无 connector 声明的工具 dispatch、`get_schemas` / 访问控制 / `risk_level` 既有行为；不引入 AI 框架、ORM、云托管专有服务；不引入新第三方依赖。
