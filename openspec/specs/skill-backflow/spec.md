## ADDED Requirements

### Requirement: 回流提名

平台 SHALL 允许把某 `(agent, skill)` 的已漂移副本提名回流到公共池。提案 SHALL 携带 agent 进化副本的**完整 bundle**（该 skill 目录下全部文件的 relpath→content，排除 `.git`，非仅 SKILL.md；文本原样存、二进制文件经编码无损保留，推备份分支时按原字节还原）、其 `base_version`（内容 hash，用于冲突检测）与 `base_commit`（同步时记录于目录并从池 git commit 重建 base），并以 `backflow` 类别进入待审 inbox。

#### Scenario: 提名捕获完整 bundle 与 base_commit
- **WHEN** 运营对 agent "support-bot" 已漂移的多文件 skill "crm-ops"（含 SKILL.md + scripts/）发起回流提名
- **THEN** 生成的 `backflow` 提案记录来源 agent、skill、**完整 bundle（含 scripts/ 下文件）**、`base_version` 与 `base_commit`

#### Scenario: 未漂移副本不可提名
- **WHEN** 对一个 `drift=0` 的 `(agent, skill)` 发起回流提名
- **THEN** 系统拒绝提名（无可回流的分叉内容）

### Requirement: 回流 diff 相对 base 与 head

对每个回流提案，平台 SHALL 展示 agent 进化副本相对**池基准版本**的 diff 与相对**池当前 head** 的 diff。base 内容 SHALL 经 `base_commit`（git commit）从池 git 重建真实 base 内容（SHALL NOT 把内容 hash 当 git ref），使 `diff_vs_base` 反映真实的 base→evolved 增量。`base_commit` 为空（存量未重新物化）时 SHALL 优雅降级（标注 base 未知、仅展示 vs head），SHALL NOT 报错或把整份内容误报为新增。

#### Scenario: diff_vs_base 反映真实增量
- **WHEN** 一个回流提案的 base 内容为 A、进化副本为 B（A→B 有具体行级改动）
- **THEN** `diff_vs_base` 含 A→B 的具体增量，而非把 B 整体当全新增

#### Scenario: 展示双向 diff
- **WHEN** 运营打开一个回流提案
- **THEN** 响应含「进化副本 vs base（经 base_commit 重建）」与「进化副本 vs 池 head」两个 diff

#### Scenario: 缺 base_commit 优雅降级
- **WHEN** 一个提案的 `base_commit` 为空
- **THEN** `diff_vs_base` 标注 base 未知、仅提供 `diff_vs_head`，不报错、不把全份内容误报为新增

### Requirement: 回流审批是平台治理决策

回流提案 SHALL 经 admin 控制台的平台治理鉴权审批，SHALL NOT 走 agent-owned DM 审批路径（后者仅用于只影响单个 agent 副本的自进化提案）。审批动作 SHALL 被审计。

#### Scenario: 治理鉴权审批
- **WHEN** 一个具备治理权限的 admin 审批回流提案
- **THEN** 审批被接受并审计

#### Scenario: 非治理路径不可审批回流
- **WHEN** 试图经 agent-owned DM 路径审批一个 `backflow` 提案
- **THEN** 该路径不处理回流提案（回流仅经平台治理审批）

### Requirement: 平台不审核回流（只读查看 + 人工 git 采纳）

平台 SHALL NOT 对回流提案做 accept / reject / fork 治理决策，SHALL NOT 因回流往池或权威分支写入。agent 的进化副本经提名记录 + `backflow_pr_sweep` 推备份分支后，采纳与否**完全是人在 git host 的动作**：对备份分支开 PR 合并到权威分支 → 经入站同步（`skill-git-sync`）自然回到池 → 下发 agent。平台仅提供**只读视图**（提案列表 + 双向 diff）供运营查看 agent 改了什么、备份到哪个分支。SHALL NOT 暴露 accept / reject / fork / open-pr 端点。冲突态（`base_version` ≠ 池 head）仍在只读 diff 中如实展示（相对 base / 相对 head），供人在 git host 裁决；平台 SHALL NOT 自动 merge、SHALL NOT 覆盖池。

> 权衡记录：早期版本平台侧提供 accept（合 PR / 直写池）、reject（清 drift）、fork（另存新 skill）治理动作。因「先自动推备份分支、后人工审」会产生矛盾（reject 只撤 agent 运行时副本，管不到已推的备份分支，若该分支被合并则改动复活），且与「git 为唯一权威写入方向、平台只读」的原则冲突，故移除全部平台侧治理，采纳统一收敛为人在 git host 的 PR。

#### Scenario: 无治理端点
- **WHEN** 客户端访问 `/admin/skills/backflow/{id}/accept`、`/reject`、`/fork` 或 `/open-pr`
- **THEN** 这些端点不存在（路由不存在）

