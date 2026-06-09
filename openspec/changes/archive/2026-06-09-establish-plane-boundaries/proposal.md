## Why

现有依赖护栏（`test_module_dependency_guardrails.py`）覆盖的是 intelligence-layer dissolution 规则，不包含核+4面架构的面间隔离规则；`governance/audit_log.py` 混在执行组件里而非基座；reflection 两拆虽已成形但缺少收口护栏；`knowledge_base` 目录分离已完成，但读写边界停在运行时检查层面，尚无类型层 Protocol 约束。这些缺口导致面边界是「说好的」而非「强制的」，任何 import 都能悄悄越界。

## What Changes

- **新增面间隔离 CI 护栏**：定义核模块集合与四个面集合，CI 强制断言「面 ✗→ 面」（面模块不互相直接 import）和「核 ✗→ 面」（核模块不 import 面模块）两条新规则
- **`governance/audit_log.py` 归基座**：从 `governance/` 移出，以顶层 `audit_log.py` 形式作为基座基础设施存在；更新全仓 import 路径
- **reflection 两拆收口**：为 `reflection/ ✗→ platform/reflection_management/`、`platform/reflection_management/ ✗→ reflection/` 内部（engine）两个方向分别补充护栏；确认现有代码符合方向
- **knowledge_base Protocol 接口落地**：在 `knowledge_base/core/` 引入 `KnowledgeReadable` / `KnowledgeWritable` Protocol，`retrieval/` 函数签名改为只接受 `KnowledgeReadable`，从「目录级隔离」升级为「类型层边界」

不做：`user_store` 三拆 / Identity 端口（需与 DB roadmap #4 协调）；巨型文件拆分（正交，待单独 change）。

## Capabilities

### New Capabilities

- `plane-boundary-guardrails`: CI 强制的核+4面架构依赖规则——面间隔离 + 核✗→面；扩展现有 `test_module_dependency_guardrails.py` 或作为新测试文件

### Modified Capabilities

- `knowledge-base-boundaries`: 新增 KnowledgeReadable / KnowledgeWritable Protocol 类型层约束（现有 spec 已要求，本 change 落地实现）

## Impact

- **测试**：`tests/unit/test_module_dependency_guardrails.py` 扩展新规则；新增面间隔离断言
- **代码**：`governance/audit_log.py` → `src/fleetent/audit_log.py`；全仓 import 路径更新（grep `fleetent.governance.audit_log`）；`knowledge_base/core/` 新增 Protocol 定义；`knowledge_base/retrieval/` 函数签名收窄
- **无 API 变更**：所有改动在模块内部边界，不暴露新 HTTP 端点
