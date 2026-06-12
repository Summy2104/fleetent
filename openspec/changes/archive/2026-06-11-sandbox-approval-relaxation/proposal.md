## Why

"沙箱优先执行"序列的**最后一步、安全敏感、小而可审计**:在地基与执行世界都落地后,把"盒子封闭 → 免审批"这一兑现做实,并堵住默认部署仍暴露的宿主直跑面。

1. **免审批尚未兑现**:`action-gate` 早已支持把 medium 操作的处置 mode 配为 `sandbox`(`action_gate_medium_mode` ∈ `{direct, sandbox, approval}`,`resolve_action_mode` 已能解析),地基的 `sandbox-containment-gating` 也已让 `sandbox_capable` 反映运行时封闭性(`effective_mode != OFF` 且容器内执行才为真,否则 fail-closed 升 APPROVAL)。但**部署侧默认仍是 `action_gate_medium_mode: approval`**——封闭的容器内 medium 操作仍逐次打扰审批人,沙箱隔离换来的"无打扰自动化"没有兑现。本 change **不改 risk 常量、不改 `resolve_action_mode` 契约**,只把"对已封闭的 medium 操作配 `sandbox` 即免审批"做成**有据可依的推荐默认 + 启用路径 + 文档**。

2. **普通 agent 默认仍可见 `bash_exec`**:`tool-access-control` 既有契约是"`allowed_tools` 空 = 放行全部已注册工具"(空列表 → 运行时收 `allowed_tools=None` → `check_tool_access` 不过滤)。这意味着一个**未显式收窄工具面的普通 agent 默认就能看到并调用 `bash_exec`**——宿主机直接执行任意 Shell 命令(`tools/shell_tool.py`,risk=high,非沙箱)。这与"模型默认只在封闭盒子里干活、宿主直跑是运维专属高危能力"的世界观相悖:免审批一旦对 medium 兑现,普通 agent 仍能用一个 high 工具触达宿主。本 change 让 `bash_exec` 成为**opt-in**:普通 agent 默认工具面**不含** `bash_exec`,运维 agent 必须在 `allowed_tools` 中**显式列出**(字面名或可覆盖它的具名模式)才获得。

3. **部署者缺少 sandbox mode 的选型指引**:`sandbox-enablement-control` 已有全局三态 `mode`(`off`/`selective`/`all`),但"哪种部署形态选哪个 mode、与免审批如何配套"无文档。本 change 补**推荐选型指引**(文档化,不改三态语义、不改降级行为)。

> **排序依赖(MUST)**:免审批兑现**不得早于**以下三者落地——`sandbox-isolation-foundation`(containment 门控:无 docker = fail-closed 升审批)、`sandbox-workspace-scope-split`(session 安全默认:工作区按主体隔离不串台)、`sandbox-execution-world`(执行面收敛:run_code 为容器内唯一执行面)。三者保证"盒子真封闭、不串台、执行面唯一",免审批的正当性才成立。本 change 排在它们之后,且**只做配置默认 / 启用 / 文档**,不引入任何新机制。

## What Changes

- **免审批兑现(配置默认 + 启用路径 + 文档)**:把"对已封闭(`sandbox_capable=True`)的 medium 操作配 `action_gate_medium_mode: sandbox` 即免审批"做成**可一键启用的推荐默认与文档**——容器内 medium 操作经地基 `sandbox-containment-gating` 解析为 `SANDBOX` 直跑、不打扰审批;封闭不成立(无 docker / 非容器内)时仍由既有 fail-closed 升 `APPROVAL`。**绝不改** registry risk 常量、**不改** `resolve_action_mode` / `is_sandbox_backed` 契约、**不改** `SANDBOX_BACKED_TOOLS` 集合。`high_mode` 默认保持 `approval`(高危不随 medium 一同放松)。
- **`bash_exec` 默认移除(opt-in 化)**:修改 `tool-access-control` 的"空 `allowed_tools` = 放行全部"语义——`bash_exec` 这类宿主直跑高危工具被划入**默认不随"放行全部"暴露的 opt-in 集合**;`allowed_tools` 为空(allow-all)的普通 agent 工具面**不含** `bash_exec`;只有在 `allowed_tools` 中**显式具名命中**(字面 `bash_exec` 或能覆盖它的显式模式)的 agent 才暴露它。空 allow-all 对其余工具的语义不变。**本 change 不碰 `builtin-shell-tool`**(`bash_exec` 自身的执行/审批/超时契约不变)。
- **sandbox mode 选型文档化**:在 `sandbox-enablement-control` 增补"部署选哪个 mode"的推荐指引 requirement(文档/指引性质:封闭可信内网→`all` + medium 免审批;最小暴露→`selective`;禁用代码执行→`off`),不改三态语义、不改 `available()` 降级行为。

- **本 change 明确不做**:不改 registry risk 常量 / `resolve_action_mode` / `is_sandbox_backed` / `SANDBOX_BACKED_TOOLS`(全复用地基与既有 action-gate 机制);不改 `bash_exec` 自身契约(不碰 `builtin-shell-tool`);不改 `sandbox-enablement-control` 三态语义与降级逻辑;不动 workspace 命名/碰撞(地基所有)、不动 scope 粒度/镜像(scope-split 所有)、不动执行面收敛/run_code 唯一执行面(执行世界所有);不新增 agent.yaml 治理字段(`action_gate_medium_mode` 已存在,仅改部署侧推荐取值与文档)。

## Capabilities

