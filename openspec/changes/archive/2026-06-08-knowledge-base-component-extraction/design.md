## Context

KB 现状（2026-06-08 核对）：`intelligence/knowledge_base/` 20 文件，职责混杂集中在三处——

- `runtime.py`(530)：容器 CRUD（`create/update_description/archive/list_knowledge_bases`）+ 文档 ingest（`ingest_text`/`ingest_parsed`/`_ingest_chunks`）+ 检索（`search`/`_search_vector`/`_search_hybrid`/rerank helpers）+ 文档删除归档（`delete`/`delete_document`/`archive`）全在一个文件。
- `store.py`(542)：`KnowledgeStore` 读写方法同一类，无读写接口区分。
- `bindings.py`(181)：scope 读（`resolve_agent_kb_ids`/`_get_binding`）与绑定写（`bind/unbind/list_agent_kb_bindings`）混。

其余：`graph_search.py`(385) 读、`extraction.py`+`extraction_store.py`（图谱抽取，写）、`connectors/*`（摄取）、`parsers.py`、`planner.py`/`sync_planner.py`（摄取编排）、`config.py`(143, connector 定义加载)、`models.py`。

消费方：agent 侧 `long_term_ctx`（读）；platform `knowledge_base_management/{kb_admin_api(24K),kb_connector_store,agent_kbs_store}`、`admin_cli`（写/管理）。当前 `intelligence/knowledge_base/` 无 `import fleetent.platform`（CLAUDE.md 点名的 `config` 依赖已不存在，迁移时复核）。

约束：结构重构、行为零变更、测试全程绿；沿用 roadmap Shim 策略与验收要求；依赖阶段1（vector_store 顶层）。

## Goals / Non-Goals

**Goals:**
- KB 成顶层独立组件，按 `core / retrieval / ingest / management` 四块归位，定位一致（未来服务雏形）。
- 读写边界由**类型**表达：retrieval 只见 core 的 Readable Protocol；ingest/management 见 Writable。
- KB 内容写入路径**单一**（只 ingest/sync），retrieval 不开写口。
- ingest 接收注入的 settings，消解 connector 双源。
- 公共 API 行为不变，调用方可分批迁移。

**Non-Goals:**
- 不改检索/rerank/embedding/graph 算法、不改 namespace 约定、不改 connector 协议。
- 不改 CLAUDE.md 契约文字（留阶段5）。
- 不做阶段6 的独立服务进程化（仅画对组件内边界）。
- 不动 reflection 对 KB 的反思（阶段3）。

## Decisions

### D1：四块结构 core / retrieval / ingest / management
按纲领 §5。`git mv` 后在 `knowledge_base/__init__.py` 留 re-export shim、`intelligence/knowledge_base/__init__.py` 留旧路径 shim。文件归属：

| 块 | 文件 / 函数 | 方向 |
| --- | --- | --- |
| `core/` | `store.py`（Readable/Writable Protocol + `KnowledgeStore` 实现）、`models.py` | 读写底层 |
| `retrieval/` | `runtime.py` 的 `search`/`_search_vector`/`_search_hybrid`/rerank helpers；`graph_search.py`；`bindings.py` 的 `resolve_agent_kb_ids`/`_get_binding`（→ `scope`） | 只读 |
| `ingest/` | `runtime.py` 的 `ingest_text`/`ingest_parsed`/`_ingest_chunks`/`delete*`/`archive*`；`connectors/*`；`parsers.py`；`extraction.py`；`extraction_store.py`；`planner.py`；`sync_planner.py`；`config.py` | 内容写（唯一） |
| `management/` | `runtime.py` 的 `create_knowledge_base`/`update_knowledge_base_description`/`archive_knowledge_base`/`list_knowledge_bases`/`list_documents`；`bindings.py` 的 `bind/unbind/list_agent_kb_bindings` | 容器/绑定写 |

- *替代*：保持单 `runtime.py`、仅加护栏约定。否决——读写在同一文件里靠约定隔离会漂移，四块物理隔离才能让护栏断言可机械验证。

### D2：core 暴露 Readable / Writable 两个 Protocol、一份实现
`core/store.py` 定义 `KnowledgeReadable`（search/get/list/iter 读方法）与 `KnowledgeWritable`（upsert/delete/archive 写方法）两个 `typing.Protocol`，`KnowledgeStore` 单实现两者。`retrieval/` 的函数签名只接受/返回 `KnowledgeReadable`，**类型层面**拿不到写方法；`ingest/`/`management/` 用 `KnowledgeWritable`。读写隔离由 mypy + 护栏断言双重保证，无需两份实现。

- *替代*：拆 `ReadStore`/`WriteStore` 两个类。否决——两份实现重复 SQL、易不一致；Protocol + 单实现是注入模式的标准答案。

