# Jira 回填计划：Fleetent 0 → Pilot Go

> 草案，供 review。目标：把 fleetent 从 0 到 Pilot Go 的全部工作回填进 Jira 项目 `AAA`（Northstar 项目管理），
> 包含**已完成**（201 个 openspec 归档 change）和**待办**（到 Pilot Go 的剩余项）。
>
> **决策基线**（已与 Randy 确认）：
> - 粒度：**中粒度** —— 相关小 change 合并成一个 Story（~70 Story）
> - 范围：**只建 feature** —— 过滤纯重构（`restructure-*`/`*-package-migration`/`shim-cleanup`）、测试层调整、CI、roadmap/docs
> - 状态：已完成→`DONE`，待办→`TO DO`/`IN PROGRESS`；Story point 由 Claude 粗估（斐波那契 1-5）
> - Assignee：按 `docs/architecture.md` 模块负责人
> - **Fix version：全部统一挂 `AI-Agent 平台-v1.0.0` 一个**（不按里程碑拆多个 Version）
> - 时间线：以 openspec 归档目录日期为准（git commit 日期不可信）
>
> **规范偏离说明**：你们敏捷规范要求 Epic 子 SP 总和 < 13。本回填是**历史追溯**，按能力域聚合，
> 多数 Epic 会超过 13 SP —— 这是有意为之（追溯准确性 > 冲刺尺寸）。仅"待办"部分（V5）严格按 < 13 拆。

---

## 负责人映射（来自 docs/architecture.md:196-220）

| 负责人 | 能力域 / Epic |
|--------|--------------|
| **张洋** | Agent Runtime · Model Router · Tools · MCP · Sandbox · Skill · Session |
| **张亮** | IM Gateway & Channels · Governance · Scheduling · Admin Console · User Center & Platform |
| **常乐** | Memory · Long-term Context · Reflection · Knowledge Base · Vector Store · Observability · Deployment · Pilot 验收 |

## Fix Version

**唯一 Fix version：`AI-Agent 平台-v1.0.0`** —— 所有 Epic / Story / Task 的 Fix versions 字段都填它，不拆多个 Version。

下面表里的 `V1~V5` 仅作**阶段标签**用于排序和理解时间线（来自 openspec 归档日期），**不是 Jira Version**：

| 阶段标签 | 日期段 | 主题 | 状态 |
|---------|-------|------|------|
| **V1 · IM MVP 基础** | 05-24~25 | Slack/Telegram、cron、webhook、准入、fallback | DONE |
| **V2 · 智能层 + 运行时治理** | 05-31~06-01 | KB/memory/vector/LTC/reflection + loop/压缩/sandbox/MCP/tools | DONE |
| **V3 · 管理后台 + Pilot 前置** | 06-02~03 | Admin Console、tui-gateway、pilot 验证套件 | DONE |
| **V4 · 配置/安装/收口** | 06-04 | 单 agent config、install、per-agent-slack、KB 真实 client | DONE |
| **V5 · Pilot Go 收口** | 待办 | 横向复核 + 准生产演练 + 验收签字 + 流式审批 | TO DO |

---

# 已完成部分（DONE）— 按 Epic

> 每个 Story 后标注：`[SP]` 估点 · `Vn` 所属 Version · 覆盖的代表性 change。

## 张洋的 Epic

### E1 · Agent Runtime 治理 — 张洋
| Story | SP | Ver | 覆盖 change |
|-------|----|----|-----------|
| 运行终止框架（max_turns/budget/cancelled/approval_rejected/loop 等终止条件） | 3 | V2 | termination-framework |
| 上下文压缩体系（双阈值触发 + 分层保留 + 增量摘要 + 压缩前清理 + 反抖动 + trace） | 5 | V2 | compression-dual-threshold, -layered-retention, -incremental-summary, -pre-cleanup, -anti-flap, -trace |
| 迭代预算与 Grace Call | 2 | V2 | iteration-budget-grace-call |
| 五层成本预算管控 | 3 | V2 | cost-budget-control |
| 循环检测 | 2 | V2 | loop-detection |
| 错误分类与重试策略 | 3 | V2 | error-classification |
| 消息卫生与契约修复 | 2 | V2 | message-hygiene |
| 取消与超时传播 | 2 | V2 | cancellation-propagation |
| 子 agent 生命周期管理 | 2 | V2 | sub-agent-lifecycle |
| 工具并行调度 | 3 | V2 | tool-parallel-dispatch |
| Prompt cache 优化 | 2 | V2 | prompt-cache-optimization |

