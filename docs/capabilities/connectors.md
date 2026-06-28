# connectors

## 概述

platform 侧工具 OAuth Vault 已退役。当前保留的是 agent 侧 connector seam：工具仍可声明 `@tool(connector=...)`，dispatch 仍会在执行前统一走 `connectors.get_credential(...)`，但没有 provider 注入时会安全降级为 `NeedsConsent`。

## 现状

- `src/fleetent/connectors.py` 仍定义 `Credential` / `NeedsConsent` / `CredentialError` / `set_provider` / `get_credential`。
- `tools/registry.py` 保留 connector 元数据通道，声明了 connector 的工具会先做凭证解析。
- platform 不再提供工具凭证的控制面、持久化、授权 UI 或启动期 provider 注入。
- `fleetent agent run` 在无 platform、无管理库表环境下，凭证类工具会降级为 consent 提示，agent 对话可继续完成。

## 行为

```python
@tool(connector='github', scopes=['repo'])
def github_connection_status(*, client):
    ...
```

- 若有 agent-side provider 通过 `set_provider(...)` 注入，dispatch 委派该 provider。
- 若无 provider，`get_credential(...)` 返回 `NeedsConsent`，工具不会执行。
- `client` 仍是隐藏注入参数，不进入 LLM 可见 schema。

## 边界

- governance 负责“能不能调这个工具”。
- connectors seam 只负责“声明了 connector 的工具，凭证解析如何短路或注入”。
- 未来若恢复真实凭证能力，应在 agent 侧通过同一 seam 注入，而不是重新引入 platform 反向依赖。