### New Capabilities
无(全部复用既有机制:免审批走地基 `sandbox-containment-gating` + 既有 `action-gate`;mode 走既有 `sandbox-enablement-control`)。

### Modified Capabilities
- `approval-minimization`: 补充"封闭 medium 操作免审批"的兑现要求——部署将 `action_gate_medium_mode` 配为 `sandbox` 时,对运行时封闭(`sandbox_capable=True`)的 medium 操作 SHALL 由 action gate 解析为 `SANDBOX` 直跑、不发审批;封闭不成立时仍 fail-closed 升 `APPROVAL`。复用地基 containment 与既有 action-gate,不改任何 risk 常量与 resolver 契约。
- `tool-access-control`: 修改"空 `allowed_tools` = 放行全部"——`bash_exec`(宿主直跑高危)从"空 allow-all 隐式暴露集合"中剔除,成为 opt-in;普通(空 allow-all)agent 默认不含 `bash_exec`,运维 agent 须显式具名命中才获得。其余工具的 allow-all 语义不变。
- `sandbox-enablement-control`: 新增"部署 mode 推荐选型指引"要求(文档/指引性质),为三态 mode 提供部署形态映射;不改三态语义与降级行为。

## Impact

- **代码**:
  - 免审批兑现:`agents/default/agent.yaml.example`(把 `action_gate_medium_mode` 的注释/推荐取值更新为"封闭部署推荐 `sandbox`";字段已存在);相关文档(`docs/capabilities/governance.md`)补"封闭即免审批"说明。**不改** `governance/action_gate.py`、**不改** `runtime/loop.py:742-748` 的 gate 调用(机制已就位)。
  - `bash_exec` opt-in:`tools/registry.py` `get_schemas()` 的工具面解析 / `governance/agent_policy.py` `check_tool_access`(或其上游 allow-all → None 归一点),让"空 allow-all"不暴露 opt-in 集合中的工具;`tools/shell_tool.py` 标注/登记 `bash_exec` 为 opt-in(机制取决于实现选型,见 design D2)。**不改** `bash_exec` 执行体。
  - mode 选型:文档(`docs/capabilities/governance.md` 或部署文档)补 mode 推荐表;`agents/default/agent.yaml.example` / platform 侧 sandbox 注释补指引。
- **复用而非新建**:免审批路由复用地基 `sandbox-containment-gating`(`sandbox_capable` 已反映封闭性)+ 既有 `action-gate`(`resolve_action_mode` 的 SANDBOX→fail-closed→APPROVAL 契约不变);mode 复用既有 `sandbox-enablement-control` 三态。
- **模块边界声明**:
  - owning package:`tools`(`bash_exec` opt-in 解析落点)、`governance`(allow-all 工具面解析,若涉及)。文档落 `docs/`,配置示例落 `agents/`。
  - public API surface:`tools.registry.get_schemas()`(行为收窄:空 allow-all 不再含 opt-in 工具,签名不变);`governance.agent_policy.check_tool_access`(若需扩展 opt-in 判定,签名尽量不变或新增可注入 opt-in 集合);无新增 dataclass/service interface。
  - owned tables:无(纯配置默认 / 工具面解析 / 文档,不落 DB)。
  - config namespace:无新增(`action_gate_medium_mode` / `action_gate_high_mode` 已在 agent governance;sandbox `mode` 已在 `sandbox-enablement-control`;本 change 只改推荐取值与文档)。
  - cross-module dependencies:`tools` / `governance` 的工具面解析为 agent 运行时内部协作;**不 import `fleetent.platform.*`**,保持 agent/platform 单向解耦;agent 须仍能在无 platform、platform 表不存在环境下 `fleetent agent run`(普通 agent 默认无 `bash_exec`、容器内 medium 按配置直跑或 fail-closed)。
  - migration / shim plan:无模块迁移、无表迁移;`action_gate_medium_mode` 字段不变,存量将其配 `approval` 的 agent 行为不变(免审批是 opt-in 的部署选择,不强制翻默认);存量在 `allowed_tools` 中显式列了 `bash_exec` 的运维 agent **不受影响**(显式命中仍暴露);仅存量"空 allow-all 且依赖隐式获得 `bash_exec`"的 agent 会失去该工具——属安全收紧,迁移路径为在其 `allowed_tools` 显式补 `bash_exec`,文档说明。
- **测试**:
  - unit:`check_tool_access` / `get_schemas` 工具面解析——空 allow-all(`None`)不暴露 `bash_exec`、暴露其余工具;显式 `["bash_exec"]` / 覆盖模式命中则暴露;`resolve_action_mode` 在 `medium_mode="sandbox"` + `sandbox_capable=True` 解析为 `SANDBOX`、`sandbox_capable=False` 升 `APPROVAL`(锁定免审批兑现是既有契约,不改 resolver)。
  - integration:普通 agent(空 allow-all)的 `get_schemas()` 无 `bash_exec`、运维 agent(显式列出)有;配 `action_gate_medium_mode: sandbox` 且运行时封闭时 medium 操作经 gate 直跑不审批、`effective_mode=OFF` 时同一操作升审批(对接地基 containment)。
- **依赖**:基于已合并 main 的 `action-gate`、`approval-minimization`、`tool-access-control`、`sandbox-enablement-control`、`builtin-shell-tool`;**排序依赖(免审批不得早于其落地)**:`sandbox-isolation-foundation`(containment 门控)+ `sandbox-workspace-scope-split`(session 安全默认)+ `sandbox-execution-world`(执行面收敛)。本 change 排在该序列**最后**。
