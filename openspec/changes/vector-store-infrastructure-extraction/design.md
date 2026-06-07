## Context

`vector_store` 公共面（`vector_store/__init__.py`）导出 15 个符号：`IndexableItem`、`SearchResult`、`Reindex*`、`Rerank*`、`search`/`upsert`/`delete`/`reindex`、`knowledge_namespace`/`memory_namespace`/`shared_namespace`、`configure_from_active_agent`、`create_rerank_provider`、`clear_namespace`。内部 6 文件：backend / embeddings / namespaces / reindex / rerank / runtime。

消费者 9 处：`knowledge_base/{config,runtime}`、`memory/{extraction,maintenance,operations,search,shared}`、`runtime/agent_app`、`agent_config`。

约束：纯结构重构，行为零变更，测试全程绿；沿用 roadmap 的 Shim 策略与验收要求。

## Goals / Non-Goals

**Goals:**
- vector_store 成为顶层基础设施组件，物理位置与定位一致。
- 公共 API 与行为完全不变，调用方可零感知迁移。
- 固化"基础设施不依赖业务/不依赖 platform"的依赖契约。

**Non-Goals:**
- 不重构 vector_store 内部、不改 rerank/embedding/namespace 逻辑。
- 不改 CLAUDE.md 契约文字（留阶段5 统一）。
- 不动其它 intelligence 模块。

## Decisions

### D1：整体移动 + 旧路径 re-export shim
`git mv intelligence/vector_store/ vector_store/`，在 `intelligence/vector_store/__init__.py` 留 `from fleetent.vector_store import *` + 显式 re-export `__all__`，使旧 import 路径继续可用。调用方分批改到新路径；全部迁完后删 shim（可能并入阶段5）。

- *替代*：一次性改所有 9 处调用方、不留 shim。否决——9 处分散，原子大改易出错且 review 面大；shim 让迁移可分批、可回退。

### D2：namespace helper 的业务命名留在 vector_store
`knowledge_namespace`/`memory_namespace`/`shared_namespace` 让基础设施"知道"业务命名空间，看似边界渗漏。本 change **不动**它——它只是命名约定（字符串前缀），非业务逻辑依赖。是否下沉为调用方传入留作 §Open Questions，不阻塞本阶段。

### D3：依赖契约用测试断言固化
新增一个轻量测试：断言 `vector_store` 包不 import `fleetent.platform`、不 import `fleetent.knowledge_base` / `fleetent.intelligence`（业务）。作为 TDD 的"红"起点（移动前在 intelligence 下，断言新位置不存在会红）。完整 import-linter 护栏留阶段5。

## Risks / Trade-offs

- **遗漏某处 import** → shim 兜底，遗漏的旧路径仍可用；CI 全绿 + 全仓 grep 校验无残留硬编码路径。
- **循环 import**（vector_store 顶层后被 agent_config 等更底层模块用） → agent_config 已经在用它，移到顶层不改变依赖方向；移动后跑全量测试确认无循环。
- **git 历史** → 用 `git mv` 保留文件历史。

## Migration Plan

1. `git mv` 整体移动 6 文件到 `src/fleetent/vector_store/`。
2. 旧路径留 re-export shim。
3. 分批改 9 处调用方 import（或暂留 shim，逐个迁）。
4. 全量测试绿 + grep 确认无残留。shim 删除可并入阶段5。
5. 回滚 = 反向 `git mv` + 删 shim；因行为不变，回滚安全。

## Open Questions

- namespace helper（D2）是否下沉为调用方传入——后续可选优化，不阻塞。
- shim 删除时机：本 change 末尾 vs 阶段5 统一收口——倾向阶段5。
