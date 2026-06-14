## Context

3 期路线收尾。前两期落地后：
- Change 1：池 → 部署 → 隔离副本 → 运行时进化（reflection 自进化 live、运营改）→ 保护（drift 副本不被覆盖）。
- Change 2：池为 git 仓，`current_version`/`base_version` 为 git 标识，只读 history/diff。

缺的最后一环 = **回流**：进化成果从 agent home 回到公共池。当前进化困在单 agent，被保护的漂移副本无出口。

回流的语义抉择（与用户在探索阶段已拍定）：
- **甲为默认**：池里 skill X 单一权威；回流 = 对池当前 head 的一个待审「PR」，冲突由人裁决，**不自动 merge**。
- **乙为逃生舱**：reviewer 逐例可选「fork 成新命名 skill」处理 agent 特化，不污染权威 X。
- **自进化保持人审**（Change 已 live、agent-owned/DM）。

新增的关键边界判断（本期定）：**回流审批 ≠ 自进化审批**。自进化只改单个 agent 副本 → agent-owned、DM 审批（既有）。回流改**共享池、影响 fleet** → **平台治理决策、admin 控制台审批**。两者复用 diff/review 范式，审批主体与影响面不同。

约束：on-prem（git 本地）；agent→platform 零反写；不自动 merge；管理表 Alembic。

## Goals / Non-Goals

**Goals:**
- 把 agent 漂移副本提名回流，展示相对 base/head 的 diff，平台治理审批。
- accept = 池 git 提交新版本 + 清 drift + 重新物化；reject = 丢弃 + 下次覆盖；fork = 新命名 skill 落池。
- 冲突（base ≠ head）显式暴露给人，不自动 merge。
- 优先复用 reflection `skill_proposals` 存储，不另起并行表。

**Non-Goals:**
- 自动 merge / 三方合并（明确否决）。
- 改自进化审批（`skill-proposal-review` agent-owned/DM 不变）。
- 池 git 机制本身（第 2 期提供）。
- 多租户池回流（远期）。

## Decisions

### D1. 回流审批是平台治理决策（admin 控制台），与自进化审批分离

回流提案经 admin 控制台审批（治理鉴权），**不**走 agent-owned DM。

**为什么**：回流写共享池、一次 accept 影响所有绑定该 skill 的 agent；这是运营/治理职责，不是单 agent 自治。自进化（单副本）才适合 agent-owned DM。

**复用而非混用**：复用 reflection inbox 的 diff/review **UI 范式与存储**，但回流是独立 kind、独立审批主体。

### D2. 回流 diff 三方可见：进化副本 vs base vs head

review 时 SHALL 展示：agent 进化副本（home/skills/X 内容）相对 **`base_version`**（部署基准）的 diff（= 这个 agent 改了什么），以及相对**池当前 head** 的 diff（= 落池会覆盖什么）。两个 diff 让 reviewer 判断改动意图与落池影响。

### D3. 三种决策的精确语义

- **accept**：进化副本内容写入池目录该 skill → 第 2 期 `commit_pool` 提交一次新 commit（author=审批运营、message 含来源 agent）→ `current_version` 前移 → 清该 (agent, skill) drift（其 base_version 下次物化对齐新版本）→ 其余绑定 agent 按常规 drift 感知物化（未漂移者拿新版本）。
- **reject**：关闭提案、不改池；清该 (agent, skill) drift → **下次物化该副本被池版本覆盖**（进化被丢弃）。运营须知 reject = 放弃该进化。
- **fork**：进化副本作为**新命名 skill**（默认名 `<X>-<来源标识>`，运营可改名）落池并 `commit_pool`；把该 agent 对 X 的绑定改/加为 fork skill；权威 X 不变；清原 drift。

### D4. 冲突显式暴露，人工裁决，不自动 merge

提案携带 agent 的 `base_version`。审批时比对池当前 head：
- `base_version == head`（池未动）→ 干净，accept 直接落。
- `base_version != head`（部署后池已被他人推进）→ **冲突态**：review SHALL 显式标记「基于过期版本 base，head 已是 X」，并展示进化副本相对 head 的 diff。reviewer 裁决：基于新 head 重导后再提 / 接受覆盖 head（带确认）/ fork。系统 SHALL NOT 自动 merge。

### D5. 存储复用 reflection `skill_proposals`

回流提案优先复用 reflection 域的 `skill_proposals` 表，新增 `backflow` kind + 来源 agent / `base_version` 字段（轻量迁移）。

**为什么**：回流提案与自进化提案同为「skill 变更待审」，共享 inbox/diff/审计基础设施；另起并行表会重复机制。若字段差异过大导致复用别扭，再评估独立表（apply 时定）。

## Risks / Trade-offs

- **[reject 误丢进化]** reject 即放弃进化、下次覆盖 → 决策端点要求确认 + 审计；UI 文案明示后果。
- **[accept 覆盖他人改动]** 冲突态 accept 覆盖 head → D4 强制显式确认 + 记录被覆盖的 head 版本，可经 git 历史回溯。
- **[fork 致池膨胀]** fork 逐例由人选、非默认；若 fork 泛滥说明该 skill 本应是 agent 特化——运营可见、可治理（归档无用 fork）。
- **[跨 change prose 漂移]** 本 change prose 引用第 2 期 git 能力；若第 2 期 apply 时接口/语义微调 → 本 change apply 前 `opsx:validate` + 人工复核引用，必要时小改 artifacts（注意：第 2 期 apply 开跑后别在 main 改第 2 期同名 artifacts）。
- **[skill_proposals 不可复用 — 已确认]** `skill_proposals` 在 agent_state_migrations v26 中已 DROP（agent-side 表已去除）；backflow 提案改用独立 Alembic 管理表 `backflow_proposals`，无需 fallback 判断。

## Migration Plan

1. （若复用 `skill_proposals`）轻量 Alembic 迁移加 `backflow` kind + 来源 agent / `base_version` 字段（号 apply 时定）。
2. 实现回流流程：提名 → diff（调第 2 期 `pool_diff_for_commit`/`pool_content_at`）→ 治理审批 accept/reject/fork → accept 调 `commit_pool` + 清 drift + 重新物化。
3. 命名正名审计：grep 残留 askit 品牌；仅正名「机制被误挂」者，保留合法 askit-facing（`askit_console` agent apply）。

**Rollback**：回滚代码 + 反向迁移（摘除 `skill_proposals` 新增字段/kind）。已落池的回流 commit 保留在 git 历史（无害，回滚不擦池历史）。

## Open Questions

- 回流候选的提名入口：运营从 drift 列表手动提名，还是 drift 出现即自动建 `pending` 回流候选？倾向「drift 列表可见 + 运营手动提名」起步，避免噪音。apply 时定。
- fork 的默认命名规则与冲突（fork 名已存在）处理？apply 时定，spec 只约束「fork 落新命名、不覆盖权威」。
- accept 后其余 agent 的重新物化是即时触发还是等下次常规 materialize？倾向复用既有 rematerialize 触发，不新增即时风暴。apply 时定。
