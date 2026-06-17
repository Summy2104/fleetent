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
    agent-management.md       # Agent 管理子系统行为模型
    im-access-model.md        # IM 接入与访问控制模型
    skill-system.md           # Skill 子系统行为模型
  capabilities/
    _template.md              # 能力域文档模板
    *.md                      # 能力定义、状态和验收标准
    roadmaps/                 # 能力簇 roadmap、Pilot readiness 总览和人工测试手册
  deployment/
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
| 能力 roadmap | `docs/capabilities/roadmaps/` | 多个相关 capability 的完成度、缺口、优先级和 Pilot 风险。 |
| 部署文档 | `docs/deployment/` | 安装、升级、备份、运行、验收、secret 处理和迁移指南。 |
| 项目记录 | `docs/records/` | 集成方案、执行日志、review/apply 决策记录。 |
| 归档资料 | `docs/archive/` | 不再作为当前事实来源的旧设计、历史调研和 deep dive。 |

## Roadmap 索引

| Roadmap | 用途 |
| --- | --- |
| `docs/capabilities/roadmaps/pilot-readiness-roadmap.md` | 全项目 Pilot readiness 总览、验收入口和 Go / Conditional Go / No-Go 风险。 |
| `docs/capabilities/roadmaps/runtime-tooling-roadmap.md` | Agent Runtime、Model Router、Tools、MCP、Sandbox、Skill、Session 能力簇。 |
| `docs/capabilities/roadmaps/intelligence-roadmap.md` | Memory、Long-term Context、Reflection、Vector Store、Knowledge Base 能力簇。 |
| `docs/capabilities/roadmaps/observability-deployment-roadmap.md` | Observability、Diagnostics、Deployment / Config 能力簇。 |
| `docs/capabilities/roadmaps/platform-channel-roadmap.md` | Platform、Governance、User Center、Connectors、IM Gateway、Scheduling / Webhook 能力簇。 |
| `docs/records/roadmaps/v1.0-roadmap.md` | 历史 v1.0 执行引擎开发排期记录。 |

## 写作规范

**功能描述**：「现状」和「规划中」每条只写可观察的行为，不写内部实现细节。有必要时加子 bullet 补充边界和约束。

**模块归属**：每份 capability 文档应声明 owning package、public API、owned tables、config namespace 和 cross-module dependencies。没有持久化或配置时写「无」，不要省略。

**验收标准**：只写用户或调用方能观察到的行为（端到端视角）。单元级断言写在 OpenSpec 的测试任务里，不在这里。

**项目记录隔离**：一次性执行日志、分支合并计划、review 决策和 apply 过程记录放在 `docs/records/`，不要放进 `docs/capabilities/` 或 docs 根目录。

**漂移处理**：实施过程中设计有变化，同步更新文档对应 section。文档是活的，不是归档记录。

**版本迭代**：`规划中（vX.X）` 的条目实现后移入「现状」并打 ✅，进入下一版本时将 section 标题改为新版本号并添加新条目。历史版本通过 `git tag` 查看，无需维护多份文档。
