# Intelligence 分层重构纲领（2026-06-08）

> 状态：**设计纲领，待 review**。本文档是后续一系列 OpenSpec change 的总纲，每个 change 都应引用此文档的判据、目标架构和阶段路线。
>
> 与 [`source-module-organization-roadmap.md`](./source-module-organization-roadmap.md) 的关系：那份 roadmap 把 `intelligence` 当作**单一顶层 package**（memory / long-term-ctx / reflection / knowledge-base / vector-store）。本文档**深入 intelligence 内部**，结论是它不应是单一 package，而要按职责裂解——KB 升格为独立组件、vector_store 升格为基础设施、外部摄取归 platform 控制面，并**解散 `intelligence/` 这一聚合层、把其内容平铺到顶层**。这是对 roadmap intelligence 条目的细化与演进；物理迁移复用 roadmap 的 [Shim 策略] 和 [每次迁移的验收要求]。

## 1. 背景与动机

起因是为 KB connector 设计定时同步（scheduler）时，发现一个解耦上的别扭：connector sync 是 platform 触发的运维操作，却因为代码物理上躺在 `intelligence/knowledge_base/`（被 CLAUDE.md 列为 agent runtime 模块、禁止 import platform / 写 platform 表），被迫把 connector 定义读成 agent 侧 config、把状态写进 agent 侧表。

深入排查后确认这是普遍问题：**`intelligence/` 把三种本质不同的职责混在一个"agent runtime"标签下，代码归属与实际用途严重错配。**

证据（2026-06-07 复核）：

- `knowledge_base/` 约 17/20 文件是摄取/管理（connectors、parsers、sync、extraction、operations…），只有 `runtime.search` / `graph_search` 是 agent 对话用的读。实际调用方：读 = `long_term_ctx`（agent 侧），写/管理 = `admin_cli` / `kb_admin_api`（platform 侧）。
- `get_connector_config` 读的是 agent 侧 `_kb_config`，状态写 agent 侧 `knowledge_connector_status`（owner=knowledge-base）——全程不碰 platform，是"控制面代码被关进 agent runtime 笼子"硬挤出来的结果。
- `vector_store/` 是无状态计算（embedding/rerank/backend），被 KB **和** memory 共同消费——本质是基础设施，却挂在 agent runtime 业务树下。

## 2. 核心判据

重构的归属判断不靠"在不在对话回合里"（那是错的判据，详见 §2.2），而靠以下三条。

### 2.1 判据一：关于自己 vs 外部对它

> **这个能力/数据，是「agent 关于自己 / 自己的交互」的，还是「外部世界 / 运维 对 agent」的？**

- **agent 关于自己**（可同步可异步）→ agent 能力：用自己的知识检索、从交互提取记忆、反思运行数据做自我进化。
- **外部对 agent** → 控制面：把外部数据源灌进库、运维管理 connector/配额/用户。

时间尺度（同步/异步、在不在对话回合）**不决定归属**。

### 2.2 判据二：审批门 ≠ 归控制面

> **一个能力即使其「变更」需要人工审批门，能力本体仍归 agent 侧。审批门是横切治理（governance），变更/审批的管理 API 是 platform 的薄暴露面，但能力本体不因此移走。**

这条是从两次返工中提炼的（reflection、shared memory 都曾被误判为控制面，理由都是"要人审批/有 admin API"）。审批门与 `governance/permission_gate`（agent 高风险操作的人工门）同类。

### 2.3 判据三：自进化是纵向元能力

> **reflection 不是与 memory/retrieval 并列的平铺能力，而是纵向贯穿各 agent 能力域的元能力**：它读 trace/memory/KB，产出对 user-memory / shared-memory / KB / skill 的改进建议，经统一审批门落地。它是 agent「关于自己」的最高阶形态。

## 3. intelligence/ 全模块分类

