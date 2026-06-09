## 1. audit_log 归基座

- [x] 1.1 Write failing test: `fleetent.audit_log` 可经顶层路径导入且不依赖业务模块或 platform
- [x] 1.2 将 `src/fleetent/governance/audit_log.py` 移至 `src/fleetent/audit_log.py`
- [x] 1.3 在原路径 `src/fleetent/governance/audit_log.py` 保留 re-export shim
- [x] 1.4 更新全仓 14 个 caller（`platform/*` + `tools/builtin_tools`）的 import 到 `fleetent.audit_log`
- [x] 1.5 运行测试确认绿（单元 + 依赖护栏）

## 2. reflection 两拆收口护栏

- [x] 2.1 Write failing tests: `reflection.* ✗→ platform.reflection_management.*`；`platform.reflection_management.* ✗→ reflection.reflection`（两条分别）
- [x] 2.2 检查现有代码是否已符合（grep 确认），若有违反则修复
- [x] 2.3 运行测试确认绿

## 3. 面间隔离护栏

- [x] 3.1 Write failing tests: 核集合 ✗→ im_gateway 规则；面①②③④互不直接 import 规则
- [x] 3.2 跑测试看红——列出所有当前违反（预期：可能有面间 import）
- [x] 3.3 逐一修复违反（按 design.md D1：先立规则，违反者当场修）
- [x] 3.4 运行完整 `make test-pr` 确认无新增失败

## 4. KnowledgeReadable / KnowledgeWritable Protocol

- [ ] 4.1 Write failing test: `retrieval/` 函数签名接受 `KnowledgeReadable`；mypy strict 下写方法不可见
- [ ] 4.2 在 `knowledge_base/core/protocols.py` 定义 `KnowledgeReadable` 和 `KnowledgeWritable` Protocol
- [ ] 4.3 更新 `knowledge_base/core/store.py` 的 `KnowledgeStore`（无需继承，structural typing 自动满足）
- [ ] 4.4 更新 `knowledge_base/retrieval/` 中接受 store 的函数签名为 `KnowledgeReadable`
- [ ] 4.5 运行 `uv run mypy src` 确认类型检查通过；运行测试确认绿
