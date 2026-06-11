## Context

本 change 是"沙箱优先执行"序列的**最后一步**,安全敏感、小而可审计。它**不引入任何新机制**,只把前序已就位的能力做成"兑现 + 收紧 + 文档":

- **免审批机制已就位**(核实):`agent_config.py:332` 已有 `action_gate_medium_mode: Literal["direct","sandbox","approval"] = "approval"`;`governance/action_gate.py` 的 `resolve_action_mode` 已能把 `medium_mode="sandbox"` 解析为 `ActionMode.SANDBOX`,并在 `sandbox_capable=False` 时 fail-closed 升 `APPROVAL`(`action_gate.py:79`);`runtime/loop.py:742-748` 已在 gate 调用点喂入 `medium_mode` 与 `sandbox_capable`。地基 `sandbox-containment-gating` 已让 `sandbox_capable` 反映运行时封闭性。**缺的只是部署侧默认仍配 `approval`、以及缺文档**——本 change 补"封闭即免审批"的推荐默认与文档。
- **`bash_exec` 默认暴露**(核实):`governance/agent_policy.py:check_tool_access` 是对 `allowed_tools` 的纯 fnmatch;`tools/registry.py:get_schemas()` 不按 `allowed_tools` 过滤(它管 availability/MCP 可见性),`allowed_tools` 过滤在 loop 的 schema 组装与 dispatch 两处经 `check_tool_access` 生效;`tool-access-control` 既有契约是"空 `allowed_tools` → `None` → 放行全部"。故普通 agent 默认能看到 `bash_exec`(`tools/shell_tool.py`,risk=high,宿主直跑)。本 change 让其 opt-in。
- **mode 三态已就位**(核实):`sandbox-enablement-control` 已有 `off`/`selective`/`all`(默认 `all`)与 `available()` 降级。本 change 仅补选型指引文档。

## Goals / Non-Goals

**Goals:**
- 兑现"盒子封闭 → medium 免审批":提供推荐默认与文档,使部署把 `action_gate_medium_mode` 配 `sandbox` 即对**已封闭**的 medium 操作免审批;未封闭仍 fail-closed 升审批。
- 收紧默认暴露面:`bash_exec` 成为 opt-in,普通(空 allow-all)agent 默认不含,运维 agent 显式列出才得。
- 给部署者 mode 选型指引文档,与免审批配套。

**Non-Goals:**
- 不改 registry risk 常量、不改 `resolve_action_mode` / `is_sandbox_backed` / `SANDBOX_BACKED_TOOLS`(全复用)。
- 不碰 `builtin-shell-tool`:`bash_exec` 自身执行/审批/超时/工作目录契约不变(本 change 只改它**是否默认出现在普通 agent 工具面**)。
- 不改 `sandbox-enablement-control` 三态语义与 `available()` 降级行为(只加选型指引文档)。
- 不碰地基(workspace 命名/碰撞、containment 派生)、scope-split(scope 粒度/镜像)、执行世界(执行面收敛/run_code 唯一执行面)——跨 change 所有权红线。
- 不新增 agent.yaml 治理字段(`action_gate_medium_mode` 已存在)。
- 不强制翻默认免审批:免审批是部署的显式选择(把 medium_mode 配 `sandbox`),存量配 `approval` 行为不变。

## Decisions

### D1:免审批兑现 = 推荐默认 + 文档,机制零改动
不动 `action_gate.py` / `loop.py:742-748`——机制完全就位且正确(fail-closed 已在,地基 containment 已喂真值)。本 change 的"兑现"落在:
1. `agents/default/agent.yaml.example` 把 `action_gate_medium_mode` 的注释从"approval=默认"扩成"封闭可信部署推荐 `sandbox`:容器内 medium 操作免审批,未封闭自动升审批";`action_gate_high_mode` 注释明确"高危默认保持 approval,不随 medium 放松"。
2. `docs/capabilities/governance.md` 补"封闭即免审批"说明:正当性绑运行时封闭性、未封闭 fail-closed。
- spec 侧用 `approval-minimization` 新增 requirement 锁定"配 `sandbox` + 封闭 → 直跑不审批 / 未封闭 → 升审批 / high 不随放松",这些**都是既有 resolver + 地基 containment 已保证的行为**,本 change 只是声明并文档化兑现路径。
- **备选**:把 `action_gate_medium_mode` 的代码默认从 `approval` 改为 `sandbox` → **否决**。会让所有未显式配置的存量 agent 静默改变审批行为(安全敏感的隐式放松),违背"小而可审计、显式选择"。保留代码默认 `approval`,推荐取值经文档/示例传达。
- **备选**:新增"一键封闭部署"宏配置 → 否决,增面、非本 change 必需。