### E2 · Tools 工具体系 — 张洋
| Story | SP | Ver | 覆盖 change |
|-------|----|----|-----------|
| 工具护栏 + 参数消毒 + Secret 过滤 | 3 | V2 | tool-call-guardrails, tool-arg-sanitization |
| 工具超时保护 + 结果截断 | 2 | V2 | tool-timeout, tool-result-truncation |
| 插件工具机制 | 2 | V2 | plugin-tools |
| 图像生成工具 | 2 | V2 | image-generation-tool |
| 多模态输入 + Vision-as-tool | 3 | V2 | multimodal-input, vision-as-tool |

### E3 · Sandbox 沙盒 — 张洋
| Story | SP | Ver | 覆盖 change |
|-------|----|----|-----------|
| 沙盒生命周期 + 启用控制（off/selective/all 三态） | 3 | V2 | sandbox-lifecycle, sandbox-enablement-control |
| 沙盒资源限制可配置 + 执行超时 + 输出截断 | 3 | V2 | sandbox-resource-limits, -exec-timeout, -output-truncation |
| 沙盒密钥过滤 + trace 写入 + 孤儿容器清理 | 3 | V2 | sandbox-secret-injection, -trace-logging, -orphan-cleanup |

### E4 · MCP 集成 — 张洋
| Story | SP | Ver | 覆盖 change |
|-------|----|----|-----------|
| MCP HTTP Streamable 标准支持 | 3 | V2 | mcp-http-streamable |
| MCP 会话管理 + 健康检查与重连 | 3 | V2 | mcp-session-management, mcp-health-reconnect |
| MCP 降级策略 | 2 | V2 | mcp-degradation |
| MCP OAuth2 认证 + server 配置拆分 | 3 | V2 | mcp-oauth2, mcp-server-config-split |

### E5 · Skill 系统 — 张洋
| Story | SP | Ver | 覆盖 change |
|-------|----|----|-----------|
| 内置 skill 集 | 2 | V2 | builtin-skills |
| YAML frontmatter 解析 + 按需读取 + 嵌套扫描 | 3 | V2 | skill-yaml-frontmatter, skill-read-on-demand, skill-nested-scan |
| 同名冲突警告 + 环境变量重命名 | 1 | V2 | skill-name-conflict-warning, skill-env-var-rename |
| Skill 禁用机制 + 热加载 + 注入审计 | 3 | V2 | skill-disable-mechanism, skill-hot-reload, skill-injection-audit |
| Agent-skill scoping | 2 | V3 | agent-skill-scoping |

### E6 · Session 会话 — 张洋
| Story | SP | Ver | 覆盖 change |
|-------|----|----|-----------|
| Session 磁盘管理 + TTL 清理 + 元数据索引 | 3 | V2 | session-disk-management, session-ttl-cleanup, session-metadata-index |
| 定时任务 session 绑定语义 | 2 | V2 | scheduled-task-session-binding |
| 内部 session 维护入口 | 1 | V3 | internal-session-maintenance |

### E7 · Model Router 路由 — 张洋
| Story | SP | Ver | 覆盖 change |
|-------|----|----|-----------|
| Fallback 链 | 2 | V1 | model-fallback-chain |
| 模型参数配置 + 路由外置化 | 2 | V2 | model-parameter-config, model-routes-externalize |
| 请求级路由覆盖 + 成本感知路由 + 健康探针缓存 | 3 | V2 | request-routing-override, cost-aware-routing, provider-health-probe-cache |

## 张亮的 Epic

### E8 · IM Gateway & Channels — 张亮
| Story | SP | Ver | 覆盖 change |
|-------|----|----|-----------|
| Slack + Telegram MVP（归一化 pipeline） | 5 | V1 | slack-telegram-mvp |
| IM 用户准入控制 + 身份映射 | 3 | V1 | im-user-access-control |
| IM 图片附件提取 | 2 | V2 | im-image-attachment-extraction |
| Per-agent Slack connector + 用户级 IM connector | 3 | V4 | per-agent-slack-connector, user-scoped-im-connectors |
| TUI 网关（WebSocket /ws） | 3 | V3 | tui-gateway |
| Slack E2E 测试套件 | 2 | V4 | slack-e2e-test-suite |