### D3：KB 写入单一化——retrieval 不开写口
KB 是**派生视图**（纲领 §4）。原 proposal 的"预留 agent 自主写入口"是误判，本 change 纠正：retrieval 侧**不暴露任何写接口**。agent/reflection 对 KB 的贡献**不直接写 KB**，而是写它的真相源——agent-curated 沉淀源（阶段3 reflection 展开），再经 connector sync 流入 KB。这样下次 sync 不会与数据源不一致（无孤儿/可追溯/可重新摄取）。KB 内容写入路径因此唯一：`ingest/sync`。

### D4：ingest 接收注入的 settings，消解 connector 双源
现状 `runtime._kb_config()` / `bindings._kb_config()` / `config.load_knowledge_config()` 让 ingest 自读 agent 侧 `_kb_config`，而 platform 另有 `kb_connectors` 表——双源。决策：

1. **ingest 对来源无知**：对外入口做成**接收 `KnowledgeBaseSettings` 的纯函数**，经 `as_knowledge_base_settings` adapter 注入；ingest 不再自读家目录 config。
2. **connector 单一真相源 = platform `kb_connector_store`（`kb_connectors` 表）**：platform `knowledge_base_management` 读该表、注入 ingest。**移除 agent 侧 `_kb_config` 的 connector 读取**——双源由此消除。
3. 单机无 platform 时，由 ingest CLI（纲领 §9，本 change 不实现）从本地来源注入；agent 对话路径（retrieval）不碰 connector，不受影响。

connector 是 platform 运维概念，单一源归 platform 表符合归属判据；注入模式让 ingest 对来源无知，二者正交、互不矛盾。

- *替代*：统一到 agent 侧 `_kb_config` 单源、platform 也读它。否决——让 agent runtime 持有运维概念违反归属判据。
- *替代*：保留双源、按部署选源。否决——双源维护负担不消除，正是本次要解决的别扭。

### D5：graph extraction 归 ingest，graph_search 归 retrieval
实体/关系抽取（`extraction.py`/`extraction_store.py`）是对**已摄取文档**的加工——写边界，归 ingest。`graph_search.py` 是读——归 retrieval。两者共享 entity/relation 表，经 core 的 Readable/Writable 切：graph_search 用 Readable 读图，extraction 用 Writable 写图。

### D6：依赖护栏渐进上（本阶段加 KB 三条）
新增轻量护栏测试断言：① `knowledge_base.retrieval` ✗→ `knowledge_base.ingest`；② `knowledge_base`（含子包）✗→ `fleetent.platform`；③ `knowledge_base.core` ✗→ `retrieval`/`ingest`/`management`（core 不反依赖上层）。完整 §6 全量护栏留阶段5 收口。TDD：移动前断言新结构不存在 → 红。

## Risks / Trade-offs

- **拆 `runtime.py` 引入回归** → 拆分是纯移动函数 + 改 import，先固化现有测试为基线，逐块迁移后跑全量；shim 兜底旧路径。
- **Readable/Writable Protocol 与现有调用不匹配** → Protocol 按 `KnowledgeStore` 现有公共方法签名抽取，实现零改；mypy strict 验证。
- **ingest settings 注入改调用方** → platform `kb_admin_api` 需改为注入 settings，是本 change 的实质改动面；用 `as_knowledge_base_settings` 把改动收敛到一处 adapter，行为不变。
- **循环 import**（四块互相引用） → 依赖方向单向：retrieval/ingest/management → core；retrieval ✗→ ingest。护栏测试守。
- **git 历史** → `git mv` 保留。

## Migration Plan

1. `git mv intelligence/knowledge_base/ knowledge_base/`，建 `core/retrieval/ingest/management/` 子包，按 D1 表移动文件/函数。
2. core 抽 Readable/Writable Protocol（D2），retrieval 签名改为只接受 Readable。
3. ingest 对外入口改为接收 settings 纯函数 + `as_knowledge_base_settings`（D4）。
4. 旧路径 `intelligence/knowledge_base/__init__.py` 留 re-export shim。
5. 分批迁调用方：`long_term_ctx` → `retrieval`；platform `kb_admin_api`/`admin_cli` → `ingest`/`management` + 注入 settings。
6. 加 KB 三条护栏断言（D6）。
7. 全量测试 + grep 无残留 + check_test_layers 绿。
8. 回滚 = 反向 `git mv` + 删 shim；行为不变，回滚安全。

## Open Questions

- ingest 单机摄取入口（CLI / KB 服务）的形态——纲领 §9，阶段6 再定，本阶段只保证 ingest 对配置来源无知。
- connector 真相源已定 = platform `kb_connector_store`（D4）；`config.py` 的 connector 定义模型在 ingest 侧仅保留**被注入的 settings 形状**，不再作为 agent 侧来源。阶段6 服务化时若需独立 connector 配置 API 再议。
- shim 删除时机：本 change 末尾 vs 阶段5 统一收口——倾向阶段5。
