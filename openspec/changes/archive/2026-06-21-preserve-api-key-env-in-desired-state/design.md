## Context

`desired_state_payload_from_agent_file` → `_strip_secret_plumbing` 递归清洗 AgentFile 的 JSON,移除"密钥相关"键后下发给 node。当前判据是:

```python
if key == "env" or key.endswith("_env") or key.endswith("credential_ref"):
    continue  # drop
```

`key.endswith("_env")` 的本意大概是连同密钥一起把 env 相关都剥掉,但 `api_key_env` 的**值是一个 env 变量名**(如 `ANTHROPIC_API_KEY`),不是密钥本身——它是运行时 resolver 用来去 `.env` 找 key 的**指针**。把它剥掉后,node 写出的 `agent.yaml` 没有这个指针,`resolver.require_api_key` 见 `api_key_env` 为空就返回 `None`,模型调用无凭证 → 401。密钥的真正值从来不在 agent.yaml 里(model target 只有 `api_key_env` 指针),而是由 `_seed_env` 写进 `.env`。

## Goals / Non-Goals

**Goals:**
- 让下发的非密载荷保留 `*_env` 指针字段名,使 node 写出的 `agent.yaml` 携带 `api_key_env`,托管 agent 的模型调用恢复正常。
- 维持"desired-state 不含明文密钥"的主权契约不变。

**Non-Goals:**
- 不改密钥值的传输/落地路径(`_seed_env` / secret-injection 不动)。
- 不做 B2(`FLEETENT_TUI_TOKEN`)、不做 B3(node 端口 / gateway)——属后续 change。
- 不碰 agent 运行时、`server.py`、schema。

## Decisions

**D1 · 只删 `key.endswith("_env")` 这一分支,保留另外两条。**
`*_env` 字段按约定是**变量名指针(非密)**;真正的密钥值落在 `env` 字典(`key == "env"`,如 mcp 的内联 env)或经 `credential_ref` 间接引用。故安全的剥离判据是:

```python
if key == "env" or key.endswith("credential_ref"):
    continue
```

这样 `api_key_env`(以及 mcp target 的 `api_key_env` 等)作为非密指针被保留,而承载密钥值的 `env` 字典与 `credential_ref` 仍被剥。备选「显式白名单只保留 `api_key_env`」——否决:`*_env` 全是非密变量名,按类别保留比逐字段白名单更稳、也不会漏掉 mcp 等其它 `*_env` 指针。

**D2 · 不让任何 secret 值借此进入 desired-state。**
被保留的只是变量名字符串(如 `"ANTHROPIC_API_KEY"`),不是值。密钥值仍只走 `_seed_env`(inject slot / provider inline key / shared secret)落 node 的 `.env`,desired-state 仍不含明文密钥——契约不变。测试要正向断言这点(带密钥的 `env` 字典仍被剥)。

## Risks / Trade-offs

- **[误以为这会把密钥泄进 desired-state]** → 不会:保留的是 `*_env` 变量名,不是值;新增测试明确断言「`env` 字典/`credential_ref` 仍被剥、desired-state 不含密钥值」守住契约。
- **[是否有 `*_env` 字段其实承载密钥]** → 按现有 schema,`*_env` 一律是变量名(model target `api_key_env`、mcp `api_key_env`),密钥值在 `env` 字典或 provider 表。Review 时对照 AgentFile/McpServerSettings 字段确认无反例。
- **[node 侧 `.env` 是否真有该 key 的值]** → 那是 secret-injection / `_seed_env` 的职责(本 change 不动);集成测试用 provider inline key 这条已存在的 seed 路径验证「agent.yaml 有指针 + `.env` 有值」闭合。若独立的 node-secret-injection 另有缺口,属后续单独排查,不在本 change。

## Migration Plan

- 纯代码修复,无 schema/迁移、无数据变更。合并即生效:此后 materialize/重新 materialize 产出的下发载荷与 `agent.yaml` 即带 `api_key_env`。已部署的旧 agent 在下次 materialize / desired-state 拉取后自动获得修复。回滚 = `git revert`。