### E9 · Governance 权限治理 — 张亮
| Story | SP | Ver | 覆盖 change |
|-------|----|----|-----------|
| Connector 凭证注入 | 2 | V2 | connector-credential-injection |
| Agent-scoped OAuth MCP 绑定 | 3 | V3 | agent-scoped-oauth-mcp |

### E10 · Scheduling & Webhook — 张亮
| Story | SP | Ver | 覆盖 change |
|-------|----|----|-----------|
| Cron 定时任务 | 3 | V1 | cron-scheduled-tasks |
| Webhook 事件触发（HMAC 验签 + 消息提取） | 3 | V1 | webhook-triggers |

### E11 · Admin Console 管理后台 — 张亮
| Story | SP | Ver | 覆盖 change |
|-------|----|----|-----------|
| 多 agent 管理 + Agent CRUD console | 5 | V3 | multi-agent-management, agent-management-console, complete-agent-crud-console |
| Agent 模板体系（可编辑模板 + 子页 + 绑定扩展 + 版本配置 CRUD） | 5 | V3 | agent-requires-template, editable-agent-templates, agents-templates-subtabs, expand-agent-bindings, expose-agent-version-config-crud, split-agent-templates-tab |
| 用户管理 + IM 工作台（身份统一） | 3 | V3 | user-management, im-gateway-management, unify-user-im-identity-admin-ui |
| Chat 管理（试运行 playground + 会话） | 3 | V3 | chat-management |
| Connector 管理（OAuth + MCP 状态） | 3 | V3 | connector-management, add-im-platform-connections |
| 知识库管理面 | 2 | V3 | knowledge-base-management |
| Model provider 管理面 | 2 | V3 | model-provider-management |
| Agent 统计面板 | 3 | V3 | agent-statistics-panel |
| 资源监控与告警面 | 3 | V3 | resource-monitoring-alerting |
| Askit 编排 console | 2 | V3 | askit-orchestration-console |
| Console UX 重构与整合（导航/模块统一/模板编辑器） | 3 | V3 | redesign-admin-console-ux, add-admin-console-modules, unify-legacy-console-modules, 等 UX 迭代 |

### E12 · User Center & Platform — 张亮
| Story | SP | Ver | 覆盖 change |
|-------|----|----|-----------|
| IM connector 合并进 IM users | 2 | V3 | merge-im-connectors-into-im-users, merge-im-connectors-ui-into-im-users |
| 自动生成 resource id | 1 | V3 | autogen-resource-ids |

## 常乐的 Epic

### E13 · Memory 记忆 — 常乐
| Story | SP | Ver | 覆盖 change |
|-------|----|----|-----------|
| SQLite 语义记忆存储 + 提取评估 | 3 | V2 | memory-sqlite-semantic-store, memory-extraction-evaluation |
| 记忆更新/合并动作 | 2 | V2 | memory-update-merge-actions |
| Memory + KB 真实 embedding 评估 | 3 | V2 | memory-and-kb-real-embedding-evaluation |
| 记忆保留与压实（retention/compaction） | 2 | V2 | memory-retention-and-compaction |
| Reflection 维护 proposal 接入 | 2 | V2 | memory-reflection-maintenance |
| Shared Memory + 质量趋势汇总 | 3 | V3 | shared-memory, memory-quality-trend-summary |

### E14 · Long-term Context — 常乐
| Story | SP | Ver | 覆盖 change |
|-------|----|----|-----------|
| 长期上下文 foundation（build_context API） | 3 | V2 | long-term-context-foundation |
| Token budget policy + 评估基线 | 3 | V2 | long-term-context-budget-policy, long-term-context-evaluation |
| Agent/租户级 context policy | 2 | V3 | long-term-context-agent-tenant-policy |

### E15 · Reflection — 常乐
| Story | SP | Ver | 覆盖 change |
|-------|----|----|-----------|
| Reflection foundation + 报告评估 | 3 | V2 | reflection-foundation, reflection-report-evaluation |
| 知识库反思报告 + Skill 提案 + 趋势汇总 | 3 | V3 | reflection-knowledge-base-reports, skill-reflection-proposals, reflection-trend-summary |

