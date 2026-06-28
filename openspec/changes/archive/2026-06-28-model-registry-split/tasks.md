# Tasks — model-registry-split

> 规则:每个实现 task 的测试 task 在其之前(TDD hard gate)。test 见红 → impl 见绿。
> 层边界:DB/schema/CRUD/materialize 协作 → integration;纯解析/序列化 → unit。

## 1. Schema 与迁移(Alembic 管理库,head 106 → 107)

- [x] 1.1 (integration test) 写迁移测试:升级后存在 `providers`、`models` 表,列与 design D1 一致(providers: id/vendor/api_key/api_key_env/base_url/description/时间戳;models: id/provider_id FK/protocol/model_name/base_url/endpoint/max_tokens/input_price_per_1k/output_price_per_1k/params/extra_params/description/时间戳);`models` 无任何 api_key 列;`temperature` 不存在于任一新表
- [x] 1.2 (integration test) 写数据回填测试:预置若干 `model_providers` 旧行 → 升级后每行 1:1 拆为 1 provider + 1 model,**model.id == 旧行 id**,provider.id 派生(vendor 优先,无则 `<旧id>__provider`),api_key/api_key_env 落 provider,连接字段/定价/params 落 model
- [x] 1.3 (integration test) 写 downgrade 测试:降级把 provider+model 逆向合并回 `model_providers`(1:1 可逆)
- [x] 1.4 实现 Alembic 迁移 107:建两表 + 外键 + 1:1 回填 + drop `model_providers`;实现 downgrade 逆向回填
- [x] 1.5 更新 `docs/architecture/data-model.md`:model_providers 退役,新增 providers/models 两表条目(人工确认后提交)

## 2. Store 层(provider_store / model_store)

- [x] 2.1 (integration test) 写 `provider_admin_store` 测试:provider CRUD(api_key 原样存、掩码在 API 层)、`provider_key_for_env` 改读 `providers`、provider body 不含 model/连接字段
- [x] 2.2 实现 `provider_admin_store` 切到 `providers` 表(named params,无 ORM);`provider_key_for_env` 改读 providers
- [x] 2.3 (integration test) 写 `model_admin_store` 测试:model CRUD、按 provider_id 列出、按 protocol 过滤列出、删除前的引用判定钩子(store 只读不判，判定在 service/api)
- [x] 2.4 实现 `model_admin_store`(新模块):model CRUD + 按 provider/protocol 查询

## 3. Materialize join 与向后兼容

- [x] 3.1 (unit test) 写 `_target_from_model_override` 测试:命中 model_id → join provider → ModelTarget(api_key_env=provider.api_key_env、连接取 model、max_tokens/params 深合并);用 monkeypatch 注入假 model/provider store(不碰真实 DB)
- [x] 3.2 (unit test) 写向后兼容测试:旧 `provider_id`/内联形态未命中注册表 → 回落旧内联逻辑 + 记 warn,不报错
- [x] 3.3 (unit test) 写 `_models_from_overrides` 测试:routes 多 entry 有序回退链、调用级覆盖透传、route entry 形态 `{model_id, max_tokens?, params?}`
- [x] 3.4 实现 `_target_from_model_override`/`_models_from_overrides`:model_id 优先解析 + provider join + 旧形态兜底(只动这两个函数,不碰 binding/MCP/knowledge)
- [x] 3.5 (integration test) 写 per-agent key 解析测试:`.env` 中 `provider.api_key_env` 取值优先级 ① agent inject slot → ② provider 共享 api_key → ③ 共享 secret(经 `_seed_env`)
- [x] 3.6 实现/校准 `_seed_env` 路径使其按新 provider 表回填(若现有逻辑已满足,仅补测试与 `provider_key_for_env` 接线)

## 4. API 层(/admin/providers + /admin/models)

- [x] 4.1 (integration test) 写 provider API 测试:list 显示 vendor/base_url/model 数/掩码 key、无 model 字段;CRUD body 拒绝 model/temperature 等 per-model 字段;edit 留空 key 不变;role-gate(viewer 只读、未登录 401);删仍挂 model 的 provider → 409
- [x] 4.2 实现 provider API 改造:body 去掉 model/max_tokens/temperature/extra_params;list 加 model 数;**移除 `/admin/providers/health` 假端点**;删 provider 的 has-models 护栏
- [x] 4.3 (integration test) 写 model API 测试:model CRUD、protocol 决定必填连接字段(chat→base_url、embedding/rerank/image→endpoint)、model 无 api_key 字段、删被引用 model → 409、role-gate
- [x] 4.4 实现 model API(`/admin/models` 新 router):CRUD + provider_id 校验 + protocol 必填字段校验
- [x] 4.5 (integration test) 写连通测试迁移测试:`POST /admin/models/{id}/connectivity-test` 用 model 连接 + provider key,不记 usage;旧 provider 级连通端点移除/改向
- [x] 4.6 实现 model 级 connectivity-test(复用 `provider_connectivity`,组装 model+provider)
- [x] 4.7 (integration test) 写引用反查测试:`GET /admin/models/{id}/references`、`GET /admin/providers/{id}/references`(provider=其下 model 引用并集),扫 `agents.model_overrides` 含旧形态识别
- [x] 4.8 实现引用反查端点 + 删除护栏接线(model 被引用 409、provider has-models 409)

## 5. 前端(providers/models 注册表 + agent 路由 UI)

- [x] 5.1 (frontend test) 写 Providers tab 测试:provider ▸ model 两级列表、model CRUD 控件、连通测试落 model、无 health 指示/无 health 端点调用、viewer 隐藏写控件
- [x] 5.2 实现 `frontend/src/features/providers/` 改造:两级列表 + model CRUD + 连通测试调 model 端点 + 删除冲突提示引用方;移除 health 指示
- [x] 5.3 (frontend test) 写 agent 路由 UI 测试:8 route(default 必填显著、其余折叠)、每 route 选择器按 protocol 过滤、回退链多 entry、调用级覆盖、写回 `{model_id,...}`
- [x] 5.4 实现 `configure.tsx` 模型段重建:route 升一等 + protocol 过滤选择器 + 回退链 + 调用级覆盖 + 引用 model_id
- [x] 5.5 (frontend test) 写 per-agent key UI 测试:选定 model 后可覆盖该 provider key、留空回落共享、reload 掩码显示
- [x] 5.6 实现 per-agent key 输入(经现有 per-agent secret 端点写 `(agent_id, provider.api_key_env)`)

## 6. 收尾:迁移执行、E 清理、回归

- [x] 6.1 迁移落地后执行 `rematerialize_all()` 刷新全量 agent.yaml,验证无空 env(integration 烟测)
- [x] 6.2 (test) 确认 `temperature` 死列清理:provider/model body、store、connectivity 不再依赖 temperature(采样参数统一走 params)
- [x] 6.3 `make test-pr` + `make test-integration-ci` 全绿(无新增失败);改动文件 ruff/mypy 通过
- [x] 6.4 更新运营文档:同 vendor 多 provider 的手动合并 SOP(人工确认后提交)