| 模块 / 子块 | 归属 | 理由 |
| --- | --- | --- |
| `vector_store/`（embedding/rerank/backend/namespaces/reindex） | 🔵 基础设施（跨域底座） | 无业务态，KB+memory 共同消费 |
| KB `core`（store/models）、memory `store` | 🔵 域内 core | 各域读写共享的持久化底层 |
| KB `retrieval`（search/graph_search/scope） | 🟢 agent 能力 | 用自己的知识 |
| memory 核心（extraction/search/maintenance） | 🟢 agent 能力 | 从交互学习、用/自维护记忆 |
| memory `shared` 核心（检索/被注入） | 🟢 agent 能力 | 对话时经 `long_term_ctx` 注入（tenant/team shared memory） |
| `long_term_ctx`(+policy) | 🟢 agent 能力 | 聚合自己的知识/记忆注入对话 |
| `reflection` 自进化引擎 | 🟢 agent 能力（纵向元能力） | 反思自己、自我进化 |
| KB `ingest`（connector/parser/sync/extraction） | 🟠 控制面（唯一实质块） | 把**外部世界数据**搬进 agent |
| 各能力的管理 API（建库/绑定/connector 配置/shared 录入/proposal 审批接口） | 🟠 控制面薄壳 | 能力本体在 agent 侧，这里只是管理暴露面 |
| 各能力变更的审批门（reflection 提案 / shared-memory 变更） | ⚙️ 治理（governance） | 与 permission_gate 同类 |

**收敛**：agent 能力层很厚；控制面塌缩到「**唯一实质块 = KB ingest** + 一圈管理薄壳」；治理（审批门）是横切。这与 fleetent「agent 自包含、platform 是管理增强」的定位吻合。

## 4. 自进化作用对象网络 + 写的双来源

代码已存在此设计（`reflection.py` action `suggest_shared_memory_or_kb`；`memory/shared.py` 的 `_SOURCES = {"manual", "reflection_proposal"}`）：

```
        ┌─────────── reflection 自进化引擎 (agent 元能力) ───────────┐
        │  读 trace/memory/KB → 产出改进建议                          │
        └──────┬─────────┬──────────┬──────────┬────────────────────┘
               ▼         ▼          ▼          ▼
          user memory  shared mem   KB        skill
               └─────────┴────┬─────┴──────────┘
                              ▼
                   ⚙️ 统一审批门 (governance)   ← 所有自进化「写」的人工把关
                              ▼
                   落地到各 agent 能力域
```

每个 agent 能力域的「写」有清晰的双来源：

| 能力域 | 自进化来源（agent，经审批门） | 外部/人工来源 |
| --- | --- | --- |
| user memory | reflection maintenance 提案 | 对话提取（agent 自己） |
| shared memory | reflection suggest（source=`reflection_proposal`） | 人工录入（`manual`） |
| KB | reflection `suggest_..._or_kb` | connector 外部摄取 |
| skill | reflection skill 提案 | 人工上传 |

除 **KB connector 外部摄取**（受信运维，唯一实质控制面，不经审批门）外，其它所有「写」要么是 agent 对话自然产生、要么是自进化经审批门落地——**全在 agent 侧，审批门是统一治理点**。

## 5. 目标架构与物理布局

```
# 解散 intelligence/ 聚合层，按高度平铺到顶层；纵向高度靠 §6 依赖护栏表达，不靠目录嵌套
src/fleetent/
  # ── 聚合 / 元能力 (依赖能力域, 不被反向依赖) ──
  long_term_ctx/    上下文聚合 (对话内, 被 runtime 调; 含 _policy)
  reflection/       自进化元能力 (异步; 审批门→governance, 管理 API→platform)

  # ── 能力域 ──
  memory/           提取·检索·自维护·shared 核心
  knowledge_base/   【独立组件 = 未来服务雏形】
    core/      store · models
    retrieval/ search · graph_search · scope   (agent 消费; 预留 agent 自主写入口)
    ingest/    connectors · parsers · sync · extraction  (platform 驱动)

  # ── 基础设施底座 ──
  vector_store/     embedding · rerank · backend   (KB+memory 消费)

  # ── 控制面 (已聚合) ──
  platform/
    knowledge_base_management/   KB ingest 编排·connector·调度·运维数据
    skill_management/            + reflection 提案审批 API
    (memory shared 的录入/审批 API 也归拢到 platform 薄壳)

  # ── 既有 (不变; governance 额外收纳审批门) ──
  runtime/  session/  im_gateway/  model/  observability/  tools/  ...
  governance/       ← 收纳 reflection / shared-memory 变更的审批门（与 permission_gate 同类）
```

`intelligence/` 目录在迁移完成后**删除**——它曾是顶层唯一的"二级聚合桶"，与 fleetent「顶层平铺 + 依赖规则表达层级」的哲学不符。`long_term_ctx` / `reflection` 是跨域聚合者/元能力，与 `memory` / `knowledge_base` 平级在顶层，其"更高层"由依赖方向（依赖后者、不被反向依赖）表达，无需目录嵌套。

