## Why

stdio MCP 服务以子进程运行。`integrations/mcp/client.py` 在 server 声明了任意 env 时，用 `{**os.environ, **server.env}` 把**整个平台环境**（`DATABASE_URL`、各类 API key、服务 token 等）透传给第三方 MCP 子进程。这违反最小权限与数据主权原则——一个第三方 npx/python MCP 包可读到平台所有密钥。这是一个真实的安全缺口（registration 与 probe 两处皆有）。

## What Changes

- stdio 子进程环境改为「**受控白名单 + 显式声明**」：从宿主仅继承一组经审定的安全变量（`PATH`/`HOME`/locale/临时目录等运行必需项），叠加 server 显式声明的 `env`；**不再继承整个平台环境**。
- 始终向子进程传入该受控 env（而非旧的「无显式 env 时传 None」分支），register 与 probe 行为一致。
- server 显式 `env` 保留并对同名键覆盖白名单值——需要把某个宿主密钥传入子进程时，operator 在 server 的 `env` 中显式声明（安全、可审计的模型）。

**行为变化（非缺陷）**：子进程不再隐式继承白名单之外的宿主变量。若此前某服务依赖隐式继承的宿主变量，需改为在 server `env` 中显式声明——这正是修复的安全目的。

## Capabilities

### New Capabilities
- `mcp-stdio-isolation`: 定义 stdio MCP 子进程的环境隔离——仅继承受控白名单 + 显式 `env`，不泄漏平台密钥。

### Modified Capabilities
<!-- 无：现有 mcp-client spec 未对 stdio 子进程环境继承作出要求，故为纯新增能力。 -->

## Impact

- 代码：`src/fleetent/integrations/mcp/client.py`——`_register_stdio_server` 与 `_probe_stdio_tools` 的 env 构建改用受控白名单；新增 `_safe_base_env`/`_subprocess_env`。
- 安全：第三方 stdio MCP 子进程不再获得平台密钥（`DATABASE_URL`/API key/token）。
- 行为：依赖隐式宿主变量的 stdio 服务需在 `env` 显式声明（送审说明）。
- 测试：`tests/unit/` 新增白名单/隔离用例 + register/probe 接线用例（mock，无真实子进程）。
- 依赖/外部系统：无新增依赖，不触碰 `data/`。
