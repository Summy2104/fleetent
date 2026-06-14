## Context

Change 1 现状（已落 main）：
- 版本身份 = `_skill_dir_version(dir)` = skill 目录内容的 sha256，**live**。
- `agent_skills.base_version` = 上次干净物化时的池内容哈希，**在写**。
- drift 检测两路：(A) SKILL.md frontmatter 运行时痕迹（`proposal_id`/`applied_at`）；(B) content-hash 比对 dest vs base/src。
- `skills.current_version`（DB Text 列，nullable）：**存在但从不填充**——真占位。
- 池目录 = `FLEETENT_SKILLS_DIR` > `paths.base_dir()/skills`；builtin 经 `materialize_builtin_skills` 幂等 copy 入池。

content-hash 已足够支撑保护，但**回流（第 3 期）需要 history / diff / conflict / 可归因变更 / 稳定 ref**——这些是 git 原生能力、content-hash 给不了。本 change 把池升级为 git 仓库提供这些底座，并把读侧（history/diff）落地为可独立交付的审计价值，避免「建好不接线」。

约束：on-prem 数据主权（git 本地、不出内网）；自包含部署（不假定宿主装了 `git`）；agent→platform 零反写；管理表 Alembic 维护。

## Goals / Non-Goals

**Goals:**
- 池目录成为 git 仓库，每次池变更一次可归因 commit。
- `current_version` 填充为 per-skill 子树最后 commit；`base_version` 升级为 git 标识，存量平滑过渡。
- 只读版本历史 / diff 接口（审计 + 第 3 期 review 读侧地基）。
- 池写串行化，避免并发损坏。

**Non-Goals:**
- 回流写 / 调和（accept→commit-on-accept、reject、fork、conflict 裁决）——第 3 期。
- 改变 drift 检测的判定语义（仍可沿用内容比对；本 change 只把版本身份换成 git 标识）。
- 多租户 per-tenant 池仓（远期）。
- agent 运行时改动。

## Decisions

### D1. 单一池 git 仓库，per-skill 版本 = 子树最后 commit

整个池目录是**一个** git 仓库（非 per-skill 仓）：简单、跨 skill 原子、标准。某 skill 的版本 = **最后触及该 skill 子目录的 commit 标识**（`git log -1 -- <name>/` 语义）。

**为什么 per-skill 子树而非全局 head**：`skills.current_version` 是 per-skill 行；用全局 head 会让「改了 skill A」把 B 的 version 也跳号，污染 B 的回流基准。子树版本精确、各 skill 独立 lineage。

**备选（否决）**：per-skill 一个 git 仓——目录爆炸、跨 skill 操作非原子、与单一池目录现状不符。

### D2. 用 dulwich（纯 Python git），不依赖宿主 git 二进制

实现层用 `dulwich`（Apache-2.0，纯 Python）做 init/commit/log/diff/show，不 shell out 到宿主 `git`。

**为什么**：on-prem appliance 不应假定宿主装了 `git` 且版本可用；纯 Python 库保持自包含、可自托管，符合基础设施原则。

**备选（否决/降级）**：shell out `git` CLI——部署假设强、跨平台行为差异、子进程管理负担。仅在 dulwich 缺某能力时局部考虑。

### D3. 提交时机与归因

每次池**写路径**（admin create/edit/upload/archive、builtin seed）在文件改完后提交一次 commit，message 含操作类型 + skill 名，author 为操作者（admin 用户）或 `system`（seed/init）。提交后刷新受影响 skill 的 `current_version`。

**幂等 seed**：`materialize_builtin_skills` 仅在内容实际变化时提交（无变化不产空 commit）。

### D4. base_version content-hash → git 标识 的平滑过渡

升级后 materialize 写的 `base_version` 是池版本的 git 标识。存量行存的是 64-hex content-hash，无法解析为 git 对象。过渡规则：首次 post-升级物化某 (agent, skill) 时，若 `base_version` 不能解析为本池 git 对象 → **回退内容比对**判 drift（不因「哈希 ≠ git sha」误判 drift）、并把 `base_version` re-baseline 写成当前 git 标识。

**为什么**：避免升级当天全 fleet 误判 drift、把所有副本冻结。

### D5. 池 git 写串行化

池 git 写（commit/init）经单机文件锁串行化，避免并发 admin 写或 seed 与写竞争损坏仓库。读（log/diff/show）不加写锁。

**备选**：进程内 asyncio 锁——不够（多 worker / CLI 与 server 并存）；用文件锁覆盖跨进程。

### D6. 池仓初始化（存量升级）

升级时若池目录非 git 仓：`git init` + 提交当前全部内容为初始 commit（author=`system`，message=`seed: initialize pool from existing skills`），随后为每个 skill backfill `current_version`。已是 git 仓则跳过。`.git` 目录不参与 skill scan、不被 copytree 进 agent home（materialize 只遍历 skill 子目录、`.git` 不是 skill dir，但需显式排除以防边界情况）。

## Risks / Trade-offs

- **[误判全员 drift]** base_version 语义切换 → 见 D4 re-baseline 兜底；并加测试覆盖「升级后首次物化不误判 drift」。
- **[.git 泄漏进 agent home]** copytree 池→home 时若把 `.git` 带进去 = 体积 + 泄漏历史。→ materialize 遍历时显式跳过 `.git`，加测试断言 agent home 无 `.git`。
- **[并发写损坏池仓]** → D5 文件锁；加并发写测试。
- **[dulwich 能力 / 性能]** 大池或大二进制资源下 dulwich diff/log 性能未知 → 限定 diff 接口在文本 SKILL.md + 合理大小；超限降级为「仅列变更文件名」并告警（不静默截断）。
- **[seed 空 commit 噪音]** → D3 仅内容变化才提交。
- **[池目录被外部手动改动]** 运营直接手改池文件绕过 commit → 下次写路径 commit 会把手改一并纳入（git add -A 语义），可接受；文档提示池应经 admin 路径改。

## Migration Plan

无 schema 迁移（`current_version`/`base_version` 列已存在）。升级数据步骤：
1. 池目录 `git init`（若非仓）+ 初始 commit（D6）。
2. 为池内每个 skill 计算并写入 `current_version`（子树最后 commit）。
3. 代码切换：写路径接 commit；materialize 写 git 标识 base_version + D4 过渡；新增只读版本端点。
4. 首次各 agent 物化时按 D4 re-baseline 存量 base_version。

**Rollback**：本 change 无 schema 变更，回滚 = 还原代码；池目录的 `.git` 可保留（无害，下次升级复用）或删除（退回无版本化）。`current_version`/`base_version` 退回占位语义不影响 Change 1 的 content-hash drift 路径（仍可工作）。

## Open Questions

- `current_version` 存 full commit sha 还是 short ref？倾向 full sha（稳定、无歧义），UI 显示截断。apply 时定。
- 版本历史 / diff 端点的鉴权与现有 `_current_user`/`_require_admin` 一致即可；是否对 viewer 开放只读历史？倾向 viewer 可读历史、diff 同 list 权限。apply 时定。
- dulwich 是否需要 LFS 类机制处理大二进制 skill 资源？本 change 先不引入，超大资源走「仅列文件名」降级；若成常态再单独立项。
