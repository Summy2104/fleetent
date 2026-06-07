## Why

平台把 admin 上传的 skill 文件写入全局 `engine_skills_dir()`，但 materialize 写 agent home 时只建 `data/` 子目录，从不把 skill 文件复制进去。agent home 下没有 `skills/` 目录。在多 agent 独立进程部署下，每个 agent 进程的 CWD / `FLEETENT_SKILLS_DIR` 很可能指不到那个全局目录，导致 agent.yaml 里 `allowed_skills` 引用的 skill 文件运行时找不到。本 change 让 materialize 把平台管理的 skill 文件分发到每个 agent 的 home，使 agent home 真正自包含。

## What Changes

- `materialize.write_home()` 在写完 `agent.yaml` / `data/` 后，把 `engine_skills_dir()` 下的全部 skill 目录复制到 `<home>/skills/`
- 复制是全量同步：源目录的 skill 全部进入 agent home，运行时由 agent.yaml 的 `allowed_skills`（catalog 收窄）和 `disabled_skills`（禁用）决定哪些可见——文件分发与可见性控制职责分离
- 复制 best-effort：源目录不存在时跳过，不抛异常；幂等（`dirs_exist_ok`）

## Capabilities

### New Capabilities

无新 capability。

### Modified Capabilities

- `platform-agent-lifecycle`：明确 materialize 必须把平台管理的 skill 文件分发到 agent home 的 `skills/`，使 home 自包含

## Impact

- **修改文件**：`src/fleetent/platform/agent_lifecycle/materialize.py`（`write_home()`）
- **依赖**：`engine_skills_dir()` 等价物——materialize 需拿到全局 skills 目录路径（`skill_registry._resolve_skills_dir(None)`）
- **测试**：`tests/integration/`（验证 materialize 后 `<home>/skills/<skill>/SKILL.md` 存在）
- **无破坏性变更**：纯增量复制；无 skill 文件时行为不变
