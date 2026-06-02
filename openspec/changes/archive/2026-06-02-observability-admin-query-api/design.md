# 设计：observability admin query API

## 方案

在 `fleetent-admin` 下新增：

```text
fleetent-admin observability traces [...]
fleetent-admin observability usage [...]
fleetent-admin observability performance [...]
```

CLI 负责解析过滤条件、调用 observability public API、将 dataclass summary 格式化为稳定文本输出。
为了降低泄漏风险，trace 查询不打印 `payload` 原值，只打印 `payload_keys` 和事件元数据。

## 输出格式

### traces

`traces` 输出表格列：

- `TS`
- `RUN_ID`
- `EVENT_TYPE`
- `USER_ID`
- `AGENT_ID`
- `SESSION_ID`
- `PAYLOAD_KEYS`

其中 payload keys 按字母排序并用逗号连接，最多展示前 8 个 key。

### usage

`usage` 输出 summary：

- run count
- prompt / completion / total tokens
- avg elapsed
- by model 明细

### performance

`performance` 输出 summary：

- run count、completed、failed、failure rate
- avg / p50 / p95 run elapsed
- LLM / tool / fallback / permission 指标
- by model 和 by tool 明细

## 过滤条件

通用过滤：

- `--user-id`
- `--agent-id`
- `--tenant-id`
- `--session-id`
- `--from`
- `--to`
- `--limit`

trace 专用过滤：

- `--run-id`
- `--event-type`

时间字段使用 ISO 8601 字符串，通过 `datetime.fromisoformat()` 解析。解析失败时 CLI 以非零退出并输出明确错误。

## 模块边界

- owning package：`observability` owns 查询数据和聚合语义。
- public API surface：为 `TraceQuery` 增加可选 `session_id` filter；CLI 复用 public API。
- owned tables：无新增。
- config namespace：无新增。
- cross-module dependencies：`admin.py` import `fleetent.observability` public API；不 import internal store。
- migration / shim plan：无迁移，无 shim。

## 测试策略

- 在 `tests/integration/test_admin.py` 中通过 monkeypatch observability API 验证 CLI 参数解析和输出格式。
- 测试 trace 输出不包含 payload secret value。
- 测试 usage / performance 调用 public API 并展示关键指标。
- 使用 `uv run pytest tests/integration/test_admin.py -x -q` 做红绿循环。
