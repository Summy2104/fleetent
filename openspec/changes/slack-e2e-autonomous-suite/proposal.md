## Why

现有 `slack-e2e-test-suite`（Claude Slack MCP 通道 + 写死 yaml catalog + 17 个 frozen coverage tag + LLM 裁判）有三个结构性短板：

1. **文件能力测不了**：经 Claude Slack MCP 收发，而 MCP 无法上传文件，图片/文件场景只能用「预先上传 / 贴 URL」回退，绕过了真实的「用户上传 → agent 处理 → 文件回传」链路。而 fleetent 近期大量新增依赖文件收发的能力（`send_file`、生成图回传、非图文件入站、`generate_image`、`analyze_image` 等约 13 个功能点）**完全没有 e2e 覆盖**。
2. **自主性受限**：测什么、判定标准都写死在 yaml，LLM 不能动态追问、跨场景串联、或自主加测边缘 case。
3. **覆盖缺口**：审批门、cron 调度、上下文压缩、路径安全、whoami、图像生成等约一半黑盒功能点未被任何 e2e 触及。

## What Changes

- 新增一套**全新、独立**的 Slack 黑盒 e2e 测试套件：
  - **Slack Web API helper CLI**：以 user token 模拟真人用户，与被测 agent bot 在指定频道交互；用 Slack Web API **替代 MCP**，从而支持文件上传/下载。
  - **autonomous 驱动方法论 skill**：由 Claude 作为自主大脑，读覆盖清单、自主多轮对话、黑盒判定。
  - **能力覆盖清单 + rubric**：作为可回归的测试目标全集（约 50 个黑盒功能点）。
- **分层调和「自主 vs 可回归」**：核心回归层（rubric 固定、进基线、可比）+ 自主探索层（即兴串联/自主生成、产发现报告、不进基线）。
- 覆盖此前完全缺失的能力：文件双向、审批门全家桶、cron、图像生成、上下文压缩、路径安全等。
- **取代并移除现有 `slack-e2e-test-suite`**：旧套件经 MCP、测不了文件、场景写死、覆盖不全，由本套件全面取代——删除其 skill（`slack-agent-e2e`）、yaml catalog（`tests/e2e/slack_scenarios/`）、catalog validator（`tests/integration/test_slack_scenarios_catalog.py`），并经本 change 的 REMOVED delta 废弃其 spec。
- 不修改任何 `src/fleetent` 生产代码。

## Capabilities

### New Capabilities

- `slack-e2e-api-helper`: Slack Web API 收发 helper CLI 的能力契约——`send`（文本，可附文件上传）/ `read`（轮询读线程，按 `bot_user_id` 过滤新消息）/ `upload` / `download`（文件双向核验）/ `resolve`（验 token、bot、channel）子命令；JSON in/out；user OAuth token；被测 agent / bot user id / channel 运行时显式指定；纯机械收发，无 LLM、无判定。
- `slack-e2e-autonomous-driver`: Claude 自主驱动的可回归测试方法论——能力覆盖清单 + rubric（A 核心黑盒层 / B 需前置配置层 / C 排除项三分组）；核心回归层 vs 自主探索层分层；判定硬信号优先、LLM 裁判兜底；四种自主（路径自主 / 临场探测 / 跨场景串联 / 自主生成探测）；诚实铁律；user token 无法点审批按钮 → text-approve 等交互限制的规避。

### Modified Capabilities

（无现有产品能力的 requirement 被修改。）

### Removed Capabilities

- `slack-e2e-test-suite`: 旧 Slack e2e 套件（MCP 通道 + 写死 yaml catalog + LLM 裁判 + catalog validator）整体废弃；其全部 requirement 由本 change 的 REMOVED delta 移除，能力由 `slack-e2e-api-helper` + `slack-e2e-autonomous-driver` 取代。

## Impact

- **新增产物（均非生产代码）**：
  - `tests/e2e/slack_autonomous/`：helper CLI（Python + Slack Web API 客户端）+ 覆盖清单/rubric 数据 + helper 纯函数单测
  - `.claude/skills/slack-e2e-autonomous/`：自主驱动方法论 skill
- **删除产物（旧套件）**：`.claude/skills/slack-agent-e2e/`、`tests/e2e/slack_scenarios/`（17 yaml + README + sample `agent.yaml.example`）、`tests/integration/test_slack_scenarios_catalog.py`；旧 spec `slack-e2e-test-suite` 经 REMOVED delta 于 archive 时移除。无活跃外部引用（仅 `docs/archive/jira-backfill-plan.md` 历史文档提及，保留原貌）。
- **依赖**：新增 dev 依赖 `slack_sdk`（self-hostable 纯 HTTP 客户端，符合数据主权原则）；若复用现有 `httpx` 则零新增，留待 design 定。
- **模块边界**：owning = `tests/e2e` + `.claude/skills`；public API surface = 无（纯测试工具，不被任何生产模块 import）；owned tables = 无；config namespace = 无（helper 用 `SLACK_E2E_*` 环境变量）；cross-module deps = 无生产依赖，**不触碰 agent/platform 解耦契约**；migration/shim = 无。
- **零影响**：`src/fleetent` 生产代码不改；无新增/修改持久化表。
- **运行前提**（运行时由用户显式提供，缺失则报「阻塞」不伪造）：fleetent server 跑着被测 agent、bot 在指定频道、user OAuth token（`xoxp-` + `chat:write` / `files:write` / `*:history` / `users:read` scope）、测试用户在 agent allowlist 内。
- **不进 CI 门禁**：大脑是会话内的 Claude，本地驱动反复跑、结果稳定可比、出报告；现有 e2e 本就默认不进 PR 门禁。
