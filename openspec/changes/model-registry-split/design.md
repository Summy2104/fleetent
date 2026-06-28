## Context

当前 `model_providers` 单表把 Provider 与 Model 压成一行(一行 = 一个 provider+model 对,自带 base_url/model/api_key/protocol/pricing)。agent 经 `agents.model_overrides` JSON 按 `provider_id` 字符串引用,并可内联 `base_url`/`model`/`api_key_env`。materialize(`platform/agent_lifecycle/materialize.py`)把这两处 join 后 flatten 成 agent.yaml 的 `models.targets/routes`(`ModelTarget`),key 经 `.env` 的 `api_key_env` 间接寻址,运行时 `resolver.py` 读取。

约束:
- **agent/platform 单向解耦**:agent 运行时只读 agent.yaml + .env,不得读管理库表。新表是平台 authoring,必须经 materialize 拍平后才到 agent 侧。
- **secret 永不内联下发**:key 经 `api_key_env` 间接;值由 `secret_store` 按 `agent_id`(per-agent inject slot)或 `None`(共享)持有,materialize `_seed_env` 负责写 `.env`。
- 管理表归 **Alembic**(当前 head 106);store 层手写 SQL + named params,无 ORM。

## Goals / Non-Goals

**Goals:**
- providers ▸ models 两层结构化:provider = 凭证边界(承载 key),model = provider 下可调用目标(承载 protocol/连接目标/定价/参数)。
- 注册表成模型定义唯一源:agent route 只引用 `model_id`,堵死内联,key 回填恒命中。
- 控制台模型路由 UI 可用:8 route 升一等、按 protocol 过滤、回退链、调用级覆盖、per-agent key 入口。
- 迁移无损且**不需重写历史 `model_overrides` JSON**。

**Non-Goals:**
- cost 视图(pricing×usage)——后续 change。
- agent 绑定/集成(kbs/skills/mcp/im_groups/service_grants/user_agents、external_services、MCP/connector UI)。
- 跨租户/per-tenant key(本 change 只做 per-agent + provider 共享默认)。
- materialize 的 binding/MCP/knowledge 函数。

## Decisions

### D1. 连接目标(base_url/endpoint)落在 model,provider 只承载身份+凭证

- `providers`: `id, vendor, api_key, api_key_env, base_url(可选,仅 UI 预填默认), description, created_at, updated_at`
- `models`: `id, provider_id(FK), protocol, model_name, base_url, endpoint, max_tokens, input_price_per_1k, output_price_per_1k, params, extra_params, description, created_at, updated_at`

**为什么**:OpenAI 这类一家多能力的供应商,chat 用 `base_url`、embedding/rerank/image 用 `endpoint`,路径随能力变 —— 连接目标天然是 model(能力)级。把它放 model 上,runtime flatten 不需要做"provider host + model path"的继承解析,迁移也能严格 1:1(旧行的 base_url/endpoint 原样落 model)。provider.base_url 仅作新建 model 时的 UI 预填,**不参与运行时 join**。
**备选**:provider 持 host、model 持 path + 继承解析 —— 增加运行时继承复杂度且对自托管异构(不同 host)不成立,否决。

### D2. 迁移用 `model.id = 旧 model_providers.id`,保历史引用零改写

每条旧 `model_providers` 行 1:1 拆:
- 新 `models` 行 **id = 旧行 id**(原样保留)→ 所有现存 `model_overrides` 里 `provider_id: <旧id>` 的引用,**直接当 `model_id` 命中**,无需改写 JSON。
- 新 `providers` 行 id = 派生(优先 `vendor`,无则 `<旧id>__provider`);`model.provider_id` 指向它;`api_key`/`api_key_env` 从旧行搬到 provider。
- `temperature` 列不带入(决策 E)。

**为什么**:迁移最大风险是历史 agent 引用悬空。让 model 继承旧 id,引用语义平滑过渡;运营上线后再手动把同 vendor 的多个 provider 合并(改 model.provider_id、删冗余 provider)。
**备选**:provider 继承旧 id、model 派生新 id —— 会让所有历史引用失效,需扫库改写 JSON,风险高,否决。

### D3. materialize flatten 改 model_id 优先、向后兼容内联

`_models_from_overrides`/`_target_from_model_override` 新解析顺序,每个 route entry:
1. 取 `model_id`(规范)或回落旧键 `provider_id`/`target`/`provider`;
2. `model_store.get(id)` 命中 → join `provider_store.get(model.provider_id)` → 构造 `ModelTarget`:
   `id=model.id, provider=provider.vendor, protocol=model.protocol, base_url=model.base_url, endpoint=model.endpoint, model=model.model_name, api_key_env=provider.api_key_env, max_tokens=entry.max_tokens or model.max_tokens, params=deep_merge(model.params, entry.params)`;
