## Why

模型配置当前住两处、靠 `provider_id` 字符串隐式拼接:全局 `model_providers` 表把 **Provider 与 Model 压成同一行**(一行=一个 provider+model 对),而 `agents.model_overrides` JSON 又允许内联 `base_url`/`model`/`api_key_env`。这带来三个真实问题:

- **内联陷阱**:内联的 `api_key_env` 无注册表回填 —— 只要它不精确等于某 provider 行的 `api_key_env`,key 回填必落空,agent 运行时拿到空 env 直接 fail。
- **维度错位**:同一供应商(如 OpenAI)的多个模型要重复登记多行、各填一次 key,定价/协议/最大 token 无法按"模型"独立维护。
- **UI 几乎不可用**:控制台只暴露 `routes.default` 一个 provider 下拉,其余 7 个标准 route、回退链、调用级覆盖只能手改 JSON/yaml。

把注册表升成 **providers ▸ models 两层、并让它成为唯一定义源**,能一次性解决凭证边界、模型独立维护、key 回填恒命中三件事,并为控制台重建模型路由 UI 打地基。

## What Changes

- **BREAKING(authoring 形态)**:`model_providers` 单表拆为 `providers`(凭证边界:vendor/base_url/api_key/api_key_env)+ `models`(可调用目标:provider_id FK/protocol/model_name/max_tokens/pricing/params)。Alembic 迁移按"每旧行 1:1 拆成 1 provider + 1 model",上线后运营手动合并同 vendor。
- agent route 改为**引用 `model_id`**,**堵死内联**(不再接受内联 base_url/model/api_key_env);materialize 向后兼容读旧 `provider_id`/内联形态(容错,不强制迁历史 JSON)。
- `materialize` 的 `_target_from_model_override`/`_models_from_overrides` 从"按 provider_id 取一行"改为"按 model_id 取 model 行 + join provider 行",flatten 成 `ModelTarget`(`target.api_key_env = provider.api_key_env`)→ **key 回填恒命中**。
- provider/model **CRUD 拆两套**(api_key 掩码输出、连通测试保留);新增**反查**("被哪些 agent/route 引用",扫 `agents.model_overrides`)与**删除护栏**(删被引用的 provider/model 拦截/警告)。
- **控制台路由 UI 重建**:8 个标准 route 升一等(`default` 必填显著、其余折叠"高级");选择器**按 protocol 过滤**只列协议匹配的 model;支持**回退链**(有序多 entry)与**调用级覆盖** `max_tokens`/`params`。
- **per-agent key**(per-agent 粒度,不新建表):agent 配置页选定 model 后可"用自己的 API Key 覆盖"该 provider 的共享默认,写进本 agent inject slot `secret_store(agent_id, provider.api_key_env)`;解析优先级 ① agent inject slot → ② provider 共享 key(沿用 `_seed_env` 现成逻辑)。
- **清理**:`temperature` 死列不带入新 schema(采样参数统一走 `params`);**移除** health 假端点(`router_health_probe` 恒返回 `{}` 的 `/admin/providers/health`)。

**不在本 change**:cost 视图(pricing×usage)留作后续 change;不碰 agent 绑定/集成(`agent_kbs`/`skills`/`mcp`/`im_groups`/`service_grants`/`user_agents`、`external_services`、MCP/connector UI);materialize 只动模型两函数,不动 binding/MCP/knowledge 函数。

## Capabilities

### New Capabilities
- `provider-model-registry`: providers ▸ models 两层注册表的数据模型与不变量 —— provider 是凭证边界(承载 key)、model 是 provider 下的可调用目标(承载 protocol/连接目标/定价/参数);agent 经 `agents.model_overrides` 引用 `model_id`(堵死内联,向后兼容读旧形态);materialize 经 model_id → model → provider join flatten 成 agent.yaml 的 `ModelTarget`(key 回填恒命中);路由 authoring(8 route 升一等、按 protocol 过滤选 model、回退链、调用级覆盖);per-agent key 的 (agent, provider) 粒度解析顺序。

### Modified Capabilities
- `provider-admin-api`: provider CRUD body 不再含 model/连接字段(下沉到 model);新增 model CRUD;连通测试移到 model 级;新增引用反查与删除护栏。
- `provider-admin-ui`: Providers tab 改为 provider ▸ model 两级列表 + model CRUD;移除依赖假 health 端点的健康指示。

> **不改 `agent-scoped-model-routing`**:agent.yaml 的 `models.targets/routes` 运行时契约与 `ModelTarget` 形态不变(materialize 仍产出等价结果),本 change 只改平台 authoring 源与 materialize 内部取数。
> **不改 `provider-health-probe`**:该 spec 是 agent 运行时的被动熔断缓存(真实、保留);本 change 仅移除平台侧恒返回 `{}` 的假 `/admin/providers/health` 端点(非该 spec 的需求)。
> **不改 `model-pricing-table` / `provider-management`**:pricing 仍 per-model(原 provider 行=单 model,语义等价);`provider-management` 是未落地的愿景文档,不在本 change 收口。

## Impact

- **owning package**: `platform/model_provider_management/`(`provider_admin_store.py`/`provider_admin_api.py`/`provider_connectivity.py`)+ `platform/agent_lifecycle/materialize.py` 的 `_models_from_overrides`/`_target_from_model_override` + 前端 `frontend/src/features/agents/configure.tsx` 与 `frontend/src/features/providers/`。
- **owned tables**: 新增 `providers`、`models`(管理库,Alembic);`agents.model_overrides` JSON 形态(读写两端)。`model_providers` 经迁移退役。
- **public API surface**: `/admin/providers` 拆出 provider + model 两套端点(nested 或并列待 design 定);旧端点按需 shim;移除 `/admin/providers/health`。
- **config namespace**: 无新增。
- **cross-module dependencies**: provider/model 为平台 authoring,materialize flatten 到 agent.yaml(`ModelTarget`)+ `.env`(key via `api_key_env`),**agent 运行时零感知、不读新表**(保持 agent/platform 单向解耦)。
- **migration / shim plan**: Alembic 拆表迁移(1:1 拆 + 数据回填);`model_overrides` 向后兼容读旧内联/`provider_id` 形态;`provider_admin_store.provider_key_for_env` 等共享 key 回填路径改读 `providers`。
- 权威参考:`docs/architecture/data-model.md`(model_providers、agents)、`resolver.py` `STANDARD_ROUTE_KEYS`(8 route)、`model-*` capability specs;mockup:`scratchpad/model-config-mockup.html`。
