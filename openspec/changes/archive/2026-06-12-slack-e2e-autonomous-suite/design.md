## Context

现有 `slack-e2e-test-suite` 经 Claude Slack MCP 收发、用写死的 yaml catalog + LLM 裁判，存在三短板：MCP 无法上传文件（文件类能力测不了，而 fleetent 近期新增约 13 个依赖文件收发的功能点完全无 e2e 覆盖）、场景与判定写死（LLM 无法动态追问/串联/加测）、约一半黑盒功能点未覆盖（审批门、cron、压缩、路径安全等）。

本设计在不碰生产代码的前提下，新建一套 Slack Web API 驱动、Claude 自主、可回归的黑盒 e2e 套件，并**移除被它取代的旧 `slack-e2e-test-suite`**（skill + yaml catalog + validator + spec）。约束：数据主权（组件须 self-hostable）、agent/platform 解耦不可逆、不进 PR 门禁（沿用现有 e2e 惯例）、绝不伪造结果。

## Goals / Non-Goals

**Goals:**
- 用 Slack Web API 实现**真实文件收发**（上传给 agent、下载 agent 回传文件核验）链路的 e2e。
- 让 Claude 作为自主大脑，在固定覆盖清单 + rubric 上**自主对话**并**黑盒判定**，结果可回归对比。
- 覆盖约 50 个黑盒功能点，重点补齐文件双向、审批门、cron、图像生成、上下文压缩、路径安全等缺口。
- 严守诚实铁律：无真实回复不判 pass、缺前置报阻塞。
- **以本套件取代并移除旧 `slack-e2e-test-suite`**，避免双轨维护。

**Non-Goals:**
- 不做 CI 无人值守自动跑（大脑是会话内的 Claude）。
- 不改任何 `src/fleetent` 生产代码、不新增持久化表。
- 不测黑盒不可观测项（反思报告生成、session 生命周期 hook 内部埋点）。

## Decisions

### D1：Slack Web API 替代 MCP 通道
helper 直接调 Slack Web API 而非经 Claude Slack MCP。**理由**：MCP 无法上传文件，而文件收发是本套件的核心增量价值。**备选**：继续用 MCP —— 否决，测不了文件，等于复制旧套件的短板。

### D2：Claude 作大脑、helper 作手脚（无 LLM 的纯收发工具）
判定与决策全部在会话内的 Claude；helper 只做 Slack API 机械收发，无 LLM、无 verdict。**理由**：最大化「发挥会话内大模型自主」，工程量最小，文件问题由 helper 用 API 解决。**备选**：独立程序内置 LLM 全自动跑 —— 否决，需接 LLM provider、自主性受程序编排限制、增数据主权/成本负担。**保留演进空间**：helper 接口设计为可被未来独立程序复用。

### D3：分层调和「自主 vs 可回归」
核心回归层（路径自主 + 临场探测，判定锚在固定 rubric，进 pass/fail 基线）与自主探索层（跨场景串联 + 自主生成探测，产发现报告，不进基线）分离。**理由**：覆盖清单 + rubric 固定 ⇒ 可回归；LLM 每点内自由展开 + 即兴探索 ⇒ 自主；不确定性隔离在探索层。**备选**：纯写死 yaml（旧套件，不自主）/ 纯自由探索（不可回归）—— 均否决。

### D4：判定硬信号优先，LLM 裁判兜底
rubric 尽量写成可观测断言（附件出现且下载内容含 X、回复含正确数值、审批请求出现且审批后续行），仅在无硬信号时用 LLM 语义裁判并要求引用决定性片段、存疑判 fail。**理由**：硬信号比语义稳定，直接治旧套件「LLM 裁判 flaky」。文件收发恰好提供大量硬信号。

