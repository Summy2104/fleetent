## Context

`fleetent agent run` 是一进程一 agent。该进程的模块级全局 skill 索引 `skill_registry._index` 语义上就代表这一个 agent 的 skill 集合。当前 `boot()` 调 `scan_skills()` 不带参数，索引建自 `_resolve_skills_dir(None)`（`FLEETENT_SKILLS_DIR` 或 CWD 相对 `./skills`）——与本 agent 的 home 无关。

Change 4 已让 materialize 把平台 skill 文件复制到 `<home>/skills/`。本 change 让运行时读这个目录。

`SkillIndex` 类（per-agent 隔离索引对象）是为多 agent 平台进程设计的——一个进程服务多个 agent 时各持独立索引。但 standalone 是单 agent，无需对象隔离：直接把全局 `_index` 指向本 agent 的 `home/skills/` 即可，且让 `available_skills_prompt` / `read_skill` / `collect_disabled_trace`（都读全局 `_index`）零改动地正确工作。

## Goals / Non-Goals

**Goals:**
- standalone agent 进程的 skill 索引来自它自己的 `<home>/skills/`
- 下游 catalog 渲染 / read_skill / disabled trace 不改动
- home 无 `skills/` 时安全回退（空索引）

**Non-Goals:**
- 不为 standalone 引入 `SkillIndex` 对象穿透 `run_stream`（多 agent 平台才需要；standalone 单 agent 用全局索引更简单正确）
- 不改 `available_skills_prompt` / `read_skill` 签名
- 不动多 agent 平台路径（platform server 的 skill 加载不在本 change 范围）

## Decisions

### D1：repoint 全局 `_index`，而非穿透 SkillIndex 对象

standalone = 单 agent/进程 → 全局 `_index` 就是这个 agent 的索引。`boot()` 用 `scan_skills(skills_dir=str(home_dir/"skills"))` 重建全局索引指向 home。

替代方案：构造 `SkillIndex(home/"skills", allowed=...)` 并穿过 `run_stream` + 改 `read_skill` 接收 index 参数——被否决：改动面大（run_stream/run/read_skill 签名 + build_app + loop），且对单 agent 无收益。`SkillIndex` 留给未来多 agent 平台进程。

### D2：扫描路径用 `home_dir / "skills"`，与 Change 4 的复制目标一致

Change 4 的 `_copy_skills` 把文件复制到 `<home>/skills/`。boot 扫描同一路径，闭环。

### D3：缺目录安全，不预先建目录

`_build_index` 对不存在的目录安全返回（skill-nested-scan spec）。`fleetent agent init` 生成的、未经平台 materialize 的 home 可能无 `skills/`——此时索引为空，agent 正常运行（无 skill catalog），不报错。boot 不主动创建空 `skills/` 目录。

### D4：`allowed_skills` / `disabled_skills` 的收窄仍在 run_stream 内

`run_stream` 已从 `allowed_skills` 参数做 catalog 收窄，`available_skills_prompt` 从 active agent 的 `disabled_skills` 做禁用。本 change 只改"索引建自哪个目录"，收窄/禁用逻辑不变——它们作用在 boot 重建后的 `_index` 上，行为正确。

## Risks / Trade-offs

**[Risk] 全局 `_index` 被 boot repoint 影响同进程其他读者**
→ standalone 进程只有这一个 agent，无其他读者。多 agent 平台进程不走 `boot()`（走 platform server 的 lifespan），不受影响。

**[Risk] home/skills 与 builtin_skills 的合并**
→ `_build_index` 始终扫描 builtin_skills + 给定 user dir。boot 传 `home/skills` 作为 user dir，builtin 仍照常并入——与现有行为一致。

**[Risk] `agent.skills_dir` 字段被忽略**
→ 当前 standalone 的 home 布局固定为 `home/skills/`（Change 4 约定）。`agent.skills_dir`（authored 字段）在 standalone 运行时不再用于定位——home 自包含布局优先。若未来需要支持自定义布局，再单独处理。本 change 以 home/skills 为准，保持与 Change 4 一致。
