## Why

Skill 生命周期到目前为止是**单向**的：池 → 部署 → agent 运行时进化（reflection 自进化 / 运营改）→ 落进 agent 自己的 home，Change 1 的保护机制防止它被重新部署抹掉。但进化的成果**回不到公共池**——没有回流路径，改进困在单个 agent 里，无法惠及全队，被保护的漂移副本也长期无出口（Change 1 已知的中间态）。

本 change（3 期路线第 3 期，收尾）建**回流审流**：把 agent 已漂移的 skill 副本提议回公共池，经人工 review（diff、冲突可见）后接受 / 拒绝 / fork，接受即更新池（依赖第 2 期的 git 版本化提交一次新 commit）。

关键设计：**回流审批是平台治理决策（admin 控制台），不是 agent-owned DM 审批**——因为回流改的是**共享池**、影响整个 fleet，与只影响单个 agent 副本的自进化审批（agent-owned、DM）性质不同。两者复用 diff/review 的 UI 范式，但审批主体与影响面不同。

## What Changes

- **新增回流提案**：把某 `(agent, skill)` 的已漂移副本提名回流（运营发起，或由 drift 列表暴露候选）。提案携带 agent 进化副本内容 + 其 `base_version`。
- **回流 diff**：展示 agent 进化副本相对**池基准版本（`base_version`）**与**池当前 head** 的 diff，供人 review。
- **平台治理审批**（admin 控制台、非 agent-owned DM）：
  - **accept**：把进化内容写回池 → 池 git 提交一次新 commit（`current_version` 前移）→ 清该 agent 该 skill 的 drift → 其余 agent 按常规重新物化拿到新版本。
  - **reject**：丢弃该回流；标记该副本将在下次部署被池版本覆盖（清 drift）。
  - **fork**（甲的逃生舱）：把进化副本作为**新命名 skill**（如 `X-variant`）落池并绑定到该 agent，不覆盖权威 `X`；回避冲突、由人逐例选择。
- **冲突显式暴露**：当 agent 的 `base_version` ≠ 池当前 head（部署后池已被他人推进），review 时 SHALL 显式标记「基于过期版本」，由人裁决（基于新 head 重导 / 接受覆盖 / fork），**绝不自动 merge**。
- **命名正名收尾**：审计残留 askit 品牌挂在机制上的命名（`askit_override` 已于 Change 1 删除；`askit_console` 包承载 agent apply API 是名副其实、保留）；仅对「机制被误挂 askit 品牌」者正名，不动合法 askit-facing 命名。

## Capabilities

### New Capabilities
- `skill-backflow`: agent 漂移副本 → 公共池 的回流审流——提名、相对 base/head 的 diff、平台治理审批（accept/reject/fork）、accept 提交池新版本并清 drift、冲突显式暴露不自动 merge。

### Modified Capabilities
（无：回流为全新能力。自进化审批 `skill-proposal-review`（agent-owned/DM）不变；池 git 版本化由第 2 期 `skill-pool-versioning` 提供，本 change 仅在 prose 中引用其 commit/diff/version 能力，不重复 delta。）

## Impact

- **owning package**: `platform`（`skill_management` 回流流程 + 复用第 2 期池 git 提交/版本 + `agent_lifecycle/materialize` 重新物化）。
- **public API surface**:
  - 新增回流端点：提名 / 列出回流候选、获取回流 diff（相对 base 与 head）、`accept`/`reject`/`fork` 决策端点（admin 治理鉴权）。
  - 调用第 2 期池 git 写：accept→`commit_pool(...)`；diff←`pool_diff`/`pool_content_at`。
  - `materialize`：accept/reject 后清 drift + 重新物化受影响 agent。
- **owned tables**: 回流提案的持久化——优先复用 / 扩展 reflection 域的 `skill_proposals`（加一个 `backflow` kind + 来源 agent / base_version 字段），避免新建并行表；若结构不契合再评估新表（迁移号 apply 时定、不写死）。
- **config namespace**: 无新增。
- **cross-module dependencies**: 依赖第 2 期 `skill-pool-versioning`（git 提交 / diff / 版本）；读 agent home 进化副本内容（platform→agent 单向读）；复用 reflection `skill_proposals` 存储。agent→platform 零反写不变。
- **migration/shim plan**: 若复用 `skill_proposals` 加 kind/字段 → 轻量 Alembic 迁移（号 apply 时定）；无表删除。
- **依赖顺序**: 本 change 依赖第 2 期（`skill-pool-git-versioning`）已落地并 sync；**apply 前需在第 2 期 specs 同步后 `opsx:validate` 复核本 change 的 prose 引用与 base 是否一致**。
- **out of scope**: 自动 merge（明确否决，只人工裁决冲突）；多租户池回流（远期）；`docs/architecture/data-model.md` 与主 specs 不在本 change 改（集成车道统一刷）。