### D5：user OAuth token（`xoxp-`）以「用户身份」交互
以 user token 模拟真人发消息，被测 agent bot（指定 `bot_user_id`）回复。**理由**：用户要求「以我的身份」；user token 还能下载 bot 的 `url_private_download` 私有文件用于核验。**备选**：专用测试 bot token —— 否决，bot↔bot 对话需额外配置且不符「我的身份」诉求。所需 scope：`chat:write`/`files:write`/`channels:history`(+groups/im/mpim)/`users:read`。

### D6：text-approve 规避审批按钮点击限制
user token 无法经 API 触发审批 interactive button 的 webhook，故审批门用文本审批途径完成（仓库 `fix/text-approve-session-lookup` 佐证 agent 支持线程内文字批准）。**备选**：伪造 Slack 交互 webhook（签名/payload）—— 否决，复杂且脆弱。进度指示/取消按钮同类限制 → 标注「可观测性待验证」，apply 时验证或降级跳过。

### D7：落点与模块边界
- owning：`tests/e2e/slack_autonomous/`（helper + 覆盖清单/rubric + 纯函数单测）、`.claude/skills/slack-e2e-autonomous/`（方法论 skill）。
- public API surface：无（纯测试工具，不被任何生产模块 import）。owned tables：无。config namespace：无（`SLACK_E2E_*` 环境变量）。
- cross-module deps：无生产依赖；**不触碰 agent/platform 解耦**（测试工具不属 agent runtime）。migration/shim：无。

### D8：Slack 客户端选型（slack_sdk vs httpx）
倾向 `slack_sdk`（封装 external upload 多步流程，self-hostable 纯 HTTP 客户端，符合数据主权）；若决定零新增依赖则用项目已有 `httpx` 手写三步上传。apply 起步时定，记于 Open Questions。

### D9：以 REMOVED delta 正规废弃旧套件
旧 `slack-e2e-test-suite` 经本 change 的 `specs/slack-e2e-test-suite/spec.md` REMOVED delta 废弃其全部 requirement，archive 时同步移除主 spec；其实现物（skill / yaml catalog / validator）在功能分支上删除。**理由**：保持 OpenSpec 契约一致，避免手删 specs 造成无记录空洞。**备选**：裸 `rm` —— 否决，破坏契约一致性、archive/validate 会不一致。

## Risks / Trade-offs

- **LLM 裁判仍有语义波动** → 硬信号优先（D4）+ 引用决定性证据 + 存疑判 fail；语义判定仅作兜底。
- **需会话内 Claude 在场，不能无人值守** → 这是 D2 的自觉取舍；helper 接口可复用，保留未来自动化空间；本就不进 CI 门禁。
- **真实 Slack / server / token 环境依赖** → `resolve` 子命令前置校验（token/bot/channel/scope），缺失报「阻塞」不伪造（诚实铁律）。
- **跨场景串联引入状态依赖、难复现** → 隔离在自主探索层，不进核心基线。
- **B 层能力（KB 摄入、热重载、多租户）需特殊部署/admin 操作** → 标注前置，缺失则跳过并报阻塞，不强求覆盖。
- **大文件 / 下载失败等降级路径** → 作为独立能力点测试其降级提示本身（占位提示是可观测硬信号）。
- **删除旧套件丢失轻量 CI validator** → 旧 catalog validator 随 yaml 一并废弃；新套件覆盖清单的结构校验由 driver 的清单校验 requirement + 其 unit 测试承接（仍进常规测试套件）。

## Migration Plan

纯测试侧变更，无数据迁移。部署 = 安装 dev 依赖（若引入 slack_sdk）+ 用户提供 token/agent/bot/channel。**移除旧套件** = 删除其 skill / yaml catalog / validator 文件 + 经 REMOVED delta 废弃 spec（archive 同步）。回滚 = 还原被删文件并删除新套件目录，对生产与数据零副作用。

## Open Questions

- D8 客户端选型（slack_sdk vs httpx）—— apply 起步时定。
- 进度指示 / 取消按钮经 Slack API 的可观测性 —— apply 时实测确认或降级跳过。
