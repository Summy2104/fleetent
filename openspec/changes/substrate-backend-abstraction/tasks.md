## 1. 后端抽象 + 工厂(镜像 sandbox backend)

- [ ] 1.1 [测试] `tests/unit/test_substrate_backend.py`(纯逻辑,无真实 DB file):工厂按 URL scheme 选后端(sqlite/本地路径 → 本地后端);capabilities 标志可读;未知 scheme 报错 → 红
- [ ] 1.2 [实现] 新增后端抽象:`BaseSubstrateBackend`(或 Protocol)+ `SubstrateCapabilities` + `factory.create_substrate(database_url)`(按 scheme 分派),镜像 `integrations/sandbox` 的 `backend.py`/`factory.py`
- [ ] 1.3 [验证] `uv run pytest tests/unit/test_substrate_backend.py -x -q` → 绿

## 2. 本地 SQLite 后端 = 现状收编(零行为变化)

- [ ] 2.1 [测试] integration:经工厂以本地 URL 开库,迁移(migrate-on-open + user_version)与 PRAGMA 行为与改造前一致 → 红/回归
- [ ] 2.2 [实现] 把现有 `SQLiteDatabase` + 嵌入式迁移收编为 `SQLiteSubstrateBackend`;`db.py` 的 `create_database` 升级为按 scheme 分派,SQLite 默认
- [ ] 2.3 [验证] 现有 DB 相关 integration 测试原样通过(回归基线)

## 3. agent 侧三关系库改走工厂

- [ ] 3.1 [实现] per-agent 运行库(`runtime/agent_state...`)开库点改走 `factory.create_substrate`
- [ ] 3.2 [实现] 共享记忆库(`memory/shared...`)开库点改走工厂
- [ ] 3.3 [实现] KB 关系库(`knowledge_base/core...`)开库点改走工厂
- [ ] 3.4 [验证] 每库改完跑其相关 integration（《相关集成测试命令》:test_kb_*、test_*memory*、agent_state 相关）无新增失败;**不直接构造 SQLiteDatabase 的开库点已收敛**(git grep 核查)

## 4. 边界 + 收尾

- [ ] 4.1 [验证] `test_module_dependency_guardrails` 绿:底座抽象未引入 store→platform 反向 import
- [ ] 4.2 [验证] `git grep -n "sqlite3.connect\|SQLiteDatabase(" -- src/fleetent`(除后端实现内部)无新增裸开库
- [ ] 4.3 [验证] `make test-pr` 全绿;《相关集成测试命令》(本 change 触碰的 DB/store 层 integration)无新增失败;**跨切面提示:本 change 改 db.py 开库边界,属"存储边界层"——收尾跑全量 integration 一次对照 main 基线**
- [ ] 4.4 [验证] `make test-unit-ci` 覆盖率 ≥ 76%
- [ ] 4.5 [验证] `openspec validate substrate-backend-abstraction`;archive 后 `opsx:verify`

> 注:本 change 是**存储边界层改动(跨切面)**,4.3 收尾按 skill 规则跑**全量 integration**(不走 scoped),因为可能波及任何用 DB 的 integration 测试。
