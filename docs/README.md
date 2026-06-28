# fleetent docs

本目录保存 fleetent 的架构、能力、部署和项目记录文档。具体实现任务通过 OpenSpec 工作流管理。

## 目录结构

```text
docs/
  README.md                    # 本文件：导航 + 写作规范
  strategy.md                  # 战略背景：为什么做、卖什么、与竞品的差异
  architecture.md              # 架构总览，当前权威入口：模块关系、数据流、关键决策
  glossary.md                  # 术语表
  architecture/
    target-architecture.md    # 详细架构模型：核+4面+基座、模块边界、Identity、只读投影、模块归属速查
    data-model.md             # 数据模型与物理拓扑（as-built）
  capabilities/
    _template.md              # 能力域文档模板
    *.md                      # 能力定义、状态和验收标准；子系统深度行为模型（agent-management / im-access-model / skill-system）也在此
  roadmaps/                   # 能力簇 roadmap、Pilot readiness 总览和人工测试手册
  operations/
    pilot-runbook.md           # Pilot 部署与人工验收流程
    pilot-install-checklist.md # 安装、升级、备份、健康检查和问题上报清单
    pilot-acceptance-guide.md  # Go / Conditional Go / No-Go 判定和报告模板
    secrets.md                 # Secret 和凭据处理指南
    monitoring.md              # 监控与告警配置指南
    per-agent-sandbox-config.md # 迁移指南：沙箱配置从 platform.yaml 移至 agent.yaml
  records/
    integration/               # 一次性集成方案与执行日志
    decision-logs/             # apply/review 过程中的决策记录（含已冻结的 agent-identity-model）
    roadmaps/                  # 历史开发排期和执行计划记录
  archive/                     # 过期设计、旧 internals deep dive、历史调研
```

## 文档类型

| 类型 | 放置位置 | 内容边界 |
| --- | --- | --- |
| 架构文档 | `docs/architecture.md`, `docs/architecture/` | `architecture.md` 是架构总览和当前权威入口；`architecture/` 放架构演进路线图和专题文档。 |
| 能力文档 | `docs/capabilities/` | 做什么、当前状态、规划项、验收标准和模块归属。 |
| 能力 roadmap | `docs/roadmaps/` | 多个相关 capability 的完成度、缺口、优先级和 Pilot 风险。 |
| 运维文档 | `docs/operations/` | 安装、升级、备份、运行、验收、secret 处理和迁移指南。 |
| 项目记录 | `docs/records/` | 集成方案、执行日志、review/apply 决策记录。 |
| 归档资料 | `docs/archive/` | 不再作为当前事实来源的旧设计、历史调研和 deep dive。 |

## Roadmap 索引

| Roadmap | 用途 |
| --- | --- |
| `docs/roadmaps/pilot-readiness-roadmap.md` | 全项目 Pilot readiness 总览、验收入口和 Go / Conditional Go / No-Go 风险。 |
| `docs/roadmaps/runtime-tooling-roadmap.md` | Agent Runtime、Model Router、Tools、MCP、Sandbox、Skill、Session 能力簇。 |
| `docs/roadmaps/intelligence-roadmap.md` | Memory、Long-term Context、Reflection、Vector Store、Knowledge Base 能力簇。 |
| `docs/roadmaps/observability-deployment-roadmap.md` | Observability、Diagnostics、Deployment / Config 能力簇。 |
| `docs/roadmaps/platform-channel-roadmap.md` | Platform、Governance、User Center、Connectors、IM Gateway、Scheduling / Webhook 能力簇。 |
| `docs/records/roadmaps/v1.0-roadmap.md` | 历史 v1.0 执行引擎开发排期记录。 |

## 能力域索引

