# eval_logger.py

## 两个写入函数

| 函数 | 用途 |
|------|------|
| `log_run(user_input, reply, messages, elapsed_s, usage)` | CLI 和非流式 HTTP 路径；包含 token 用量 |
| `log(user_id, messages, response, platform, ...)` | IM 网关路径；包含 platform/session/channel/thread/message_id 等 IM 元数据 |

两个函数写到同一文件（`data/traces.jsonl`），通过字段区分来源。没有 IM 元数据的字段不写入（不出现 `null`），保持 trace 简洁。

## 为什么用 JSONL

每行一个独立 JSON 对象，append-only 写入。崩溃不破坏之前的记录，每行独立可解析，grep 友好。

## 一条 log_run trace 包含什么

`ts`（时间戳）、`input`、`reply`、`messages`（完整对话历史）、`elapsed_s`（耗时）、`tokens`（prompt/completion/total，usage 为 None 时字段值为 null）。

## _serialize 为什么用 hasattr 而不是 isinstance

duck typing：只要对象有 `model_dump()` 就调，不导入 SDK 内部类型，不与具体类绑死。OpenAI SDK 基于 Pydantic，所有响应对象都有 `model_dump()`。换 SDK 不用改这里。

## data/ 目录的 gitignore 策略

- `data/*.jsonl` — traces 文件
- `data/*.db` — SQLite 数据库
- `data/users/` — 每用户记忆目录（`data/*.jsonl` 只匹配顶层，子目录需单独声明）