#### Scenario: 只读列表 + diff 可用
- **WHEN** admin 请求回流列表 / 单提案 diff
- **THEN** 返回提案元数据（来源 agent、skill、备份分支、状态）与双向 diff（相对 base / 相对 head、含 conflict 标记），不含任何治理动作

#### Scenario: 采纳靠人 git PR
- **WHEN** 运营想采纳某回流
- **THEN** 在 git host 对该提案的备份分支开 PR 合并到权威分支；合并后入站同步把改动带回池、下发 agent；平台全程不写 git、不写池

### Requirement: drift 观测自动触发回流提名

平台在消费 node 上报的 skill drift 观测时，SHALL 只把某 `(agent, skill)` 标记为 drifted，**SHALL NOT 在该请求路径（`POST /nodes/{id}/status`）上创建提案**——提名需从 owning node 拉取进化副本 bundle（网络操作），不得阻塞状态上报。自动提名改由后台定时任务 `backflow_pr_sweep` 承担：sweep SHALL 扫描已标记 drifted 且无 pending 提案的 `(agent, skill)`，为其创建一条 pending backflow 提案；已存在 pending 时 SHALL 跳过（去重）。上报 `drift=false` SHALL NOT 触发提名。自动提名 SHALL 为 best-effort：单条提名失败（如 owning node 不可达、无可捕获 bundle）SHALL NOT 崩溃 sweep，亦 SHALL NOT 影响同轮其它 `(agent, skill)`——失败 SHALL 记日志，下一轮可重试。每轮提名 SHALL 有预算上限（bounded per round），超额部分留待下一轮，使单轮 wall-clock 有界。

#### Scenario: 上报 drift=true 只落 drift、请求路径不提名
- **WHEN** node status 上报某 managed agent 的 skill `crm-ops` `drift=true`
- **THEN** 平台落 `agent_skills.drift=1`、`POST /nodes/{id}/status` 成功返回，且该请求路径 SHALL NOT 创建提案、SHALL NOT 从 owning node 拉 bundle

#### Scenario: sweep 为已漂移 skill 自动生成 pending 提案
- **WHEN** 存在 `drift=1` 且无 pending 提案的 `(agent, crm-ops)`，`backflow_pr_sweep` 运行一轮
- **THEN** 自动新增 1 条 `(agent, crm-ops)` 的 pending backflow 提案（携带进化副本 bundle）

#### Scenario: sweep 提名去重
- **WHEN** 上述 skill 已存在 pending 提案，sweep 再运行一轮
- **THEN** 不新增第二条提案（仍为 1 条 pending）

#### Scenario: drift=false 不提名
- **WHEN** node status 上报某 skill `drift=false`
- **THEN** 平台不为该 `(agent, skill)` 创建 backflow 提案

#### Scenario: sweep 提名失败被舱壁化
- **WHEN** sweep 提名过程中某条抛出异常（如无法从 owning node 捕获 bundle）
- **THEN** sweep SHALL NOT 崩溃、继续处理同轮其它 `(agent, skill)`，失败被记日志而不传播；该 skill 的 drift 仍正确保留，下一轮可重试

### Requirement: 回流待审经 admin 端点可列出与查看 diff

平台 SHALL 提供经 admin 治理鉴权的只读端点列出待审回流提案，及查看单个提案的 diff。列表 SHALL 返回提案元数据（含来源 agent、skill、冲突态、创建时间），SHALL NOT 在列表中回传 `proposed_bundle` 全量文件内容（避免列表载荷膨胀）。diff 端点 SHALL 复用「相对 base / 相对 head」双向 diff，提案不存在时 SHALL 返回 404。鉴权口径与回流决策端点一致。

#### Scenario: 列出待审回流
- **WHEN** admin 请求回流待审列表端点
- **THEN** 返回各 pending 提案的 id、status、来源 agent（id 与名称）、skill、base_version/base_commit、conflict、创建时间，且不含 `proposed_bundle` 全文

#### Scenario: 查看单提案 diff
- **WHEN** admin 请求某存在提案的 diff 端点
- **THEN** 返回该提案的 `diff_vs_base`、`diff_vs_head`、`conflict`

#### Scenario: 不存在的提案返回 404
- **WHEN** admin 请求一个不存在的提案 id 的 diff
- **THEN** 端点返回 404

#### Scenario: 读端点需治理鉴权
- **WHEN** 无 admin 会话或非 admin 身份请求列表/diff 端点
- **THEN** 端点返回 401/403，不泄露提案内容

### Requirement: 回流治理 router 挂载到平台应用

回流 router（只读 list / diff + 手动 sync-backflow）SHALL 挂载到平台 FastAPI 应用，使这些端点经平台 admin 入口可达；未挂载（端点对客户端 404 不可达）SHALL 视为缺陷。router SHALL NOT 含 accept / reject / fork / open-pr 治理端点。

