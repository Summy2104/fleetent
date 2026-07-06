## 1. 服务骨架 + per-tenant boot 绑定

- [x] 1.1 写 integration 测试:`fleetent kb serve --tenant T` 启动后,boot 经 `tenant_scope(T)` 注入 kb_db/vector_backend(只读 tenants/T/kb/)(见红),tmp_path 隔离绝不碰 data/
- [x] 1.2 新增 `knowledge_base/serve.py`:FastAPI app + `main()`+argparse(`fleetent kb serve --tenant --host --port`,FastAPI 入口内 import);boot 绑定租户 set_database 一次;跑 1.1 见绿
- [x] 1.3 确认 `knowledge_base` ✗→ import platform(module-boundaries 护栏);FastAPI 不进 knowledge_base 顶层 import 链

## 2. wire 协议 server + 检索

- [x] 2.1 写 integration 测试:`POST /search` `{principal,query,kb_ids,limit}` → `{chunks:[...]}`,chunk 字段齐全、可被 HttpKnowledgeProvider 反序列化(见红)
- [x] 2.2 写 integration 测试:以显式 mode(默认 hybrid)+ 请求 kb_ids/limit 调 knowledge_base.search,不依赖 active_agent 决定 mode(见红)
- [x] 2.3 实现 `/search` handler:tenant_scope 注入下调 `knowledge_base.search`(显式 mode),序列化 chunks 返回;跑 2.1–2.2 见绿

## 3. 鉴权 + 租户校验

- [x] 3.1 写 integration 测试:合法 Bearer + 可解析 X-Fleetent-Principal → 受理;缺鉴权/不可解析 → 拒绝(见红)
- [x] 3.2 写 integration 测试:principal.tenant_id ≠ 服务绑定租户 → 拒绝(防串租户)(见红)
- [x] 3.3 实现鉴权(Bearer service key,env:/file:// 解析)+ `identity.decode_ingress_principal` + 租户校验;跑 3.1–3.2 见绿

## 4. 端到端 + 收尾

- [x] 4.1 写 e2e/integration:agent 经 HttpKnowledgeProvider(若 Slice ① 已落地)或等价 client → 本服务 → kb/ 端到端读到 chunks(in-process 起服务亦可)
- [x] 4.2 跑 `make test-pr` + `make test-unit-ci`(含 76% 覆盖率关)+ `make test-integration-ci`,判"对照 main 基线无新增失败、覆盖率不破 76"(注:integration 有已知并行 flaky,失败先 `-p no:randomly` 串行复核)
- [x] 4.3 ruff format/check;module-boundaries 护栏过;`openspec validate kb-read-service` 通过
- [x] 4.4 更新 `docs/capabilities/` + `docs/architecture/`:KB 读服务(wire 协议 server / per-tenant / 鉴权 / 读 kb/ / 不动 ingest);标注 ②b(ingest 搬迁)待做(非代码产物,人工确认后再 commit)
