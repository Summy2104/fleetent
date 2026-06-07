## Context

Agent home 由 `write_home()` 写出：`agent.yaml` + `.env` + `data/`。缺 `skills/`。平台把 skill 文件存在全局 `skill_registry._resolve_skills_dir(None)`（默认 `./skills`，或 `FLEETENT_SKILLS_DIR`）。多 agent 部署时每个 agent 是独立进程、独立 home，需要各自的 skill 文件副本才能自包含。

Change 5 会让 `agent_app.boot()` 用 `SkillIndex(home/"skills")` 读取本 agent 的 skill。本 change 是其前置：先保证文件在 `home/skills/` 就位。

## Goals / Non-Goals

**Goals:**
- `write_home()` 把全局 skills 目录的内容复制到 `<home>/skills/`
- 复制 best-effort + 幂等：源缺失跳过、重复运行不报错
- 文件分发与可见性解耦：全量复制，可见性由 agent.yaml 的 allowed/disabled 在运行时决定

**Non-Goals:**
- 不在此 change 改 agent runtime 的 skill 加载（Change 5）
- 不做按 `allowed_skills` 的选择性复制（全量复制更简单，可见性控制已由 catalog 收窄覆盖；选择性复制是未来优化）
- 不复制全局以外的 skill 源（builtin_skills 由 agent runtime 自身扫描，不经 home）

## Decisions

### D1：全量复制，不按 allowed_skills 筛选

`write_home()` 复制 `engine_skills_dir()` 下所有 skill 目录到 `home/skills/`。理由：
- agent.yaml 的 `allowed_skills`（catalog 收窄）+ `disabled_skills`（禁用）已经在运行时控制可见性，文件多复制几个不影响行为
- 选择性复制需要把 allowed/disabled 解析逻辑搬进 materialize，重复且易错
- 全量复制让 `home/skills/` 是全局 skills 的镜像，语义简单

### D2：复制源用 `skill_registry._resolve_skills_dir(None)`

与 `skill_admin_api.engine_skills_dir()` 同源。materialize 直接调 `skill_registry._resolve_skills_dir(None)` 拿全局 skills 目录，避免反向依赖 platform 的 skill_management。

### D3：`shutil.copytree(src, home/"skills", dirs_exist_ok=True)`

幂等覆盖。源不存在则跳过（先 `Path(src).exists()` 判断）。复制失败（IO 错误）记录告警但不阻断 materialize——与 `_seed_env` 等步骤的 best-effort 风格一致；agent.yaml 已写出，skill 文件缺失只影响 skill 能力，不应让整个 materialize 失败。

### D4：复制位置——`agent.yaml` 之后、`.env` 之前或之后均可

放在 `_seed_env` 之后，作为 home 写出的最后一步。顺序无依赖关系。

## Risks / Trade-offs

**[Risk] 全量复制使每个 agent home 占用冗余磁盘**
→ 可接受：skill 文件是小文本（SKILL.md + 少量脚本）。若未来 skill 库极大，再考虑按 allowed_skills 选择性复制或软链接。当前 YAGNI。

**[Risk] 复制覆盖 agent home 中 operator 手放的 skill**
→ 已知：与 agent.yaml 一样，`home/skills/` 是平台导出产物。operator 自定义 skill 应进全局 skills 目录（经 admin 上传），不应手放进 agent home。`dirs_exist_ok=True` 会覆盖同名文件。

**[Risk] 源 skills 目录是相对路径（`./skills`），materialize 进程 CWD 不确定**
→ `_resolve_skills_dir` 返回的相对路径相对 materialize 进程（平台进程）CWD 解析。平台进程 CWD 是已知的部署根。若需要绝对化可在 D2 处 `Path(src).resolve()`，但保持与现有 `engine_skills_dir` 一致即可。
