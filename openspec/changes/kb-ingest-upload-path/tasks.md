# kb-ingest-upload-path — Tasks

> 每个实现 task 严格 TDD：先写测试（最窄命令见红）→ 实现（同命令见绿）。测试任务在对应实现任务之前。
> 前置：kb-binding-provider-materialize 已合 main（双方都碰 `kb_serve_client.py`）；未合则 apply 前确认并 pull。

## 1. serve 上传端点

- [ ] 1.1 测试：`service_config` 的 `service.max_upload_bytes` 可配置、缺省 50MB（unit，先红）
- [ ] 1.2 实现：`KBServiceSection` 增加 `max_upload_bytes` 字段与默认值；见绿
- [ ] 1.3 测试：`POST /kb/{kb_id}/documents` 的鉴权与校验分支——无/错 Bearer 401、principal 租户不符 403、kb_id 不存在 404、超限 413（integration，serve TestClient + tmp_path 数据目录，先红）
- [ ] 1.4 实现：serve 增加上传路由骨架（鉴权复用 `_require_authorized_principal`、KB 存在性校验、大小限制流式检查）；见绿
- [ ] 1.5 测试：合法上传 → 文件落 `tenants/<t>/kb/uploads/<kb_id>/` 且暂存名为 uuid 前缀 + 净化原名（含 `../` 穿越用例断言不逃逸）、`kb_ingest_jobs` 队列出现 `sync_directory` job（`connector_ref.path` 指向暂存文件）、响应含 job id（integration，先红）
- [ ] 1.6 实现：流式暂存 + 文件名净化 + `enqueue_job` 入队 + 响应体；见绿
- [ ] 1.7 测试：端到端消费——上传后跑 worker 单轮消费，文档出现在 `GET /kb/{kb_id}/documents` 且 `/search` 可命中（integration，复用既有 worker 测试夹具与 deterministic embedding，先红）
- [ ] 1.8 实现/修缝：打通 1.7 暴露的缝隙（如有）；见绿

## 2. platform 代理路由

- [ ] 2.1 测试：`KBServeClient.upload_document` 以 multipart 透传（mock transport 断言路径/头/载荷），serve 端 404/413 原样抛给调用方（unit，先红）
- [ ] 2.2 实现：`KBServeClient` 增加 upload 方法；见绿
- [ ] 2.3 测试：`POST /admin/kb/{kb_id}/documents`——admin 成功透传并写 `doc_upload` 审计（含 kb_id 与原始文件名）、viewer 403、serve 端错误码透传且不写审计（integration，mock KBServeClient，先红）
- [ ] 2.4 实现：admin API 增加上传代理路由 + 审计；见绿

## 3. 收尾

- [ ] 3.1 更新 `kb-service.yaml.example` 注释（`max_upload_bytes` 可选项）与 `docs/capabilities/knowledge-base.md` 的上传通路说明；人工确认后提交
- [ ] 3.2 change/PR 收尾：`make test-pr` + `make test-integration-ci` 全绿（对照 main 基线无新增失败）
