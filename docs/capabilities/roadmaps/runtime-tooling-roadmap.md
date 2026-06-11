# Runtime and tooling roadmap

这份文档跟踪 fleetent 的执行引擎与工具能力簇：Agent Runtime、Model Router、Tools、MCP、Sandbox、Skill 和 Session。它用于汇总这些 capability 的当前完成度、Pilot 风险、后续 OpenSpec 优先级和与其他能力簇的依赖关系。

## 当前结论

**基础执行链路已可用。** HTTP / IM / TUI 请求可以进入 agent loop，完成模型调用、工具调用、session 持久化、部分治理和 trace 写入。

**运行治理仍需持续收敛。** v1.0 执行引擎的大量增强已落地（实施状态以 `openspec/changes/archive/` 为准；历史排期见 [v1.0-roadmap.md](../../records/roadmaps/v1.0-roadmap.md)），但 runtime、tooling、MCP、sandbox、skill、session 的最终生产默认策略仍需要随 Pilot 反馈调整。

**Pilot 风险主要来自端到端链路稳定性。** 真实用户路径会同时穿过 agent loop、model fallback、tool dispatch、approval、MCP / sandbox、session 和 observability。单点能力可用不等于整条执行链路可验收。

## 范围

| 能力域 | 文档 | 负责范围 |
| --- | --- | --- |
| Agent Runtime | [../agent-runtime.md](../agent-runtime.md) | agent loop、termination、cancellation、budget、loop detection、message hygiene |
| Model Router | [../model-router.md](../model-router.md) | Agent-scoped model targets / routes、provider fallback、route override、model params、provider health |
| Tools | [../tools.md](../tools.md) | `@tool` registry、schema、dispatch、guardrails、timeout、result truncation |
| MCP | [../mcp.md](../mcp.md) | stdio / HTTP MCP client、session continuity、health reconnect、degradation、OAuth |
| Sandbox | [../sandbox.md](../sandbox.md) | sandbox enablement、resource limits、secret injection、timeout、cleanup、trace |
| Skill | [../skill.md](../skill.md) | Skill discovery、frontmatter、read-on-demand、hot reload、disable、audit、scoping |
| Session | [../session.md](../session.md) | session persistence、metadata index、TTL / disk maintenance、anti-flap and binding behavior |

## 当前能力地图

| 能力 | 当前状态 | 已有基础 | 当前缺口 | 后续增强 |
| --- | --- | --- | --- | --- |
| Agent Runtime | 部分完成 | `run()` / `run_stream()`、termination、budget、cancellation、loop detection、message hygiene、多模态入口、trace 接线、`streaming-approval-gating`（2026-06-10 落地）、审批挂起-恢复（approval-suspend-resume） | 全链路 E2E 稳定性、复杂 tool-use 场景回归 | 更细粒度 stop reason、parallel dispatch 体验、成本感知默认策略 |
| Model Router | 部分完成 | Agent `models.targets` / `models.routes`、OpenAI-compatible provider、fallback、route override、provider health cache、参数配置 | 真实 provider smoke、Agent-scoped model config 文档和生产默认值 | 成本感知路由、provider dashboard、route policy UI |
| Tools / MCP | 部分完成 | 内置工具、MCP HTTP / stdio、tool namespace、guardrails、timeout、result truncation、Agent-scoped MCP binding、Agent credential authoring / materialize 注入 | 真实 MCP server smoke、降级策略人工凭证、credential lifecycle / rotation 生产路径 | Tool marketplace、细粒度策略、更多 connector |
| Sandbox | 部分完成 | Docker-based sandbox、enablement、resource limits、secret injection、timeout、orphan cleanup、trace | 生产默认隔离档位、network / read-only 策略确认、宿主环境差异 smoke | 更强隔离后端、artifact 管理、后台清理历史 |
| Skill | 部分完成 | YAML frontmatter、nested scan、conflict handling、read-on-demand、builtin skills、disable、audit、agent scoping、skill proposal 生成→审批→apply 全链路（unify-self-evolution-model，2026-06-11 落地：全树 bundle 写入 + 热更新，update=全树覆盖、deprecate=`enabled:false` 软禁用） | scope 默认策略、真实工作流回归、平台侧 skill 收录整理（Step 2，独立 change） | SkillProposal review UI、自动发布前置审核 |
| Session | 基础完成 | JSON 原子写、metadata index、TTL cleanup、disk management、internal maintenance、scheduled task binding | 长期运行压测、迁移后路径一致性、UI / admin 操作入口 | session dashboard、导出/清理策略 UI |

## Pilot 验收关注点

- 一次 agent run 能稳定完成：request → context assembly → model route → tool dispatch → reply → trace / usage。
- streaming 和 non-streaming 路径在 approval、tool event、error handling、session persistence 上语义一致。
- MCP / sandbox / built-in tools 的失败能被分类、记录、降级或清晰暴露。
- session 持久化不会丢失用户消息、assistant 回复、tool result 或人工接管记录。
- Agent model route / provider / sandbox / skill 配置错误能 fail fast，并给出可行动错误。

## Backlog 骨架

### Pilot blocker 候选

- 真实 agent run 链路无法稳定完成。
- provider fallback 或 tool dispatch 在常见错误下无法恢复或无法记录。
- session 写入、恢复或清理导致数据丢失。
- sandbox / MCP failure 无法诊断或泄露 secret。

### Docs gap 候选

- Agent model route、tool、MCP、sandbox、skill、session 的生产默认配置说明不足。
- failure mode、skip reason、operator action 缺少 runbook。

### Enhancement 候选

- 成本感知路由默认策略。
- Tool / Skill review UI。
- Sandbox artifact 管理和历史记录。
- Runtime dashboard。

## 维护规则

- Agent runtime / model-router / tools / MCP / sandbox / skill / session 的跨能力改动完成后，同步更新本 roadmap。
- 单 capability 的细节仍写在对应 capability 文档；本文件只维护能力簇状态、依赖和 Pilot 风险。
- v1.0 执行计划的历史排期保留在 [v1.0-roadmap.md](../../records/roadmaps/v1.0-roadmap.md)，不要把执行过程日志复制到本文件。