### E16 · Knowledge Base — 常乐
| Story | SP | Ver | 覆盖 change |
|-------|----|----|-----------|
| KB core（导入/chunking/vector search/delete） | 5 | V2 | knowledge-base-core |
| 基础文档解析器（text/md/html/pdf/docx/pptx/xlsx） | 3 | V2 | knowledge-base-parsers-basic |
| 本地目录 connector | 2 | V2 | knowledge-base-connectors-local |
| Hybrid search（FTS5/BM25 + RRF） | 3 | V2 | knowledge-base-hybrid-search |
| 检索评估基线 | 2 | V2 | knowledge-base-retrieval-evaluation |
| Google Drive + Confluence connector | 5 | V2 | knowledge-base-connectors-google-drive, -confluence |
| 同步 planner（dry-run/new/changed/archive） | 3 | V2 | knowledge-base-sync-planner |
| Agent-KB 绑定 + connector 运维 CLI | 3 | V3 | knowledge-base-agent-kb-binding, knowledge-base-connector-operations |
| 实体关系提取 + graph search | 3 | V3 | knowledge-base-entity-relation-extraction, knowledge-base-graph-search |
| 高级文档解析 + query planner | 3 | V3 | knowledge-base-file-parsers-advanced, knowledge-base-query-planner |
| Rerank 接入 KB search | 2 | V3 | rerank-kb-search-integration |
| KB connector 真实 HTTP client + smoke status | 3 | V4 | real-kb-connector-http-clients, kb-connector-smoke-status |

### E17 · Vector Store — 常乐
| Story | SP | Ver | 覆盖 change |
|-------|----|----|-----------|
| Vector store foundation + SQLite backend | 3 | V2 | vector-store-foundation, vector-store-sqlite-backend |
| Embedding/rerank provider 抽象 | 3 | V2 | embedding-rerank-provider-abstraction |
| Reindex jobs + provider backoff | 3 | V2 | vector-store-reindex-jobs, vector-reindex-provider-backoff |
| Vector provider 环境变量配置 | 1 | V4 | env-config-vector-providers |

### E18 · Observability & Diagnostics — 常乐
| Story | SP | Ver | 覆盖 change |
|-------|----|----|-----------|
| 结构化日志 | 2 | V2 | observability-structured-logging |
| SQLite agent traces + 契约测试 | 3 | V2 | observability-sqlite-agent-traces, observability-contract-tests |
| Usage + performance summary | 3 | V2 | observability-usage-summary, observability-performance-summary |
| Source attribution + runtime event coverage | 2 | V2 | observability-source-attribution, observability-runtime-event-coverage |
| Admin query API | 2 | V3 | observability-admin-query-api |
| Diagnostics 脱敏导出加固 + retention 策略 | 3 | V3 | diagnostics-redaction-export-hardening, data-retention-and-diagnostics-policy |

### E19 · Deployment & Config — 常乐
| Story | SP | Ver | 覆盖 change |
|-------|----|----|-----------|
| 配置 foundation（pydantic-settings 多环境） | 3 | V2 | configuration-foundation |
| 升级与备份脚本 | 3 | V2 | deployment-upgrade-and-backup |
| Docker Compose foundation | 2 | V3 | deployment-docker-compose-foundation |
| 生产配置校验 | 2 | V3 | production-config-validation |
| 可配置 data home + 单 agent config 文件 | 3 | V4 | configurable-data-home, single-agent-config-file, config-dir-single-agent-yaml, file-driven-agent-config |
| Install 脚本 + seed agent.yaml | 3 | V4 | install-script, installer-seed-agent-yaml |
| Intelligence agent.yaml 配置 | 2 | V4 | agent-yaml-intelligence-config |
| 手动维护入口 | 1 | V3 | manual-maintenance-entrypoints |

### E20 · Pilot 就绪与验收 — 常乐（横向）
| Story | SP | Ver | 覆盖 change |
|-------|----|----|-----------|
| Pilot 安装清单 + 验收指南 | 3 | V3 | deployment-pilot-install-checklist, pilot-acceptance-guide |
| Pilot 能力验证套件 + 验证门 | 3 | V3 | pilot-capability-verification-suite, pilot-verification-gate |
| Pilot 就绪保障修复 | 2 | V3 | pilot-readiness-safeguard-fixes |
| Intelligence 生产校验就绪 | 2 | V4 | intelligence-production-validation-readiness |

