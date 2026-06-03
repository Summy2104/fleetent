## Why

张洋负责的能力域(agent-runtime / model-router / tools / mcp / sandbox / skill / session)在 `src/fleetent/` 下大多是**平铺单文件**(`agent_loop.py`、`tool_registry.py`、`sandbox_*.py`、`session_mgr.py` 等 30+ 个),而其它 owner 的域已成 package(`intelligence/`、`integrations/mcp/`、`governance/`、`platform/`)。`docs/architecture.md` 的目标 package map 要求「代码按能力边界组织」,且当前模块地图已把 `integrations/sandbox/` 标为目标位置(代码尚未到位 → 文档/代码不一致)。

逐包迁移前需要一份**共享蓝图**:确立目标结构、命名与迁移约定、迁移顺序,作为后续每个逐包 change 的统一契约。本 change 只确立蓝图并据此更新架构文档,**不搬任何源码**(搬迁由后续逐包 change 承接)。

## What Changes

- **确立目标 package 结构**(张洋负责部分):`runtime/`、`model/`、`tools/`、`skills/`、`session/` 各为独立能力包,`sandbox` 收进 `integrations/sandbox/`(与 `mcp`/`connectors` 同属「工具依赖的外部执行后端」)。
- **确立迁移约定**:公共 API 收口 `__init__.py`;跨包只 import 公共 API,不碰内部模块;去冗余前缀重命名(对齐 `mcp/client.py`);迁移期旧扁平路径留 re-export shim(不承载逻辑),全部迁完统一删。
- **据此更新 `docs/architecture.md`**:把目标 package map 细化到 7 个能力包,补迁移约定与命名规则。
- **枚举后续逐包迁移 change 及顺序**(blast radius 由小到大):`integrations/sandbox` → `session` → `skills` → `model` → `tools` → `runtime`(殿后)。
- **删除** `docs/superpowers/specs/2026-06-03-flat-to-package-refactor-design.md`(等价内容并入本 change,避免重复)。

## Capabilities

### New Capabilities
- `runtime-package-architecture`: 张洋负责能力域的**包组织不变量**——每个能力域是一个 package、公共 API 收口于 `__init__.py`、跨包只用公共 API、命名去冗余前缀、迁移期 shim 不承载逻辑。这些是可验证的架构约束,后续逐包迁移 change 据此实现并被审查。

### Modified Capabilities
<!-- 无:本 change 不改任何运行时能力的需求/场景;纯结构蓝图 + 文档,行为不变。 -->

## Impact

- **文档**:更新 `docs/architecture.md`(目标 package map + 当前模块地图说明);删除重复的 superpowers 设计稿。
- **代码**:本 change **不动源码**(蓝图 only)。
- **后续 change**(逐包,各自独立 PR):`restructure-sandbox-package`、`restructure-session-package`、`restructure-skills-package`、`restructure-model-package`、`restructure-tools-package`、`restructure-runtime-package`,各引用本蓝图。
- **不受影响**:运行时行为、公共契约、数据库 schema 全部不变;其它 owner 的域(intelligence / platform control plane / channels)不动。
- **分支**:基于并合回 `main`。
