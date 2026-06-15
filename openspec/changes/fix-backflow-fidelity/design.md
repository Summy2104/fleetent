## Context

Change 1–3 已落 main。审查发现两处回流保真度缺陷（见 proposal）。根因是**跨 change 语义错配**：

- Change 2 实现有意把 `agent_skills.base_version` 定为**内容 hash**（drift 检测用内容比对，避免 git-sha 语义切换带来的全 fleet 误判风险——这是个好决定，本 change 保留它）。
- Change 3 的 `get_proposal_diff` 却假设 `base_version` 是 git ref，喂给 `pool_content_at()`（`r[ref.encode()]`）→ 内容 hash 在 git 无此对象 → `except: return None` → `diff_vs_base` 退化。
- 另外 Change 3 的 `proposed_content` 单 Text 只存 SKILL.md，多文件 bundle 有损。

Change 3 apply 时的 PHASE B 校准抓到了**命名**漂移（`pool_diff`→`pool_diff_for_commit`）与 `skill_proposals` 被 DROP，但没抓到这层**语义**漂移（base_version 是 hash 还是 ref）——单测弱断言（`diff_vs_base` 非空即过）也没拦住。

## Goals / Non-Goals

**Goals:**
- `diff_vs_base` 展示真实 base→evolved 增量（修 bug）。
- 回流携带并写回完整 skill bundle（修多文件有损）。
- 保留 Change 2 的合理拆分：`base_version`=内容 hash 专供 drift，新增 `base_commit`=git sha 专供回流 base 重建。
- 补强回归测试，断言真实增量，堵住放过 bug 的弱断言。

**Non-Goals:**
- 改 drift 检测机制（仍 content-hash）。
- 改池 git 版本化（复用 Change 2）。
- 改回流的治理审批 / accept/reject/fork / 冲突语义（这些都对，不动）。

## Decisions

### D1. 新增 `base_commit`（git sha），不动 `base_version`（内容 hash）

`agent_skills` 加 `base_commit`：materialize 覆盖副本时写 `pool_version_for_skill(pool_dir, skill)`（该 skill 子树的池 git commit）。`base_version`（内容 hash）保持原样、继续专用 drift 检测。

**为什么不把 base_version 直接改成 git sha**：那会重蹈 Change 2 实现刻意规避的「升级当天全 fleet 误判 drift」风险，且 drift 用内容比对本就正确。两个字段各司其职最稳：hash 判「home 改没改」，sha 定「基于哪个池版本」。

**备选（否决）**：在回流时反查池 git 历史找内容 hash 匹配的 commit——脆弱、昂贵、可能多命中。

### D2. 回流提案快照 `base_commit` + 完整 bundle

提名时把 `agent_skills.base_commit` 复制进提案（稳定，不随 agent 后续 re-materialize 变）。提案内容从单 SKILL.md 改为**完整 bundle**：捕获 agent home 副本目录下全部文件（`rglob`，排除 `.git`）为 relpath→content 映射。

### D3. `diff_vs_base` 用 `base_commit` 重建真实 base

`get_proposal_diff` 改用 `base_commit`（git sha）经 `pool_content_at`（按 git ref 取内容）重建 base 内容，对 evolved 出真实增量。`diff_vs_head`（直读池当前内容）与冲突检测（`base_version` 内容 hash 比对池 head 内容 hash）**保持不变**，二者本就正确。

多文件 bundle 的 diff：SKILL.md 出文本 diff；其余文件至少列出「新增/修改/删除」清单（bundle-aware），超大降级为文件名清单 + 告警、不静默截断。

### D4. accept / fork 写回完整 bundle

accept 把提案 bundle 全量写入池该 skill 目录（先清目录再落，保证删除的文件不残留），再 `commit_pool`。fork 同理写新命名 skill 目录。不再只写 SKILL.md。

### D5. 回归测试断言真实增量

新增/改写测试：构造「base 内容 A → 进化为 B」，断言 `diff_vs_base` 含 A→B 的**具体行级变化**（而非仅断言非空字符串）；多文件场景断言非 SKILL.md 文件也进 bundle 并被 accept/fork 写回。

## Risks / Trade-offs

- **[存量 agent_skills.base_commit 为 NULL]** 升级后未重新物化的绑定 `base_commit=NULL` → 这些绑定被提名回流时 `diff_vs_base` 无 base 可重建 → 优雅降级（标注「base 未知，仅展示 vs head」），下次物化 backfill 后恢复。加测试覆盖 NULL 降级不报错。
- **[存量 backflow_proposals 内容列迁移]** 单 SKILL.md → bundle：存量行迁移为 `{"SKILL.md": <旧值>}`，语义不丢。
- **[bundle 体积]** 多文件 + 大二进制资源进 DB JSON 可能膨胀 → 限定捕获文本与合理大小；超限走「仅列文件名」降级 + 告警（同 Change 2 diff 降级策略），不静默截断。
- **[clear-then-write 误删]** accept/fork 先清目录再写：须确保写入原子性（写 tmp 再 rename，或失败回滚），避免中途失败留空目录。沿用既有 `write_skill` 的 .tmp→rename 范式。

## Migration Plan

1. 一支 forward Alembic 迁移（号 apply 时按 head 现取、不写死）：
   - `agent_skills` 加 `base_commit TEXT NULL`。
   - `backflow_proposals` 加 `base_commit TEXT NULL`；内容列转 bundle 表示（relpath→content JSON），存量 `proposed_content` 迁为 `{"SKILL.md": <旧值>}`。
2. 代码：materialize 写 `base_commit`；backflow 提名捕获 `base_commit` + 全 bundle；`get_proposal_diff` 用 `base_commit` 重建 base；accept/fork 写回全 bundle。
3. backfill：无需一次性脚本，`base_commit` 随各 agent 下次常规 materialize 自然填充。

**Rollback**：反向迁移摘除两个 `base_commit` 列、内容列转回单 SKILL.md Text（bundle 取其 `SKILL.md` 键）。已落池的回流 commit 保留在 git 历史（无害）。

## Open Questions

- bundle 内容列存 JSON-in-TEXT 还是关联子表（一文件一行）？倾向 JSON-in-TEXT（简单、与 agent 侧 `write_skill` 的 `files` dict 同形），apply 时定。
- 非文本/大二进制资源是否纳入回流 bundle？本 change 先限文本 + 合理大小，超限降级列名；大二进制若成常态再单独立项（与 Change 2 同款 open question）。
