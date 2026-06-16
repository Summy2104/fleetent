---
name: common-mcp-guide
description: Use when calling MCP tools in fleetent, constructing tool arguments, or debugging empty/incorrect results from MCP tool calls — especially when a parameter is a numeric-looking string ID (e.g. uid) that must NOT be coerced to an integer.
---

# MCP Tool Calling Guide

## Core Rule

在 fleetent 里 MCP 工具是**直接的工具调用**：工具名 = `{server_id}__{tool_name}`（双下划线），参数以结构化 JSON 对象传入（不存在 `key=value` 位置参数解析层）。**关键纪律：ID 类字段若服务端期望字符串，必须传字符串，不要传成整数。**

```jsonc
// ✅ 安全：numeric-looking ID 显式传字符串
{ "uid": "1224548319", "limit": 10 }

// ❌ 危险：把字符串 ID 写成整数 —— 见下方类型表
{ "uid": 1224548319, "limit": 10 }
```

## 为什么 ID 字段类型容易踩雷

很多 OpenAPI 后端把 `uid` / `account_owner` / `market` / `tag` / 逗号分隔多值串等字段定义为 `str`，但它们的值经常是纯数字字符串。一旦传成整数，服务端报 type error 或静默返回空结果。

| 字段值 | 应传类型 | 安全？ |
|-------|---------|-------|
| `limit` = 10 | int | ✅ 服务端期望 int 时安全 |
| `flag` = true | bool | ✅ |
| `status` = "active" | string | ✅ 非数字字符串天然安全 |
| `filter` = `{"k":"v"}` | object | ✅ |
| `uid` = "1224548319" | **string** | ✅ 服务端期望 str 时正确 |
| `uid` = 1224548319 | int | ❌ 服务端期望 str 时 type error / 空结果 |

**根因：** 纯数字的值若按整数传入，会丢失"这是字符串 ID"的意图。务必在工具参数里显式写成带引号的字符串。

## Quick Reference

```jsonc
// 单参数
{ "key": "value" }

// 多参数（混合类型）—— numeric-looking ID 用字符串
{ "uid": "1224548319", "limit": 10, "status": "active" }

// 多值串保持字符串，不要拆成数组（除非工具明确接受数组）
{ "market": "4,10,19" }
```

## 错误现象与定位

- 工具返回 `result: []`（空）且无报错 → numeric-looking ID 被当成整数传入
- 服务端报 `Input should be a valid string, input_type=int` → 数字值被当 int，应改成字符串
- 纯文本查询能命中、但 ID 查询命不中 → 该 ID 是 numeric string，需显式带引号
