## ADDED Requirements

### Requirement: 回流提名

平台 SHALL 允许把某 `(agent, skill)` 的已漂移副本提名回流到公共池。提案 SHALL 携带 agent 进化副本的**完整 bundle**（该 skill 目录下全部文件的 relpath→content，排除 `.git`，非仅 SKILL.md）、其 `base_version`（内容 hash，用于冲突检测）与 `base_commit`（部署时池 git commit，用于重建 base），并以 `backflow` 类别进入待审 inbox。

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

### Requirement: accept 更新池并清 drift

审批 accept 时平台 SHALL 把进化副本的**完整 bundle** 写入公共池该 skill（先清该 skill 目录再原子落盘，使被删文件不残留），并经池 git 提交一次新 commit（含来源归因），使该 skill 的 `current_version` 前移；SHALL 清除来源 `(agent, skill)` 的 drift；其余绑定该 skill 的 agent SHALL 在常规重新物化时拿到新版本。

#### Scenario: accept 写回完整 bundle
- **WHEN** 运营 accept 多文件 skill "crm-ops" 的回流（无冲突）
- **THEN** 池中 "crm-ops" 的 SKILL.md 与 scripts/ 等全部文件更新为进化 bundle 并产生一个新 commit、`current_version` 前移
- **AND** 来源 agent 的该 skill drift 被清除

#### Scenario: accept 后他 agent 拿到新版本
- **WHEN** accept 后另一个未漂移地绑定 "crm-ops" 的 agent 重新物化
- **THEN** 该 agent 拿到回流后的新池版本（含全部 bundle 文件）

### Requirement: reject 丢弃回流

审批 reject 时平台 SHALL 关闭提案且不改动池，并清除来源 `(agent, skill)` 的 drift（使该副本在下次物化被池版本覆盖）；动作 SHALL 被审计。

#### Scenario: reject 后副本将被覆盖
- **WHEN** 运营 reject skill "crm-ops" 的回流
- **THEN** 池不变、提案关闭、该 agent 的 drift 被清，下次物化其 "crm-ops" 副本被池版本覆盖

### Requirement: fork 落新命名 skill 不覆盖权威

审批 fork 时平台 SHALL 把进化副本的**完整 bundle** 作为**新命名 skill** 落入公共池（经池 git 提交）并将来源 agent 的绑定指向该 fork skill，SHALL NOT 覆盖原权威 skill。

#### Scenario: fork 落完整 bundle 不动权威
- **WHEN** 运营对多文件 skill "crm-ops" 的回流选择 fork
- **THEN** 池新增一个新命名 skill（如 "crm-ops-support-bot"）含完整 bundle 并提交，原 "crm-ops" 权威版不变，来源 agent 绑定指向 fork

### Requirement: 冲突显式暴露不自动 merge

当回流提案的 `base_version` ≠ 池当前 head（部署后池已被推进），平台 SHALL 在 review 时显式标记冲突态并展示进化副本相对 head 的 diff，由人裁决（基于新 head 重导 / 带确认地覆盖 head / fork）。平台 SHALL NOT 自动 merge。

#### Scenario: 过期基准触发冲突态
- **WHEN** 一个回流提案的 `base_version` 落后于池 head
- **THEN** review 显式标记「基于过期版本」并展示相对 head 的 diff，不自动合并

#### Scenario: 覆盖 head 需确认
- **WHEN** 冲突态下运营选择覆盖 head
- **THEN** 需显式确认，accept 记录被覆盖的 head 版本以便经 git 历史回溯

### Requirement: drift 观测自动触发回流提名

平台在消费 node 上报的 skill drift 观测、把某 `(agent, skill)` 标记为 drifted 时，SHALL 自动为该 `(agent, skill)` 创建一条 pending backflow 提案；同一 `(agent, skill)` 已存在 pending 提案时 SHALL 跳过（去重，不重复生成）。上报 `drift=false` SHALL NOT 创建提案。自动提名 SHALL 为 best-effort：提名失败（如 owning node 不可达、无可捕获 bundle）SHALL NOT 令 node 状态上报失败，亦 SHALL NOT 影响同批其它 agent/skill 的 drift 落库——失败 SHALL 记日志。

#### Scenario: drift 转为 true 自动生成 pending 提案
- **WHEN** node status 上报某 managed agent 的 skill `crm-ops` `drift=true`，且该 `(agent, crm-ops)` 当前无 pending backflow 提案
- **THEN** 平台落 `agent_skills.drift=1`，并自动新增 1 条 `(agent, crm-ops)` 的 pending backflow 提案（携带进化副本 bundle）

#### Scenario: 已有 pending 不重复提名
- **WHEN** 上述 skill 在已存在 pending 提案的情况下再次被上报 `drift=true`
- **THEN** 不新增第二条提案（仍为 1 条 pending）

#### Scenario: drift=false 不提名
- **WHEN** node status 上报某 skill `drift=false`
- **THEN** 平台不为该 `(agent, skill)` 创建 backflow 提案

#### Scenario: 提名失败不阻断状态上报
- **WHEN** 自动提名过程抛出异常（如无法从 owning node 捕获 bundle）
- **THEN** `POST /nodes/{id}/status` 仍成功返回、该 skill 的 drift 仍正确落库，失败被记日志而不传播

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

回流治理 router（list / diff / accept / reject / fork）SHALL 挂载到平台 FastAPI 应用，使所有回流端点经平台 admin 入口可达；未挂载（端点对客户端 404 不可达）SHALL 视为缺陷。

#### Scenario: 回流端点经平台应用可达
- **WHEN** 客户端访问平台应用上的回流端点（如未鉴权访问待审列表）
- **THEN** 端点已挂载、可路由（返回鉴权相关的 401/403 而非「路由不存在」的 404）