#### Scenario: 回流端点经平台应用可达
- **WHEN** 客户端访问平台应用上的回流端点（如未鉴权访问待审列表）
- **THEN** 端点已挂载、可路由（返回鉴权相关的 401/403 而非「路由不存在」的 404）

### Requirement: 回流提名先推备份分支保命

启用外部 git 源时，平台 SHALL 经一个独立定时任务（`backflow_pr_sweep`，类比 KB connector sweep）扫描 pending 且未备份的回流提案，把其进化副本经 `push_branch` 推到一个**备份分支** `<branch_prefix>/<agent_id>/<skill>`（**非权威主分支**），并标记 `pr_state="backed_up"`。备份是即时保命动作：即使后续 PR 被拒/关，备份分支仍留痕、agent 改动不丢。node 上报/reconcile 路径 SHALL **零 git 依赖**且 SHALL NOT 触发提名；提名（`backflow_store.nominate`）只存 bundle、亦零 git，且与推备份分支同在 sweep 内进行。`push_branch` 推备份分支 SHALL 只浅取 `base_ref` 的 tip（`depth=1`，不整仓克隆），使一次备份不因仓库历史体积而变慢。分支名 SHALL 按 `(agent, skill)` 稳定，配合去重压制短命分支。

若外部源额外配置了 `skills_subdir`（见 `skill-git-sync`），`push_branch` 推送内容在备份分支中的树路径 SHALL 为 `<skills_subdir>/<name>` 而非 `<name>`，使备份分支与权威仓库的目录布局一致（人工合并到 main 时 skill 落在正确子目录下）。未配置 `skills_subdir` 时，树路径退化为 `<name>`。

#### Scenario: 提名后推备份分支
- **WHEN** sweep 扫到一条 pending 未备份的回流提案
- **THEN** 经 `push_branch` 推一个非主分支的备份分支，提案标 `pr_state="backed_up"`，记录分支名

#### Scenario: node 上报与提名零 git
- **WHEN** node 上报某 agent 的 skill 漂移，随后 sweep 为其提名
- **THEN** node 上报/reconcile 路径不触发任何 git_platform / push 调用（只落 drift）；sweep 内的提名只存 bundle，同样不触发 git 操作（git 只发生在其后的 `push_branch`）

#### Scenario: 配置 skills_subdir 时备份分支内容落在子目录
- **WHEN** 外部源配置了 `skills_subdir="skills"`，sweep 把 skill "crm-ops" 的进化副本推备份分支
- **THEN** 备份分支上该内容的树路径为 `skills/crm-ops`，而非仓库根的 `crm-ops`

#### Scenario: 未配置 skills_subdir 时树路径不变
- **WHEN** 外部源未配置 `skills_subdir`
- **THEN** 备份分支/fork 分支上内容的树路径仍为 `<name>`，行为与本 change 之前一致

### Requirement: 采纳靠人对备份分支开 PR（平台不开 / 不合 PR）

平台 SHALL NOT 开或合并任何 PR，SHALL NOT 以任何方式往权威分支写入。采纳一条回流一律靠人在 git host 对已推的备份分支 `<branch_prefix>/<agent_id>/<skill>` 开 PR 合并到权威分支，合并后经入站同步（`skill-git-sync`）自然拉回池。平台 SHALL 暴露 `POST /admin/skills/backflow/sync-backflow`（admin 手动触发一轮 sweep，只推备份分支、不开 PR）。SHALL NOT 提供平台开 PR 的端点（如 `open-pr`）。历史 `auto_open_pr` 配置列 SHALL 保留但无行为（sweep 忽略之，永不自动开 PR）。

#### Scenario: 手动同步只推备份分支
- **WHEN** admin 调 `POST /admin/skills/backflow/sync-backflow`
- **THEN** 立即触发一轮 sweep，把 pending 未备份提案推备份分支、标 `pr_state="backed_up"`，不开任何 PR

#### Scenario: sweep 即使 auto_open_pr 开启也不开 PR
- **WHEN** 历史配置残留 `auto_open_pr=1`，sweep 扫到一条已备份提案
- **THEN** sweep 只备份、不开 PR（`auto_open_pr` 无行为）

#### Scenario: 平台不提供开 PR 端点
- **WHEN** 客户端访问 `POST /admin/skills/backflow/{id}/open-pr`
- **THEN** 该端点不存在（路由不存在）

### Requirement: git 不可达降级不误改治理状态

回流 sweep 推备份分支的 git 操作 SHALL 舱壁化：git 不可达（`GitPlatformUnavailableError`）时 SHALL 标 `pr_state="deferred"` 下轮/手动重试。单次 git 失败 SHALL NOT 崩溃定时任务、webhook 线程或服务启动。

#### Scenario: sweep 遇 git 不可达降级
- **WHEN** sweep 推备份分支时远端不可达
- **THEN** 提案标 `pr_state="deferred"`、不抛、下轮重试，其它提案与维护任务不受影响