| 文档 | 覆盖范围 | 优先级 | 依赖的模块 | 负责人 | 状态 |
|------|---------|:------:|-----------|--------|------|
| [roadmaps/pilot-readiness-roadmap.md](roadmaps/pilot-readiness-roadmap.md) | Pilot readiness 横向总览、Go / Conditional Go / No-Go 风险和验收入口 | P0 | 全项目 capability | - | 基础完成 |
| [roadmaps/intelligence-roadmap.md](roadmaps/intelligence-roadmap.md) | Memory / Long-term Context / Reflection / Vector Store / Knowledge Base 能力簇 roadmap | P0 | memory · long-term-ctx · reflection · vector-store · knowledge-base | - | 基础完成 |
| [roadmaps/observability-deployment-roadmap.md](roadmaps/observability-deployment-roadmap.md) | Observability / Diagnostics / Deployment / Config 能力簇 roadmap | P0 | observability · config-management | - | 基础完成 |
| [agent-runtime.md](capabilities/agent-runtime.md) | 核心循环、工具调度、上下文压缩、运行治理 | P0 | model-router · tools · session · skill · governance · observability | 张洋 | 部分完成 |
| [model-router.md](capabilities/model-router.md) | task_type 路由、provider 配置、fallback 链 | P0 | config-management | 张洋 | 部分完成 |
| [tools.md](capabilities/tools.md) | @tool 装饰器、schema 构建、dispatch、内置工具集 | P0 | governance · connectors | 张洋 | 部分完成 |
| [session.md](capabilities/session.md) | session 持久化、并发保护、生命周期管理 | P0 | - | 张洋 | 已实现 |
| [im-gateway.md](capabilities/im-gateway.md) | Slack / Telegram 接入、用户映射 | P0 | session · governance · platform | 张亮 | 部分完成 |
| [governance.md](capabilities/governance.md) | 权限审批、工具白名单、agent 定义与分配 | P0 | session | 张亮 | 部分完成 |
| [observability.md](capabilities/observability.md) | 评估日志、数据统计、链路追踪 | P0 | - | 常乐 | 基础完成 |
| [mcp.md](capabilities/mcp.md) | MCP 外部工具集成（stdio / HTTP） | P1 | connectors | 张洋 | 部分完成 |
| [sandbox.md](capabilities/sandbox.md) | 安全代码执行（Docker / microsandbox 可插拔后端） | P1 | - | 张洋 | 部分完成 |
| [skill.md](capabilities/skill.md) | Skill 发现、read-on-demand 注入、catalog | P1 | - | 张洋 | 部分完成 |
| [platform.md](capabilities/platform.md) | 用户管理、API 认证、admin CLI、node 编排 | P1 | - | 张亮 | 部分完成 |
| [scheduling.md](capabilities/scheduling.md) | Cron 定时任务、Webhook 事件触发 | P1 | agent-runtime · session · im-gateway | 张亮 | 部分完成 |
| [memory.md](capabilities/memory.md) | User Memory、Agent Memory、维护 proposal、质量趋势 | P1 | model-router · vector-store · observability · reflection | 常乐 | 基础完成 |
| [long-term-ctx.md](capabilities/long-term-ctx.md) | 长期上下文调度与注入，memory / knowledge-base / Agent Memory provider 和 context policy | P1 | memory · knowledge-base | 常乐 | 基础完成 |
| [knowledge-base.md](capabilities/knowledge-base.md) | 企业文档知识库、local / Google Drive / Confluence 同步、hybrid / graph / rerank / planner | P1 | vector-store | 常乐 | 基础完成 |
| [vector-store.md](capabilities/vector-store.md) | 向量索引、SQLite backend、embedding / rerank provider、同步 reindex | P1 | config-management | 常乐 | 基础完成 |
| [config-management.md](capabilities/config-management.md) | on-premises 打包、配置管理、SQLite upgrade / backup | P1 | - | 常乐 | 基础完成 |
| [connectors.md](capabilities/connectors.md) | connector seam 与 agent-side 凭证注入口（platform vault 已退役） | P2 | runtime · tools | 张亮 | 基础完成 |
| [reflection.md](capabilities/reflection.md) | User Memory / Skill / 知识库反思、proposal lifecycle、趋势聚合 | P2 | memory · skill · knowledge-base · observability | 常乐 | 基础完成 |
| [agent-management.md](capabilities/agent-management.md) | Agent 生命周期、版本、管理态、materialize、node 编排（as-built 行为模型） | — | — | — | as-built |
| [im-access-model.md](capabilities/im-access-model.md) | IM bot 接入身份、三层访问控制、配置同步契约（as-built 行为模型） | — | — | — | as-built |
| [skill-system.md](capabilities/skill-system.md) | Skill 子系统完整行为：read-on-demand、平台治理、drift 检测、backflow 回流（as-built 行为模型） | — | — | — | as-built |

## 写作规范

**功能描述**：「现状」和「规划中」每条只写可观察的行为，不写内部实现细节。有必要时加子 bullet 补充边界和约束。

**模块归属**：每份 capability 文档应声明 owning package、public API、owned tables、config namespace 和 cross-module dependencies。没有持久化或配置时写「无」，不要省略。

**验收标准**：只写用户或调用方能观察到的行为（端到端视角）。单元级断言写在 OpenSpec 的测试任务里，不在这里。

**项目记录隔离**：一次性执行日志、分支合并计划、review 决策和 apply 过程记录放在 `docs/records/`，不要放进 `docs/capabilities/` 或 docs 根目录。

**漂移处理**：实施过程中设计有变化，同步更新文档对应 section。文档是活的，不是归档记录。

**版本迭代**：`规划中（vX.X）` 的条目实现后移入「现状」并打 ✅，进入下一版本时将 section 标题改为新版本号并添加新条目。历史版本通过 `git tag` 查看，无需维护多份文档。
