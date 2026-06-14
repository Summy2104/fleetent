# Design — unified-file-exchange

## Context

fleetent 的文件平面当前分裂为两个互不可见的世界：

- **agent workspace**：host 目录按 scope（session 默认 / agent）键控，挂进沙箱为 `/workspace`；`file_sandbox_io.py` 的围栏（fence）把所有 file 工具（read/write/edit/search/send_file）钉死在这个单根内。
- **MCP server 私有目录**：每个 stdio server 自行决定写哪（XDG 约定、cwd、写死路径），fleetent 仅透传 env，对其位置与产物零感知。例如 google-workspace 经 agent.yaml 手工配置的 `XDG_DATA_HOME` 写入 `agents/<id>/xdg/share/google-workspace-mcp/workspace/`。

实证后果（2026-06-12 事故，Slack my-bot）：google-drive 导出 xlsx 落 MCP 私有目录 → `send_file` 的 fence 拒绝（文件不在 workspace）→ 文件无法投递，模型改发链接并虚报"已完成"；同日早间 deploy_check 测试中模型被迫"在 /workspace 重建文件再发"，同一摩擦两小时两次。模型曾主动传 `localPath="/workspace/outbound/…"`（被 server 拒绝），证明模型直觉就是"一棵树"，缺的是系统供给。

**硬约束**（决定方案空间）：MCP server 是 agent 级长驻进程，一个进程服务所有 session；workspace 默认 per-session。两者生命周期错配 ⇒ 任何"把 server 文件根直接指到 session workspace"的纯配置方案在结构上不成立。第三方 server 不可要求配合（roots/resources 支持参差）。

## Goals / Non-Goals

**Goals:**

- 任何 MCP 工具产出的文件，模型可用**统一路径**直接引用：`send_file` 投递（出站）、`read_file`/`run_code` 消费（进站），零手工搬运。
- 模型零新概念：只有路径，无 artifact id 等第二套引用语义。
- 会话隔离不松动：跨 session 取用工件默认拒绝（host 工具）/物理不可见（容器），仅可经人工审批授权。
- 存量部署零迁移：显式 env 配置原地收编，token 不挪、不重新 OAuth。
- 第三方 server 零感知、零改动。

**Non-Goals:**

- MCP resources 协议读取、MCP server 容器化（future，与本设计正交且可平滑演进）。
- 存量 xdg 树物理搬家（纯 housekeeping）。
- workspace 产物 / 入站 IM 附件纳入台账（统一审计，后续）。
- exchange 配额/TTL 清扫（仅留台账与目录结构钩子）。
- 审批挂起-恢复的会话地址统一、投递回执后置校验（另行 change）。

## Decisions

### D0 归属轴 = workspace scope key（继承 `/workspace`，agent 内不另起隔离轴）

> 本决策为后续所有归属/校验/视图条款的根。2026-06-13 架构审计修正：原设计（旧 D3/D4/D5）以裸 `session_id` 作独立归属轴，与 agent 内既有的**唯一文件隔离轴**矛盾，是"别扭"的根因。

agent 运行时内，对**文件 / sandbox / exchange**只有一条隔离轴：**workspace scope**。其 key 由 `SandboxManager` 解析一次：

- `workspace_scope == SESSION` → key = `session_id`
- `workspace_scope == AGENT` → key = `agent_name`

`/exchange` 工件的归属、访问校验、视图分组**复用同一 scope key**，与 `/workspace` 挂载**同源同 key**——两个挂载一套规则。`resolve_workspace_scope` 已强制「multi_user 时 AGENT→SESSION」（`manager.py`），exchange 复用即白捡多人隔离护栏，无需另写一套。

- **边界澄清（platform ⊥ agent）**：`tenant_id` 是 platform 概念，agent 运行时**不建模、不依赖**（AGENTS.md 单向解耦契约）。`user_id` 在 agent 内只服务 memory 分区与审批路由，**不是文件隔离 key**——多人 agent 下「按用户隔离文件」由 session 隔离自动达成（DM 的 `session_id` 内已含 user）。故归属轴**只有 workspace scope key 一条**。
- **单一 key 派生权威**：抽 `workspace_scope_key(scope, session_id, agent_name)`（或经 `SandboxManager` 暴露），`/workspace` 挂载与 `/exchange` 归属**必须调同一个**，杜绝两处各自推导 scope 导致 split-brain（workspace 按 agent、exchange 按 session）。
- **审计 ≠ 访问**：台账行**仍记录产生该调用的具体 `session_id` + `user_id`**（审计真相），但**可见性/访问分组用 `scope_key`**。两者是不同列、不同用途，旧 D4「归属==当前 session」把二者混为一谈才是冲突源。

- *备选：exchange 维持独立 session 轴（旧设计）*——后果：单人 `workspace_scope: agent` 部署下 `/workspace` 跨 session 可见但 `/exchange` 不可见，两挂载两规则，违背"一棵树"北极星；且与 fence/file tools/sandbox/send_file 既有的 scope-key 归属不一致。否决。

