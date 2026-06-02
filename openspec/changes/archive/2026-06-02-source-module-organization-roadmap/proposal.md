## Why

`src/fleetent` 当前处于“部分模块化 + 大量 legacy 平铺模块”状态。`intelligence`、`observability`
和 `im_gateway` 已经有目录边界，但 `agent_loop.py`、`admin.py`、`memory_layer.py`、`user_store.py`
等核心模块仍然平铺在顶层。

随着 Pilot MVP 已完成，后续会同时推进 runtime、platform、memory、connectors 和 deployment 相关工作。
如果继续在平铺文件上叠加功能，容易出现多人并行修改同一文件、public API 边界漂移和迁移时机不一致的问题。

本 change 不移动代码，只沉淀 source module organization roadmap：定义目标 package map、迁移顺序、
shim 策略、首批实现型 specs 和不应提前迁移的范围。

## What Changes

- 新增 `docs/architecture/source-module-organization-roadmap.md`。
- 梳理 `src/fleetent` 当前平铺模块和已模块化目录。
- 定义目标 package map：
  - `runtime`
  - `platform`
  - `governance`
  - `channels`
  - `intelligence`
  - `integrations`
  - `observability`
  - `infrastructure`
- 明确迁移优先级：
  1. `admin-cli-module-split`
  2. `memory-layer-package-migration`
  3. `runtime-package-migration`
  4. `platform-user-center-package-migration`
  5. `channels-package-migration`
  6. `integrations-and-infrastructure-package-migration`
- 明确旧 import 路径保留 re-export shim，shim 不承载业务逻辑。
- 明确迁移前置检查、测试策略和不应一次性大搬家的原则。
- 更新 `module-boundaries` spec，要求维护 source organization roadmap。

## Out of Scope

- 不移动任何 Python 代码。
- 不重命名 import。
- 不新增 package。
- 不修改 runtime 行为。
- 不新增数据库 migration。
- 不清理 `__pycache__` 或其他本地生成文件。
- 不执行 `admin-cli-module-split`，只把它列为下一步首选实现型 spec。

## Module Boundary Impact

- **Owning package**：none，文档型 change；架构边界归 `module-boundaries` spec 管理。
- **Public API surface**：none。
- **Owned tables**：none。
- **Config namespace**：none。
- **Cross-module dependencies**：只记录目标依赖方向，不改变 import。
- **Migration / shim plan**：文档定义后续迁移必须使用 re-export shim；本 change 不创建 shim。
