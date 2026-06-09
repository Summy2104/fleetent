## Context

目标架构（`docs/architecture/target-architecture-proposal.md`）定义了「核 + 4面 + 基座」的依赖铁律：核 ✗→ 面、面 ✗→ 面（直接）、任意 → 基座合法。现有 `test_module_dependency_guardrails.py` 覆盖 intelligence-layer dissolution 场景，定义的是组件层级的规则（`_COMPONENTS ✗→ fleetent.platform`），但没有面间隔离规则，也没有明确哪些模块属于核、哪些属于面。

三个具体的代码结构问题：

1. **`governance/audit_log.py` 错位**：audit_log 是平台管理操作的审计基础设施（"谁在几点改了什么"），被 14 个 `platform/*` 模块以及 `tools/builtin_tools` 共同依赖——这是基座基础设施的特征。但它目前住在 `governance/` 组件包里，与执行门（permission_gate、quota 等）混杂。这不造成直接 import 错误（platform 可以 import governance），但概念归属不对，且使 governance 包语义不纯（执行门 ≠ 审计日志）。

2. **reflection 两拆缺收口护栏**：`reflection/`（引擎）和 `platform/reflection_management/`（管理 API）已经物理分离，但没有 CI 规则强制这两个方向的边界——`reflection/` 不 import `platform/reflection_management/` 内部（现在如此，不代表将来不会发生），`platform/reflection_management/` 不 import `reflection/` 引擎私有 API（只通过公开 store 接口访问产物）。

3. **knowledge_base 边界停在目录层**：`retrieval ✗→ ingest` 已是硬 CI gate，但 `retrieval/` 函数签名接受具体 `KnowledgeStore` 实例，而非协议类型。这意味着在类型系统里 retrieval 仍然可见写方法（`upsert`/`delete` 等），只是没有调用——类型层的边界没有落地，`knowledge-base-boundaries` spec 已要求的 Protocol 接口尚未实现。

## Goals / Non-Goals

**Goals:**

- 建立 CI 强制的面间隔离规则（面 ✗→ 面、核 ✗→ 面）作为架构护栏
- 将 `governance/audit_log.py` 移至基座层（顶层 `src/fleetent/audit_log.py`）
- 为 reflection 两拆补充收口护栏（两个方向）
- 落地 `KnowledgeReadable` / `KnowledgeWritable` Protocol，使 retrieval 在类型层只见读接口

**Non-Goals:**

- `user_store` 三拆 / Identity 端口（依赖 DB roadmap #4，本 change 不做）
- 巨型文件拆分（`loop.py`/`reflection.py`，正交，单独 change）
- `platform/` 内部按①②③④重新命名目录（纯重组，后续可做）
- 修复 `user_store` 导致的传递性 platform 泄漏（已在现有护栏 allowlist 中 pin，本 change 不触碰）

## Decisions

### D1：面间护栏用「模块前缀集合」方式定义，加入现有 `test_module_dependency_guardrails.py`

面（plane）模块统一在 `fleetent.platform.*` 和 `fleetent.im_gateway.*` 下（其他面子模块也住在这两个命名空间）。核（core）模块集合 = `{runtime, session, model, tools, integrations, governance, memory, long_term_ctx, reflection, skills, knowledge_base.retrieval}`。

新增两条规则：
- **核 ✗→ 面**（精化）：核模块集合中任一模块 MUST NOT import `fleetent.platform.*`——已覆盖但通过明确列出「核模块」集合提高可读性与意图清晰度
- **面 ✗→ 面**（新增）：`fleetent.platform.*` 中属于不同面（①②③④）的子包 MUST NOT 互相直接 import

对于面间隔离，使用已有的面划分（见架构提案 §9）：
- ①边缘：`im_gateway` + `server`（`/chat /ws`）
- ②控制：`platform/{agent_management_console, connector_management, knowledge_base_management, model_provider_management, skill_management, user_management, chat_management, askit_console, reflection_management}`
- ③编排：`platform/agent_lifecycle`
- ④摄取：`knowledge_base.ingest` + `platform`（connector sync）

> 取舍：面内部（如 ② 的各子包互相 import）暂不强制隔离——先立面间边界，后续再视需要立面内边界。

### D2：`audit_log.py` 迁移路径——顶层基座，保留 shim 一个 sprint

移至 `src/fleetent/audit_log.py`（与 `structured_logging.py` 并列，都是基座基础设施）。在原路径 `src/fleetent/governance/audit_log.py` 保留 re-export shim（`from fleetent.audit_log import *`），移除 shim 作为后续清理任务（非本 change 范围）。14 个 caller 在本 change 内全部更新到新路径。

> 取舍：shim 牺牲一点洁净度换取低风险——调用方在本 change 内全更新，shim 是双重保险；不用 shim 的话需要保证更新无遗漏，对 14 个文件来说风险稍高。

### D3：reflection 收口护栏——在现有 test 文件里新增两条断言

- `fleetent.reflection.*` MUST NOT import `fleetent.platform.reflection_management.*`
- `fleetent.platform.reflection_management.*` MUST NOT import `fleetent.reflection.reflection`（直接 import 引擎私有 API）；只允许通过 `fleetent.reflection.store` 访问产物

### D4：KnowledgeReadable / KnowledgeWritable Protocol 定义在 `knowledge_base/core/protocols.py`

`retrieval/` 函数签名改为接受 `KnowledgeReadable`；`ingest/` 和 `management/` 接受 `KnowledgeWritable`。`core/store.py` 的 `KnowledgeStore` 同时实现两个 Protocol（structural subtyping，不需继承）。

不在本 change 内做运行时 isinstance 检查——纯类型层约束，mypy strict 已开启。

## Risks / Trade-offs

- **audit_log 移动的 import 影响范围**：14 个文件，grep 可穷举，风险可控。shim 提供双重保险。
- **面间隔离规则的完整性**：platform/ 内子包间的交叉 import 可能比预想的多；先跑测试看红，再逐条处理，不先假设零违规。
- **KnowledgeReadable Protocol 签名收窄**：retrieval 函数目前接受 KnowledgeStore，如果有 caller 传入了写操作后又用同实例调 retrieval，改 Protocol 后 mypy 仍通过（因为 KnowledgeStore 实现了两者）；类型层边界是声明意图，不是运行时拦截。
