## ADDED Requirements

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