### D1 逻辑命名空间 `/exchange/<server_id>`，映射"有效文件根"——而非物理统一目录

`/exchange/<server_id>` 是 fence 认识的第二个逻辑根，启动 server 时绑定到该 server 的**有效文件根**：未显式配置 → 约定注入的 `<agent_home>/exchange/<server_id>/data`；已显式配置（如 my-bot 的 google-workspace xdg 树）→ 显式值原地收编。

- *备选 A：人工 `file_root` 声明 + diff 扫描*——配置里抄写第三方内部路径，server 升级换布局即静默失效；引入 `artifact:<id>` 第二套引用语义。否决为主机制，降级为顽固 server 的逃生门。
- *备选 B：纯物理收敛（所有根迁入 exchange 树）*——对不可配 server 无效，存量迁移成本（OAuth token 搬家），且对功能零增益（命名空间已抽象位置）。否决。
- *选择理由*：映射是构造性兼容——"迁移"变成不存在的问题；模型视角与 `/workspace` 完全同构。

### D2 发现机制三层：约定注入（确定性）→ 咽喉改写（确定性）→ diff（兜底）

1. **约定注入**：`_subprocess_env` 合并序扩为 `安全白名单 < 约定注入 < 显式 env`，注入 `cwd`+`XDG_DATA/CONFIG/CACHE` 四值指向分区树（`data/` 产物区进命名空间；`config/`、`cache/` 隔离在外，登记噪音源头消除）。
2. **咽喉改写**：所有 MCP 调用经 `integrations/mcp/client.py` 单咽喉；结果文本中位于有效根内的 host 绝对路径做前缀替换 → `/exchange/...` 并登记（精确归因到触发调用的 session）。确定性字符串变换，非启发式嗅探。
3. **调用窗口 diff**：对产物区做调用前后快照对比（path/mtime/size；跳过点文件与 `*.tmp`），登记结果未提及的新文件；per-server `asyncio.Lock` 包住"调用+diff"窗口防并发归因错乱。

- *备选：FS events（watchdog）*——精度更高但引入依赖与常驻 watcher；产物区树规模小、MCP 调用本身重，快照 diff 足够。记为 future 优化。

### D3 台账（artifacts 表）是治理元数据，不是模型接口

`agent_state.db` 嵌入式迁移：v32 建 `artifacts`（已合入 main）`{artifact_id, server_id, rel_path, session_id, user_id, filename, mime, size, created_at}`；**v33 追加 `scope_key` 列**（登记时解析的归属/可见性 key，见 D0）。新平铺模块 `artifact_exchange.py` 仿 `schedule_store.py`（`set_state_db` 注入、named parameters）。台账职责：归属校验、视图构建、审计。模型永远不见 artifact_id。

- **列语义二分**：`scope_key` = 访问/可见性 key（按 D0 解析，SESSION→session_id / AGENT→agent_name）；`session_id` + `user_id` = 产生该工件的具体调用，仅作审计真相，**不参与访问判定**。
- *备选：`artifact:<id>` 作为工具引用语义*——模型需要在路径/id 两套语义间切换，是前两代方案被否的核心原因。

### D4 归属即访问控制，统一在 fence 一处实现

fence 解析 `/exchange` 路径时校验"台账 `scope_key` == 当前 run 的 scope_key"（D0），对**所有** host 侧 file 工具一致生效（不只 send_file）。跨 scope → 拒绝并提示走 `send_im_message`（审批）。多人部署 scope 被强制为 session，隔离不因 exchange 是 agent 级物理目录而倒退。

- **查找按 scope_key 过滤，非按路径取最新**：`resolve` 必须查 `(server_id, rel_path, scope_key)` 命中当前 run 归属的行，而非「按路径取最新行再校验」——后者在两 run 同 rel_path 时会取到他人最新行、误判越权（已合入 v32 休眠代码的 `_find_by_path` 缺陷，本期修正）。
- **唯一跨 scope 豁免 = 已过审批**：`resolve(path, scope_key, *, approved=False)`，`approved=True`（send_file 升级审批 / send_im_message files，人批即授权）才跳过 scope 校验。审批旁路应记审计（谁、批了哪个工件）。

### D5 沙箱消费用"归属视图 + ro 挂载"，不是 staging 复制

工件登记时向归属 scope 的视图目录 `<agent_home>/exchange/.views/<scope_key>/<server_id>/…` 补硬链接（`scope_key` 按 D0，SESSION→session_id / AGENT→agent_name）；容器创建时第二卷 `视图目录 → /exchange:ro`。容器消费侧用 `scope_key` 取视图目录，与 `/workspace` 同 key——同一 run 的两个挂载视图一致。

- bind mount 挂目录 ⇒ 挂载后新增硬链接容器内实时可见（容器先建、文件后到成立）；
- 容器内外 `/exchange/...` 路径一字不差，动态拼路径的代码天然工作（任何"预扫描代码提取路径再复制"的方案做不到）;
- ro ⇒ 产物只能落 `/workspace`，输出契约自动成立；
- 归属过滤在 host 侧视图构建时完成 ⇒ 容器跨 session 物理不可见。