---

# 待办部分（TO DO / IN PROGRESS）— V5 Pilot Go 收口

> 这部分严格按规范拆（Story 1-5，每 Epic < 13）。三个 Epic 对应 pilot-readiness-roadmap 的剩余横向项。

### E21 · Runtime/Tooling 横向复核与加固 — 张洋（10 SP）
| Story | SP | Pri | 状态 | 验收要点 |
|-------|----|----|-----|---------|
| agent 执行链路 + 工具 dispatch 端到端稳定性复核 | 3 | High | TO DO | 关键路径有 trace；异常不崩 run |
| MCP 健康/重连/降级路径复核 | 2 | High | TO DO | server 掉线安全降级；gap 分类 |
| Sandbox 降级与隔离边界复核 | 2 | Medium | TO DO | 不可用时降级明确；无 No-Go 级泄漏 |
| run_stream opt-in 流式审批门控落地 | 3 | Medium | IN PROGRESS | 现有 TDD tasks 转绿；SSE /chat 零影响（openspec: streaming-approval-gating） |

### E22 · Platform/Governance/Channels 横向复核 — 张亮（7 SP）
| Story | SP | Pri | 状态 | 验收要点 |
|-------|----|----|-----|---------|
| Slack + Telegram 链路 + DM/群聊权限边界 + allowlist 复核 | 3 | High | TO DO | 收发通过；非 allowlist 被拒；群内隔离 |
| Webhook + scheduler 可用性 + 签名/触发边界复核 | 2 | Medium | TO DO | HMAC 生效；session 绑定语义正确 |
| Governance / permission gate 权限边界复核 | 2 | High | TO DO | 高风险拦截审批；越权工具被拒 |

### E23 · 准生产演练 + Pilot 验收上线 = AAA-7748 — 常乐（8 SP，上线锚定）
| Story | SP | Pri | 状态 | 验收要点 |
|-------|----|----|-----|---------|
| 准生产 Docker 安装/升级/备份/恢复演练 | 3 | High | TO DO | 全流程跑通；restore drill 证明可恢复 |
| 真实外部依赖 smoke 目标环境 opt-in 复跑 | 2 | Medium | TO DO | 各项 passed/skipped，附凭证注入方式 |
| 汇总全 roadmap 复核 → 最终 Pilot 验收报告 + Go/No-Go | 3 | High | TO DO | 产出 acceptance report；判定 + 问题分类 |

---

## 汇总

| 区块 | Epic 数 | Story 数（约） | 状态 |
|------|--------|--------------|------|
| 已完成（V1-V4） | 20 | ~67 | DONE |
| 待办（V5 Pilot Go） | 3 | 10 | TO DO/IN PROGRESS |
| **合计** | **23** | **~77** | |

> AAA-7748 → 改名「准生产演练 + Pilot 验收上线」作为 E23（上线锚定 Epic）。
> 全部 23 Epic / ~77 Story 的 Fix versions 统一挂 `AI-Agent 平台-v1.0.0`。

## 被过滤掉的 change（只建 feature，故不回填）

纯重构/架构迁移（~16）：`define-module-boundaries`、`introduce-database-runtime-boundary`、`restructure-*-package`(6)、
`*-package-migration`(3)、`*-shim-cleanup`(2)、`remove-package-migration-shims`、`database-default-path-rename`、
`runtime-package-blueprint`、`admin-cli-module-split`、`source-module-organization-roadmap`、`capability-docs-package-path-sync`。
测试/CI（~6）：`migrate-existing-tests-by-layer`、`test-suite-organization`、`intelligence-unit-test-hardening`、
`clarify-test-layer-boundaries`、`eliminate-unit-db-test-exceptions`、`raise-unit-coverage-to-75`、`bitbucket-ci`。
Roadmap/docs（~3）：`intelligence-capability-roadmap`、`sync-intelligence-capability-status`、`knowledge-bridge-migration-plan`。

> 若你希望这些也留痕，建议单独建一个 **Epic「工程化与重构」** 把它们作为 Task（非 Story）归档，不计入产品 backlog。
