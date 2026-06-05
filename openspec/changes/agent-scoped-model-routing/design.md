## Context

Fleetent 的配置方向已经变成“平台 DB authoring → 单 Agent home materialization →
runtime file-only”。模型配置必须跟随这个边界：部署后的 Agent runtime 不应回查平台
DB，也不应依赖全局 `routes.yaml`。

当前实现的割裂点：

- `AgentFile` 已经能承载很多 Agent-local 配置，但模型仍是浅层 `model_overrides`。
- LLM router 仍有内置 `DEFAULT_ROUTES` 与 `config/routes.yaml`。
- embedding/rerank/knowledge 仍有部分路径读取 `Settings()`。
- platform provider 管理是全局 CRUD/route，代码注释也承认 runtime consuming tables 是 follow-up。

本 change 以 Agent-local `models` 作为唯一 runtime 模型配置契约。

## Goals / Non-Goals

**Goals:**

- 用 `models.targets` / `models.routes` 统一表达 LLM、vision、embedding、rerank。
- 每个 Agent 拥有自己的 provider 凭据 env 引用，便于计费、审计和隔离。
- route 数组顺序表达 fallback，route entry 覆盖 target 默认参数。
- runtime 只读取当前 Agent snapshot。
- 平台 materialize 写出完整 `agent.yaml` 和 `.env` scaffold。
- 删除旧 `model_overrides` / `routes.yaml` 主路径。

**Non-Goals:**

- 不支持 OAuth、mTLS、workload identity 等非 API key 认证。
- 不把 `provider` 限制为内置枚举。
- 不让 runtime 依赖平台 provider catalog。
- 不保留旧配置兼容。

## Decisions

### D1 — `models.targets` 定义“能调用什么”

每个 target 是 Agent-local 的模型端点：

```yaml
models:
  targets:
    - id: primary
      provider: anthropic
      protocol: openai_chat
      base_url: https://api.anthropic.com/v1/
      model: claude-sonnet-4-5
      api_key_env: FLEETENT_MODEL_PRIMARY_API_KEY
      max_tokens: 4096
      params:
        temperature: 0.5
```

字段语义：

- `id`: Agent 内唯一。
- `provider`: 必填非空字符串；用于展示、审计、计费、平台模板；runtime 不靠它决定调用方式。
- `protocol`: 必填；MVP 支持 `openai_chat`, `http_embedding`, `http_rerank`。
- `base_url`: OpenAI-compatible chat endpoint。
- `endpoint`: embedding/rerank HTTP endpoint。
- `model`: provider 下具体模型名。
- `api_key_env`: 可选；指向当前 Agent 进程环境变量里的 API key。
- `max_tokens`: chat target 默认 token 上限。
- `params`: provider 调用参数默认值。

默认 env 命名：

```text
FLEETENT_MODEL_<TARGET_ID_UPPER>_API_KEY
```

### D2 — `models.routes` 定义“场景怎么用”

route key 代表调用场景。MVP 保留：

- `default`
- `memory_extraction`
- `vision`
- `embedding`
- `rerank`
- `image_generation`
- `audio_transcription`
- `audio_generation`

其中 image/audio 相关 route 可先保留命名，不要求第一阶段 adapter 完整实现。

route value 是数组，数组顺序表达 fallback：

```yaml
routes:
  default:
    - target: primary
    - target: backup
```

route entry 可覆盖 target：

```yaml
routes:
  memory_extraction:
    - target: fast
      max_tokens: 1024
      params:
        temperature: 0
```

合并规则：

1. 根据 route key 读取 entries。
2. 每个 entry 解析其 target。
3. target 提供 endpoint/model/auth/base params。
4. route entry 覆盖 `max_tokens` 和 `params` 同名键。
5. fallback 按 entries 顺序执行。

### D3 — `api_key_env` 是 MVP 认证契约

MVP 使用 `api_key_env`，不使用 `secret_env` / `credential_env`。这不锁定 Anthropic；
锁定厂商的是 `ANTHROPIC_API_KEY` 这种变量名。`api_key_env` 只表达认证机制。

本地无鉴权 provider 可以省略 `api_key_env`。

### D4 — runtime resolver 取代全局 route 主路径

新增 Agent-scoped model resolver：

1. 从当前 `AgentSnapshot.models` 读取配置。
2. 按 route key 返回 resolved target chain。
3. 调用 adapter 前校验该 target 所需 env。
4. 根据 `protocol` 选择 adapter。

`model/router.py` 可以被重构或替换，但 runtime 主路径不得再从 `config/routes.yaml`
或 `DEFAULT_ROUTES` 推导生产配置。

### D5 — platform provider catalog 只做 authoring 辅助

平台可以保留 provider/template/catalog，用于预填：

- provider 名称
- protocol
- base URL
- 默认参数
- 价格
- 能力标签

但部署时必须展开成 Agent-local `models.targets`。runtime 不回查平台 DB。

### D6 — materialize 管理 `.env` scaffold，不写明文 secret

平台部署时：

1. `agent.yaml` 写入 `api_key_env` 名称。
2. `.env` 写入缺失的 env key，值为空。
3. 已存在 `.env` 的 operator value 保留。
4. 明文 key 不写入 `agent.yaml`。

## Error Handling

配置加载 fail loud：

- duplicate target id 报错。
- route 引用不存在 target 报错。
- target 缺少 `provider` 或 `protocol` 报错。
- `openai_chat` 缺少 `base_url` 或 `model` 报错。
- `http_embedding` / `http_rerank` 缺少 `endpoint` 报错。
- target 声明 `api_key_env` 但调用前 env 缺失时报错。

fallback 只处理可切换错误，例如 rate limit、provider unavailable、timeout。认证错误和配置错误不应
fallback，以免掩盖部署问题。

## Observability / Billing

每次模型调用至少记录：

- agent name
- route key
- target id
- provider
- protocol
- model
- token usage 或 provider 等价用量
- latency
- error classification

计费聚合维度至少包括 agent、provider、target、route、model。

## Risks / Trade-offs

- [一次性删除旧路径影响测试较大] → MVP 未上线，避免兼容债；通过 OpenSpec tasks 明确替换范围。
- [embedding/rerank 纳入统一 schema 触碰 intelligence] → 分阶段实现 adapter 和 runtime wiring，
  但 schema 一次定准。
- [`provider` 非枚举可能出现拼写漂移] → MVP 优先自定义 provider 灵活性；平台 UI 可提供模板选择。

## Open Questions

无。以下问题已关闭：

- `provider` 必填，非枚举。
- env 字段名使用 `api_key_env`。
- env 默认命名为 `FLEETENT_MODEL_<TARGET_ID_UPPER>_API_KEY`。
- embedding/rerank 纳入统一 `models`。
- 不兼容旧 `model_overrides` / `routes.yaml`。

