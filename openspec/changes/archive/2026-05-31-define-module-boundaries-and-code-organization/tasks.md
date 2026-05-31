## 1. 文档落地

- [x] 1.1 更新 `docs/architecture.md`：补充模块化单体目标 package map，并说明 legacy 平铺模块可渐进迁移
- [x] 1.2 更新 `docs/README.md` 或 capability 模板：新增 capability 文档需要声明 owning package、public API、owned tables、config namespace、cross-module dependencies
- [x] 1.3 更新与你负责的 intelligence 相关 capability 文档：统一 canonical name（`memory_layer`、`knowledge_base`、`long_term_ctx`、`vector_store`、`reflection`、`observability`）
- [x] 1.4 更新 `deployment.md` / `architecture.md` 中 DB runtime 相关描述：只引用 `introduce-database-runtime-boundary`，不重复定义具体接口

## 2. OpenSpec 约束

- [x] 2.1 给 OpenSpec change 作者增加自检清单：package owner、public API、owned tables、config namespace、依赖方向、shim 计划
- [x] 2.2 检查当前 active changes，标记哪些 change 会触碰共享契约（DB runtime、admin/user、IM gateway），避免本 change 与它们抢实现文件
- [x] 2.3 为后续 intelligence 模块规划第一批独立 OpenSpec changes：`vector-store-foundation`、`observability-trace-contract`、`long-term-context-contract`

## 3. 轻量结构检查

- [x] 3.1 Write failing tests or script check：已迁移 package 的 internal 模块不得被其他 package import
- [x] 3.2 实现轻量检查脚本或 pytest，用 `ast` 扫描 `src/fleetent` import，先只检查 `_internal` / leading underscore 违规 import
- [x] 3.3 将检查加入测试文档或 CI 建议，但不阻塞 legacy 平铺模块

## 4. 迁移示范

- [x] 4.1 选择第一个示范迁移模块（建议在 `vector_store` 或 `observability` 中二选一，避开正在执行的 DB runtime 文件）
- [x] 4.2 Write failing tests：旧 import 路径通过 compatibility shim 仍可导入 public API
- [x] 4.3 创建目标 package，并把示范模块的新业务逻辑放入目标 package；旧路径只做 re-export shim
- [x] 4.4 更新相关 import 和文档，确认没有调用方 import 示范模块 internal implementation

## 5. 验证与收尾

- [x] 5.1 运行 `openspec status --change define-module-boundaries-and-code-organization`，确认 proposal/design/specs/tasks 全部就绪
- [x] 5.2 运行 `uv run pytest -x -q`，确认结构检查和 shim 示例不破坏现有测试
- [x] 5.3 运行 ruff 验证：targeted ruff 通过；全仓 `uv run ruff check src tests scripts` 已运行但存在既有 lint 问题，另行处理
- [x] 5.4 运行 mypy 验证：`uv run mypy src` 已运行但当前环境缺少 `mypy` 可执行文件，另行处理
- [x] 5.5 自检：本 change 没有引入 ORM、AI framework、云专有服务，也没有大规模机械搬迁现有模块