### D2:`bash_exec` opt-in —— 在工具面解析层剔除"空 allow-all 隐式集合"
让 `bash_exec` 不随"空 `allowed_tools`(allow-all)/ `*`"隐式暴露;仅当 `allowed_tools` **显式具名命中**(字面 `bash_exec` 或能覆盖它的显式模式)才暴露。实现锚定在**工具面解析层**(loop 的 schema 组装 + dispatch 的 `check_tool_access` 同一逻辑源),而非改 `bash_exec` 执行体:
- 维护一个 **opt-in 工具集合**(初始 `{"bash_exec"}`,内聚在 governance/tools 工具面解析处,可注入便于测试)。
- "空 allow-all → None"语义保留(loop 仍收 `None`);opt-in 剔除在"判断某工具是否对该 agent 可见"处生效:`allowed_tools` 为 `None`(allow-all)或 `["*"]` 时,opt-in 工具判为不可见;`allowed_tools` 显式含命中模式时可见。
- 与既有 `availability`(`tool-availability`)正交:availability 管"运行时条件是否满足"(全局),opt-in 管"该 agent 是否显式授予"(per-agent)。不复用 availability(它无 per-agent allowed_tools 上下文)。
- **备选 A**:给 `@tool` 加 `opt_in=True` 标志,在 `get_schemas()` 按全局规则隐藏 → 否决,`get_schemas()` 无 per-agent `allowed_tools` 上下文,无法表达"运维 agent 显式列出则可见"。
- **备选 B**:把 `bash_exec` 从注册表移除、改默认不注册 → 否决,运维 agent 仍需用它,移除等于砍能力;且违背"工具面是视图过滤、注册表保留"(`tool-availability` 既有原则)。
- **选定**:opt-in 集合 + 在 per-agent 工具面解析(`check_tool_access` 调用上下文 / loop schema 组装)处对 allow-all 收窄。改动小、可审计、保留运维 agent 显式获得路径。具体落点(扩展 `check_tool_access` 签名加可选 opt-in 集合,还是在其调用方过滤)实现期定,以 unit 锁定行为。

### D3:mode 选型指引为纯文档 requirement
`sandbox-enablement-control` 新增 requirement 为"指引/文档"性质,scenario 断言"指引推荐 X"与"指引不改变语义/降级",不触碰三态判定纯函数与 `available()`。文档落 `docs/capabilities/governance.md`(或部署文档)与 example 配置注释。
- **备选**:把推荐 mode 写成代码默认变更 → 否决,默认已是 `all`(`sandbox-enablement-control` 既有),且选型因部署而异,属指引非强制。

## Risks / Trade-offs

- **存量"空 allow-all 且隐式依赖 `bash_exec`"的 agent 失去该工具** → 属安全收紧(预期)。迁移路径:在其 `allowed_tools` 显式补 `bash_exec`;文档与 CHANGELOG 明确说明。显式列出 `bash_exec` 的运维 agent **不受影响**。
- **免审批兑现被误解为"全局自动放松"** → spec 与文档强调:仅对**运行时封闭**的 **medium** 操作、且部署**显式**把 medium_mode 配 `sandbox` 才生效;high 不随放松;未封闭 fail-closed 升审批。
- **opt-in 集合落点若选错层导致 dispatch 与 schema 不一致**(schema 隐藏但 dispatch 仍放行,或反之)→ 锚定在 `check_tool_access` 的同一逻辑源,unit 同时覆盖 schema 可见性与 dispatch 放行,保证两处一致。
- **`*` 通配的预期**:用户可能以为 `["*"]` 该包含一切。trade-off:为安全,`*` 不隐式授予 opt-in(与空 allow-all 同);文档明示"opt-in 工具须具名"。这与 `agent-definition` 的 `allowed_tools` 通配语义不冲突(那是 MCP 通配,opt-in 是对宿主高危工具的额外门控)。
- **依赖排序**:免审批兑现若先于地基 containment / scope-split / 执行世界落地,会在"盒子未真封闭/会串台/执行面不唯一"时放松审批——故本 change 排在序列**最后**,proposal/Impact 明列排序依赖。

## Migration Plan

- 无 DB 迁移、无模块迁移、无 shim。
- `action_gate_medium_mode` 字段与代码默认(`approval`)不变:免审批是部署 opt-in,存量行为默认不变。
- `bash_exec` opt-in:存量显式列出者不受影响;空 allow-all 隐式依赖者需在 `allowed_tools` 补 `bash_exec`——文档/CHANGELOG 说明,属一次性配置动作。
- Rollback:回滚代码即可。回滚后 `bash_exec` 恢复随 allow-all 暴露、免审批文档失效(机制仍在但回到推荐 `approval`);因本 change 不改机制,回滚不影响地基与执行世界。

## Open Questions

- opt-in 集合的承载形态与落点:扩展 `check_tool_access(tool, allowed_tools, *, opt_in_tools=...)` 还是在其调用方(loop schema 组装 / dispatch 前)统一过滤——实现期定,以 unit 锁定"空 allow-all/`*` 不含、显式命中含"且 schema 与 dispatch 一致。
- 是否需要让 opt-in 集合可经配置扩展(未来其他宿主高危工具)→ 倾向先硬编码 `{"bash_exec"}` 内聚一处、留扩展点,不在本 change 引入配置面。
- `action_gate_medium_mode: sandbox` 的推荐文档放 `governance.md` 还是独立部署 hardening 文档 → 实现期定,以"部署者能一处读到封闭即免审批 + mode 选型"为准。
