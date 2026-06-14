## Context

Skill 子系统平台侧现有三张表（management.db，Alembic 018，详见 `docs/architecture/skill-system.md`）：

- `agent_skills`（绑定，live）：`PK(agent_id, skill_name)`，`FK agent_id→agents.id CASCADE`（082 加）。
- `skill_admin_state`（治理，live）：`PK skill_name`，无 FK。列 `status/global_enabled/audit_verdict/audit_rules/forced/archived_at/updated_at`。
- `skill_provenance`（self-managed 溯源，**inert**）：`PK skill_name`，无 FK。列 `source/drift/immutable_fields/last_deploy_at/updated_at`。

运行时自进化已 live：`reflection` 生成 `SkillProposal` → DM 投递人审（agent-owned，平台 console 只读）→ `apply_skill_proposal_to_boundary` → `skills.write_skill(source="reflection")` 落入**该 agent 自己的** `home/skills/`（原子写 + `.bak`）。

两个缺口：
1. **保护缺失**：`materialize._copy_skills` 用 `copytree(dirs_exist_ok=True)` **无条件覆盖**，绑定/全局启停触发的重新部署会抹掉 agent 运行时进化但未回流的 skill。
2. **drift 键错位**：`skill_provenance.drift` 以 `skill_name` 为键（per-skill 全局），无法表达「agent A 漂移、agent B 没漂移」——保护无法按 agent 副本精确生效。

约束：
- 核心架构契约——agent 运行时禁止反写 platform 表；platform 需要 agent 数据时只能**读** agent 侧产物。
- 管理表仅由 Alembic 维护，不在 store 中 `_init_db()` 建表；手写 SQL、named parameters、走 store 边界。
- `docs/architecture/data-model.md` 与 `openspec/specs/` 主 specs 本 change 不改（集成车道统一刷）。

## Goals / Non-Goals

**Goals:**
- 修正 drift 键错位：drift 迁到 per-agent-per-skill 轴（`agent_skills`）。
- 引入 `skills` 主表作为池 catalog 权威元数据源，消除「skill_name 软键浮空、无主表」与「治理/溯源两表 1:1 同键」的结构问题。
- 部署期保护：重新部署不再覆盖已漂移的 agent 副本。
- 为后续回流（第 3 期）铺底：`base_version`（绑定上的部署基准版本）+ `current_version`（池 head 指针）落库。
- 清除 inert 调和脚手架（promote/discard/`askit_override`）与死列 `last_deploy_at`，去 askit 品牌。

**Non-Goals:**
- 池的 git-on-disk 版本化（第 2 期）——本 change 仅落 `current_version`/`base_version` **列**，不接 git 真实版本语义（先用占位/内容哈希）。
- 回流审流与真调和算子（第 3 期，复用 `reflection_management` 的 `SkillProposal`）。
- agent 运行时改动（drift 维护全在 platform 侧）。
- 多租户 per-tenant 池（远期）。

## Decisions

### D1. 三表 → 两表（`skills` 主表 + 扩展 `agent_skills`），删 `skill_provenance`

`skills`（新主表，仅元数据/索引，内容在文件系统池）：

| 列 | 来源 | 说明 |
|---|---|---|
| `name` | PK | 池 skill 名（文件系统实体名）|
| `status` | skill_admin_state | active/archived/quarantined |
| `global_enabled` | skill_admin_state | |
| `audit_verdict`/`audit_rules`/`forced` | skill_admin_state | 治理 |
| `source` | skill_provenance | managed/adhoc（池 skill 来源）|
| `immutable_fields` | skill_provenance | JSON |
| `current_version` | **新增** | 池 head 版本指针（顶替死列 `last_deploy_at`；第 2 期接 git）|
| `archived_at`/`created_at`/`updated_at` | | |

`agent_skills`（绑定 + per-agent 部署态）新增：

| 列 | 说明 |
|---|---|
| `base_version` | 该 agent 物化自的池版本（回流基准）|
| `drift` | 这个 agent 副本是否分叉（**从 skill_provenance 搬来，键现在对了**）|
| `drift_at` | 漂移观测时间 |

**为什么不合并成一张表**：绑定/部署态是 per-(agent,skill)，治理/catalog 是 per-skill，两个不同的键基数，强行合并会产生稀疏冗余。两表各守其键最自然。

**为什么引入主表（vs 继续软键）**：池正在成为版本化权威源，`current_version` 等池级事实需要一个权威落点；主表也让 `agent_skills.skill_name` 可加 FK 完整性。代价是池内每个 skill 需保证有 catalog 行（scan/seed 时 upsert），不再靠「无行即默认 active/enabled」的惰性兜底。

**主表命名 `skills`**：与 `agents`/`users` 主表复数惯例一致；docstring 写清「仅元数据、内容在文件系统池」以免误解为存内容。

### D2. drift 维护单向 platform（不破坏架构契约）

drift 标志在 platform 表，但运行时修改发生在 agent 侧，agent runtime 禁止反写 platform 表。因此 **drift 由 platform 侧判定**，两种可选信号（实现取其一或组合）：

- **信号 A（产物标记）**：agent 侧 `write_skill` 已把 `SkillWriteProvenance`（source/proposal_id/applied_at）注入 SKILL.md frontmatter。platform 读 `home/skills/<name>/SKILL.md` frontmatter，发现运行时写入痕迹 → 判 drift。
- **信号 B（内容哈希比对）**：platform 比对 `home/skills/<name>` 内容哈希与 `base_version` 对应池内容哈希，不一致 → 判 drift。