## 6. 依赖护栏（迁移后由 import-linter / 测试断言强制）

```
long_term_ctx · reflection ─▶ memory · knowledge_base.retrieval ─▶ vector_store · 各域 core
runtime ─▶ long_term_ctx · memory · knowledge_base.retrieval
platform ─▶ knowledge_base.ingest · vector_store · (reflection 审批 API)
memory · knowledge_base ──✗──▶ long_term_ctx · reflection     (能力域不反依赖聚合者)
knowledge_base.retrieval ──✗──▶ knowledge_base.ingest          (读永不拉进摄取)
任何组件 ──✗──▶ platform                                        (组件不依赖控制面)
reflection 自进化「写」 ─▶ 统一审批门(governance) ─▶ 落地各域
```

## 7. 迁移路线（每阶段兼容垫片先行，测试全程绿）

复用 roadmap 的 Shim 策略：旧路径保留 re-export shim，调用方分批迁移，最后收窄。

```
阶段1  vector_store 提为顶层基础设施组件（底座先稳, KB+memory 都依赖它）
阶段2  KB 提为顶层独立组件 + 三分 core/retrieval/ingest; ingest 由 platform/knowledge_base_management 驱动
阶段3  reflection 提为顶层 + 拆 自进化引擎(agent)/审批门(governance)/管理API(platform);
       shared-memory 的提案落地随之归位（它是自进化的产出目标）
阶段4  memory · long_term_ctx 提为顶层; memory 核心确认无遗留控制面、shared 录入/审批 API 收到 platform 薄壳;
       long_term_ctx(+policy) 独立顶层, 被 runtime 调用
阶段5  删除已空的 intelligence/ 目录; 上 import 护栏 + 改 CLAUDE.md 架构契约（见 §8）
阶段6  (后置) knowledge_base 升格为独立服务: 检索 API(数据面) + 管理 API(控制面), self-hostable
```

每阶段验收（沿用 roadmap §每次迁移的验收要求）：

- `uv run pytest -x -q` 全绿；`uv run python scripts/check_test_layers.py` 通过。
- 旧 public 路径 re-export shim 保留，调用方迁移完成前不删。
- **解耦基线**：agent 在「无 platform、platform 表不存在」环境下，`fleetent agent run` 对话 + KB 检索 + memory + reflection 自进化（除审批落地外）正常工作。

## 8. 要改的 CLAUDE.md 架构契约点

重构落地（阶段5）时同步更新 CLAUDE.md：

1. **解散 `intelligence/` 聚合层**：架构目录树移除 `intelligence/` 节点，把 `long_term_ctx` / `reflection` / `memory` / `knowledge_base` / `vector_store` 平铺为顶层条目，与 runtime/session/governance 并列；纵向高度由依赖规则（§6）表达，不靠目录嵌套。
2. **重新定位平铺出来的组件**：`knowledge_base` = 独立组件、`vector_store` = 基础设施，不再属于「agent 运行时模块」列表、不受"不得 import platform"约束（它们本就不该依赖 platform，但理由从"是 agent runtime"改为"是独立组件/基础设施"）；`long_term_ctx` / `reflection` / `memory` 仍是 agent 能力，留 agent 侧。
3. 明确 **KB 读写边界**：`knowledge_base.retrieval`（agent 消费）/ `knowledge_base.ingest`（platform 驱动），retrieval ✗→ ingest。
4. 记录三条判据（§2）作为 agent 能力 vs 控制面归属的判断标准。
5. 明确**自进化的写经统一审批门**（governance），以及 KB 的 agent 自主写入口子。
6. 更新「现存待审计的 agent→platform 依赖」条目：`knowledge_base/config` 等随重构清理。

## 9. 开放问题

- **终局形态**（阶段6 单体内包边界 vs 抽独立服务进程）尚未定，先把 §5 边界画对，封装强度后续升级。
- **单机 agent（无 platform）摄取**：摄取做成 agent 进程之外的独立单元（ingest CLI 或 KB 服务）；单机是否运行它是部署选择，不影响 agent 只读纯净。
- **governance 自身**也混了 agent 治理（permission_gate）与 platform 治理（audit_log），与本重构相关但属另一条线，暂不扩入。
- reflection **异步执行的调度**（定时触发自进化）与 KB connector sync 调度同属 cron_scheduler 横切关注，归 platform 驱动。
