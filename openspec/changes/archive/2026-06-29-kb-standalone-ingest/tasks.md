## 1. standalone 配置契约 + 加载 + boot 校验

- [x] 1.1 写 integration 测试:加载 `kb-service.yaml` → 构造 KnowledgeConfigSnapshot(连接器/检索/embedding/extraction/chunking),注入 `operations` 后 `list_configured_connectors` 反映文件内容(见红),tmp_path 隔离绝不碰 data/
- [x] 1.2 实现 standalone 配置加载(yaml → snapshot,与 `as_knowledge_base_settings` 等价形状),经 B1 注入 operations;跑 1.1 见绿
- [x] 1.3 写 integration 测试:boot 校验——某连接器 credential_ref 指向的 env/file 缺失 → 启动失败指出缺项;embedding 未配 → 失败;齐全 → 成功(见红）
- [x] 1.4 实现 boot 校验（枚举 credential_ref + embedding endpoint）;跑 1.3 见绿
- [x] 1.5 提供 `kb-service.example.yaml` + `.env.example`（覆盖各段 + 鼓励 credential_ref 复用注释）

## 2. 本地凭据解析

- [x] 2.1 写 integration 测试:worker 执行连接器同步时经 credential_ref 在本地 env/file 解析凭据;两连接器共用同一 env → 都拿到（见红）
- [x] 2.2 确认/接线本地凭据解析（复用 `_read_credential_ref`），standalone 路径不经网络下发;跑 2.1 见绿

## 3. KB 本地队列 + worker + sweep

- [x] 3.1 写 integration 测试:standalone 模式 ingest job 入 **KB 本地**队列、本地 worker 抽取写 kb/，**不读写 management.db**（见红）
- [x] 3.2 把 `kb_ingest_jobs` 的队列连接来源参数化（可指向本地库，非仅 `Settings().database_url`）；standalone worker 抽本地队列；claim/done/retry/可观测逻辑复用不动；跑 3.1 见绿
- [x] 3.3 写 integration 测试:某连接器配 sync_interval、到期 → KB 服务自有调度器入本地队列（不依赖 platform cron）（见红）
- [x] 3.4 实现 KB 服务自有 sweep 调度（复用 due 判定/去重/重试，读文件连接器 + 入本地队列 + 自有定时器）；跑 3.3 见绿

## 4. platform-optional + 收尾

- [x] 4.1 写 integration 测试:无 platform、management.db 不存在的环境下，standalone KB 服务按 kb-service.yaml 完成 connector sync / ingest / 检索，进程不因缺 management.db 失败（见红→绿）
- [x] 4.2 确认 `knowledge_base` ✗→ import platform（module-boundaries 护栏）；standalone 路径不连 management.db
- [x] 4.3 跑 `make test-pr` + `make test-unit-ci`（含 76% 覆盖率关）+ `make test-integration-ci`，判"对照 main 基线无新增失败、覆盖率不破 76"（注:integration 已知并行 flaky，失败先 `-p no:randomly` 串行复核）
- [x] 4.4 ruff format/check；`openspec validate kb-standalone-ingest` 通过
- [x] 4.5 更新 `docs/capabilities/` + `docs/architecture/`:standalone KB 服务（自包含 ingest / 配置契约 / 本地 secret / platform 可选），标注平台侧退役为后续 `kb-retire-platform-ingest`（非代码产物，人工确认后再 commit）
