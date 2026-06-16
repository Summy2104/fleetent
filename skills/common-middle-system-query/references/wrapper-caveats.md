# 中台 MCP 调用已知问题与约定

> NOTE (fleetent): 中台 `middle` MCP server 当前不在 my-bot 已挂载的 MCP 清单内。本文按 fleetent 直接调用约定（`middle__<tool_name>`）描述；实际运行前需在 my-bot 挂载该 `middle` server。

## 1. 调用契约（核心）

在 fleetent 里中台查询是**直接的 MCP 工具调用**：

- 工具名 = `middle__<tool_name>`（双下划线）
- 参数以结构化 JSON 对象传入
- 无参数时传空对象 `{}`

**为什么 ID 字段类型容易踩雷**（详见 `common-mcp-guide`）：

| 字段值 | 应传类型 | 风险 |
|----------|---------|------|
| `limit` = 10 | int | ✅ 服务端期望 int 时安全 |
| `flag` = true | bool | ✅ |
| `status` = "active" | str（非数字） | ✅ |
| **`uid` = 123456** | **若传成 int** | **❌ 服务端期望 str 时 type error / 空结果** |
| `filter` = `{"k":"v"}` | object | ✅ |

中台 OpenAPI 把 `uid` / `account_owner` / `market` / `tag` / `account_code` / `tx_id` / `status` 等都标为 `str` 类型，**这些字段的值经常是纯数字字符串**（`uid="123456"`、`market="4,10"`）。务必在工具参数里把它们显式传成**带引号的字符串**，保留 caller 的类型意图。

## 2. 错误码归类

所有中台 MCP 工具错误从工具返回内容透传。spoke 按以下规则解析归类：

| 工具返回包含（小写匹配） | reason | 处理建议 |
|----------------------|--------|---------|
| `unknown tool` / `tool not found` | `middle_mcp_tool_missing` | 按 `common-tool-naming.md` §3 兜底名重试一次 |
| `unknown server` / `server not found` | `middle_mcp_not_registered` | 提示运维核查 my-bot 是否挂载 `middle` MCP server |
| `401` / `403` / `unauthorized` | `missing_or_invalid_api_key` | 提示运维补中台 API Key |
| `timeout` / `connection refused` | `upstream_timeout` | 重试 1 次；仍失败建议用户收窄查询范围 |
| `--args` JSON 解析失败 / `invalid json` | `invalid_args_json` | spoke 内拼参数的代码 bug，需修复 |
| 其它错误 | `upstream_error` | 透传错误信息给用户 |

## 3. 当前能力面

- ✅ 每个中台工具以 `middle__<tool_name>` 直接调用，参数照传
- ✅ 通过结构化参数对象保留 caller 类型意图，避免数字串字段被误转 int
- ❌ **不**做 JSON schema 校验（`middle` server 端会按 OpenAPI 校验）
- ❌ **不**做 path 白名单校验（中台 server 端有 server-side 白名单）
- ❌ **不**做 retry / circuit breaker（这是 spoke 的职责）

## 4. 与 NS hub (`common-ns-system-query`) 的差异

| 维度 | NS | 中台 (`middle`) |
|------|-------------|------------------|
| 强制首参 | `slackUserId`（Step 0 sender_id 校验） | ❌ 无 |
| `_meta` 注入 | `_meta.slackUserId` | ❌ 无 |
| method 参数 | 显式 `get`/`post` 二选一 | ❌ 无（由工具名决定） |
| 类型安全 | 依赖 caller 用嵌套 JSON | 直接结构化参数，无 kv 注入点 |

差异原因：

- NS 大量端点采用 `path` + `queryParams` 嵌套结构；中台直接把字段平铺在顶层，每个字段都是独立键，类型暴露面更大，必须显式带引号传字符串 ID
- NS 涉及业务流程写操作（POST `/v1/accounts/digital_coin` 等），需追溯到用户做审计；中台目前只读账户域数据，`X-API-Key` 鉴权 + per-agent server 隔离已足够（key 本身已绑定权限范围）

## 5. 参数构造要点

- **numeric-looking ID 用字符串**：`uid` / `account_owner` / `market` / `tag` / `account_code` / `tx_id` / `status` 等值若是纯数字，必须带引号传字符串
- **空查询**：传空对象 `{}` 表示无过滤参数（如 `middle__common_list_chains` 传 `{}` 取默认 50 条）
- **空字符串字段**：直接省略该键（不要写 `"key": ""`，中台会作为显式空字符串过滤）
- **多值逗号串**：保持字符串形态如 `"market": "4,10,19"`，**不要**拆为数组（除非工具明确接受数组）
- **datetime**：保留原字面字符串如 `"tx_start_time": "2026-04-29 00:00:00"`，**不要**做 ISO 转换
- **嵌套对象**：极少数中台工具需要嵌套结构，原样嵌入 `{"outer": {"inner": "value"}}`

## 6. 信任模型

中台调用通过 `middle` MCP server 自身配置注入 `X-API-Key` 鉴权，agent 不接触 Token。不同 X-API-Key 对应不同的中台权限范围，per-agent 的 `middle` server 配置确保每个 agent 只能访问自己 key 授权的数据。中台目前只读账户域数据；若未来新增写端点或安全审计要求升级，可参考 NS hub 引入 sender_id 强校验。