降级：`BackendCapabilities` 新增 `exchange_mount` 能力位；无能力后端（如 microsandbox 视实现而定）退化为 exec 前按代码中 `/exchange/…` 引用做归属校验后 staging 复制，行为可见不静默——复用既有能力门控模式，不用 isinstance。

- *备选：exchange 整树 ro 挂载 + 容器内过滤*——mount 全有全无，容器内无法按 session 过滤，隔离倒退。否决。

### D6 工具不合并：两个表面、一个内核

`send_file`（无收件人参数 ⇒ 结构上不可能发错人 ⇒ 免审批快速通道）与 `send_im_message`（收件人模型填 ⇒ 恒 medium 审批）保留各自意图表面，底层共享同一执行内核（归属校验 + outbound 原语）。

- `send_file` 风险参数化：免审批四条件（回当前会话 / DM / 文件全为本 run scope 归属（其 `scope_key` == 当前 run scope_key，含 workspace 相对路径与 `/exchange` 工件）/ 交互上下文）全满足 → 直发；任一不满足 → **升级 medium 审批**取代现行"拒绝"——所有死路变成"最坏多点一次同意"。归属以 scope_key 表达后，单人 `workspace_scope: agent` 部署下 agent 级工件对该 run 即"本 scope 归属"，不再因 `scope != session` 被一刀拒绝（与 `/workspace` 一致）。
- `send_im_message` 新增可选 `files` 参数（跨会话工件、显式目标的文件投递经此，人批即跨会话授权）。
- *备选：合并为单一 `send_message(to=?)`*——评估否决：收件人变可选参数后安全从"结构保证"降为"分类器保证"（单点 bug = 静默免审批）；实证显示模型爱填可选参数（事故中主动填 target=发起人），会把免审批流误升级；"send_im_message 必审批"审计不变量被稀释；allow-always 指纹/skill/prompt 迁移面大。合并声称的好处（共享内核、升级式降级、附件能力）全部不依赖合并。

### D7 权限门 `risk_level` 支持 callable

`@tool(risk_level=fn)`，`fn(args, tool_context) -> "low"|"medium"|"high"`，gate 调用处已持有 tool_args，调用期求值。通用机制，本期仅 send_file 使用。allow-always 指纹机制按 `(工具, 参数)` 维度不变。

## Risks / Trade-offs

- [diff 归因仍是时间窗近似（结果未提及的文件）] → per-server 锁消除并发交错；咽喉改写覆盖主流场景（结果带路径）；归因错误的影响面=归属校验偏严/偏松一次，台账可人工修正。
- [硬链接要求同文件系统] → exchange 与视图同在 agent home（成立）；收编的存量根若跨文件系统 → 该 server 视图退化 staging 复制，走 D5 降级路径不特判。
- [server 事后覆写文件换 inode，视图链接指旧 inode] → 重登记时刷新链接；记录为已知边界。
- [约定注入改变"无显式 env 的新 server"的文件落点] → 这正是特性；`file_isolation: off` 逃生门保留读宿主真实 `~/.config` 的场景。
- [send_file 从拒绝改为升级审批，模型可见行为变化] → 行为更顺（死路→可批准），EGRESS 提示文案同步更新。
- [旧容器无 `/exchange` 挂载] → 新容器一律带挂载；存量容器自然轮换或 `manager.invalidate`；staging 降级兜底。
- [callable risk 扩大权限门审计面] → send_im_message 恒 medium 不变量保持；callable 仅 send_file 一处使用，risk 函数为纯函数可单测穷举真值表。

## Migration Plan

1. 嵌入式迁移：v32 加 `artifacts` 表（已合入）；v33 追加 `scope_key` 列（forward-only，migrate-on-open，旧库自动升级；空表无回填问题）。
2. 部署后新启动的 MCP server 应用约定注入；显式 env 的 server 行为不变（原地收编）。
3. 新建容器带 `/exchange` 挂载；存量容器随 session 轮换自然获得。
4. 回滚：去掉注入与挂载即回到现状；`artifacts` 表残留无害（无人读）。

## Open Questions

- 无。设计决策已与 owner 逐项确认：双向范围、不合并工具、视图挂载方案。
- **2026-06-13 架构审计修正**：归属轴由「裸 session_id 独立轴」改为「继承 workspace scope key」（D0），已与 owner 确认（含单人 `workspace_scope: agent` 下 exchange 跟随 `/workspace` 按 agent 共享）。已合入 main 的 v32 休眠代码（`resolve`/`list_by_session`/`_find_by_path` 以 session_id 为轴、按路径取最新）按 D0/D4 重做：v33 加 `scope_key` 列、签名改收 scope_key、查找按 scope_key 过滤。因属休眠脚手架（无生产 import），改动零现网风险。
