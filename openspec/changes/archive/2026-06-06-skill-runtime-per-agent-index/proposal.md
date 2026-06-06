## Why

`agent_app.boot()` 调用 `scan_skills()` 不带参数，全局 skill 索引从 `FLEETENT_SKILLS_DIR` 或 CWD 的 `./skills` 构建——而不是本 agent 自己 home 的 `skills/`。Change 4 已让 materialize 把 skill 文件分发到 `<home>/skills/`，但运行时仍不读它。结果：standalone `fleetent agent run` 进程的 skill catalog 取决于进程 CWD/env，而非它自己的 home，违反"agent 自包含、只读自己 home"的解耦原则。

## What Changes

- `agent_app.boot()` 把 `scan_skills()` 改为 `scan_skills(skills_dir=str(home_dir / "skills"))`，使本 agent 进程的 skill 索引来自它自己的 home
- 目录不存在时安全（`_build_index` 对缺失目录已安全返回，符合 skill-nested-scan）
- 下游无需改动：`available_skills_prompt` / `read_skill` / `collect_disabled_trace` 继续读全局 `_index`，而该索引现在正确反映本 agent home 的 skill

## Capabilities

### New Capabilities

无新 capability。

### Modified Capabilities

- `agent-runtime-cli`：明确 `boot()` 从 agent home 的 `skills/` 构建 skill 索引，使 standalone agent 的 skill catalog 自包含

## Impact

- **修改文件**：`src/fleetent/runtime/agent_app.py`（`boot()` 一行）
- **测试**：`tests/integration/`（验证 boot 后全局索引来自 home/skills；验证 home 无 skills/ 时安全）
- **无破坏性变更**：单 agent 进程的全局索引本就代表该 agent；改为读 home/skills 后语义更正确，无 home/skills 时回退空索引（与缺目录行为一致）