3. 未命中 → **保留旧内联兜底逻辑**(读 entry 内联字段),仅记 warn,确保旧形态不炸。

`require_api_key` 永远拿到 `provider.api_key_env` → 与 provider 同源 → 回填恒命中。

### D4. API:provider 与 model 拆为并列资源(flat),连通测试落 model

- `/admin/providers` CRUD(api_key 掩码输出不变);移除 `/admin/providers/health`(决策 D)。
- `/admin/models` CRUD(`provider_id` 为 body 字段;protocol 必填);**连通测试移到 `/admin/models/{id}/connectivity-test`**(它才是含 base_url+model+key 的可调用单元);provider 级可选保留"凭证可达性"轻探活(非必须,design 内不强求)。
- 反查:`/admin/models/{id}/references`、`/admin/providers/{id}/references`(provider 级 = 其下所有 model 引用并集),扫 `agents.model_overrides`。
- 删除护栏:删被引用 model → 409;删仍挂 model 的 provider → 409(先删/迁移其 model)。

**为什么 flat 而非 nested**:model 自带 `provider_id`,flat 更利于"按 protocol 列全部 model"(路由选择器)与全局反查;nested 反而要多一跳。

### D5. per-agent key:复用 secret_store inject slot,不新建表

agent 配置页选定某 model 后,展示"覆盖该 provider 的 API Key"输入,目标 env 名 = `provider.api_key_env`,值经现有 `credential_slots`/`secret_store` 以 `(agent_id, env_name)` 写入(inject 模式)。materialize `_seed_env` 现成优先级不变:① `secret_store(agent_id, env)` → ② provider 共享 key(`provider_key_for_env` 改读 `providers`)→ ③ 共享 secret。粒度 = **(agent, provider)**:同 provider 的多个 model 共用这把覆盖 key。

**为什么不开 `agent_provider_credentials`**:secret_store 已按 agent_id 隔离/加密且不破坏解耦契约;新表会撞成第二个真相源。日后若需"哪些 agent 给 provider X 配了私钥"审计页再加。

### D6. 路由 UI:model 选择器按 protocol 过滤

`configure.tsx` 每个 route 的选择器只列 `protocol` 与该 route 期望协议匹配的 model(default/memory_extraction → openai_chat;embedding → http_embedding;rerank → http_rerank;image_generation → openai_image_generation;vision → openai_chat)。route entry 写回 `{model_id, max_tokens?, params?}`;回退链 = 同 route 多 entry 有序数组。`default` 必填显著,其余 7 route 折叠"高级"(audio_* 无内置 protocol,先隐藏)。

## Risks / Trade-offs

- **迁移数据保真** → 1:1 拆 + `model.id` 继承旧 id 使引用零改写;迁移后跑 `rematerialize_all()` 让所有 agent.yaml 重新 flatten 一次,验证无空 env。
- **过渡期双形态并存**(新 model_id 写法 vs 旧内联) → materialize D3 兜底读旧形态 + warn;护栏测试覆盖两条路径。
- **provider 合并是手动步骤** → 上线即可用(1:1 仍正确),合并是优化非必须;文档写清运营 SOP。
- **protocol 过滤误配兜底** → 即使 UI 过滤,后端 model CRUD 仍校验 protocol 合法值;materialize 对 protocol 与 route 不匹配只记 warn 不阻断(由 resolver 既有校验处理)。
- **删除护栏的反查成本** → 扫 `model_overrides` 是单管理库表全表遍历,agent 量级小,可接受;必要时加索引/缓存(本 change 不做)。

## Migration Plan

1. Alembic 迁移(head 106 → 107):建 `providers`、`models`;按 D2 回填(每旧 `model_providers` 行 → 1 provider + 1 model,model.id 继承);保留 `model_providers` 暂不 drop(回滚兜底),或同迁移 drop + downgrade 重建回填(二选一,倾向**同迁移 drop**,downgrade 逆向 1:1 合并)。
2. store/api 切到新表;`provider_key_for_env` 改读 `providers`。
3. materialize 切 D3 flatten。
4. 迁移后执行 `rematerialize_all()` 刷新全量 agent.yaml。
5. 前端切新端点 + 路由 UI。
- **回滚**:Alembic downgrade 逆向把 provider+model 合并回 `model_providers`(1:1 可逆);agent.yaml 经 rematerialize 复原。

## Open Questions

- `model_providers` 是同迁移 drop 还是保留一版做灰度?(倾向同迁移 drop,downgrade 可逆)
- provider 级是否保留一个"凭证可达性"轻探活端点,还是连通测试完全只在 model 级?(倾向仅 model 级,provider 级先不做)