判定与 `drift` 列写入均在 platform（materialize 或专门的 reconcile 读取路径）完成——platform 读 agent home（platform 管理的产物）、写 platform 自己的表，**单向 platform→agent 读，零反写**。

**备选（否决）**：让 agent 运行时直接置 platform 的 drift 列——直接违反核心架构契约，否决。

### D3. 部署保护：materialize drift 感知，per-skill 副本粒度

`_copy_skills` 从「整目录无条件 `copytree` 覆盖」改为「按 skill 子目录逐个判定」：该 (agent, skill) `drift=1` → **跳过覆盖该子目录**（保住进化副本）、记审计日志；`drift=0` → 正常覆盖并刷新 `base_version`。

**为什么子目录粒度而非整目录**：drift 是 per-skill 的；整目录跳过会连带冻结同 agent 其它未漂移 skill 的更新。

**保护与可见性正交**：被保护（不覆盖）的 skill 仍受 `allowed_skills`/`disabled_skills` 运行时收窄约束——保护只管「不抹掉文件」，不改变启用矩阵。

### D4. 移除 inert 调和端点与死列

`POST /admin/skills/{name}/provenance/{promote,discard}`、`askit_override()`、`last_deploy_at` 全部移除：它们操作即将删除的 `skill_provenance`、且是 no-op 占位。真回流调和（promote/discard/fork）留待第 3 期用 `reflection_management` 的 `SkillProposal` inbox 重建，不在本 change 留半成品。

### D5. API 响应形变

- `list_skills`：行级 `drift` 从「per-skill 标志」改为 **per-agent 聚合语义**（如 `drifted_agents` 计数或列表），或从 skill 行移除、改由 per-agent 视图承载。`source` 改读 `skills.source`。
- `edit_skill`：移除 `immutable_warning`/`drift` 响应字段（per-skill drift 不再存在）。`is_immutable_change` 逻辑若仍需保留（编辑池权威版时的不可变字段告警），改读 `skills.immutable_fields`。
- `create_skill`/`_import_skill_dir`/`_publish`：`source` 的唯一真实消费者原为 `set_provenance`，改为写入 `skills.source`；`_publish` 签名里未使用的 `source` 形参清理。

## Risks / Trade-offs

- **[数据迁移正确性]** 现有 `skill_provenance.drift`（per-skill）无法无损映射到 per-agent `agent_skills.drift`（语义维度不同）→ 迁移时 per-agent drift 一律初始化为 0，并在迁移说明里标注「历史 per-skill drift 不携带、首次重新部署后由 platform 重新判定」。inert 期间 drift 基本未被有意义写入，丢弃可接受。
- **[主表行缺失兜底]** 引入主表后，池内 skill 若无 catalog 行会失去惰性默认 → 迁移须从现有 `skill_admin_state` 全量 backfill，且 scan/seed 路径 upsert 兜底；缺行时读取仍返回 active/enabled 默认以保兼容。
- **[保护与回流的时间差]** 第 2/3 期未落地前，被保护的漂移副本无回流出口，会长期停留在 agent home。本 change 接受此中间态（保护优先于回流，先止血）；审计日志记录被保护跳过的 skill 以便运营可见。
- **[`current_version`/`base_version` 暂为占位]** 第 2 期接 git 前，这两列先用内容哈希或单调计数占位；需保证列语义在第 2 期可平滑升级为 git ref（避免再次破坏性迁移）。
- **[API 形变破坏前端]** `list`/`edit` 响应与移除的端点会影响 `skill-admin-ui`；本 change 同步移除对应 UI 入口（promote/discard 按钮、per-skill drift badge），避免悬空调用。

## Migration Plan

1. **新建 `skills` 表**，从 `skill_admin_state` 全量 backfill（`status/global_enabled/audit_verdict/audit_rules/forced/archived_at/updated_at`），并将 `skill_provenance` 的 `source`/`immutable_fields` 按 `skill_name` 合并进对应行；`current_version` 初始化为占位值；缺 provenance 行的 skill `source` 默认 `adhoc`。
2. **扩展 `agent_skills`**：加 `base_version`（默认 NULL 或当前池占位版本）、`drift`（默认 0）、`drift_at`（默认 NULL）。可选加 `FK skill_name→skills.name`（评估存量脏值后决定是否启用）。
3. **删除 `skill_provenance` 表**（列已迁移完毕）。
4. **代码切换**：store/api/materialize 改读写新结构；移除 provenance 调和端点与 `askit_override`。
5. **迁移号 apply 时再定**（不写死）；遵循 Alembic forward-only。

**Rollback**：迁移为破坏性结构变更，回滚需反向迁移（重建 `skill_provenance`、回填 `source`/`immutable_fields`、从 `agent_skills` 摘除新列）；per-agent drift 在回滚后丢失（可接受，inert 期数据）。部署前在副本库验证 backfill 计数对账（`skills` 行数 == 迁移前 `skill_admin_state` ∪ `skill_provenance` 的 skill 名集合基数）。

## Open Questions

- `agent_skills.skill_name` 是否启用 `FK→skills.name`？取决于存量 `agent_skills` 是否仍有未清理的脏 skill_name（082 修过 agent_id 混写，skill_name 侧需确认）——apply 阶段先查存量再定，避免迁移因孤儿行失败。
- drift 判定取信号 A（产物标记）还是信号 B（内容哈希），或组合？apply 阶段按实现成本与误报率定；spec 只约束「platform 单向判定、不反写」的契约，不锁具体信号。
