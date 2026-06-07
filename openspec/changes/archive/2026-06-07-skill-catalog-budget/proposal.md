## Why

`available_skills_prompt` 无条件渲染所有 enabled skill 的完整 catalog（name+description+location）到 system prompt 的稳定前缀。skill-admin-api 设想的是一个完整 CRUD skill 库——当 skill 数量增长，catalog 会静默膨胀，吃掉 prompt cache 预算、推高每请求成本，且无任何上限或警告。openclaw 的 `buildWorkspaceSkillSnapshot` 用 150-skill / 18000-char 预算 + compact fallback 解决了同一问题。

## What Changes

- `available_skills_prompt` 新增 `max_skills`（默认 150）/ `max_chars`（默认 18000）两个 keyword 参数
- 超 `max_skills`：截断到前 N 个，并在指令前加一行 `⚠ Skills: showing N of M (truncated)`，提示模型 catalog 不完整
- 渲染后超 `max_chars`：切换到 compact 格式（仅 `name` + `location`，省去 `description`），在更小体积下保留可发现性；compact 仍超限则进一步截断条数
- 默认值足够大，现有部署（skill 数远小于 150）行为完全不变

## Capabilities

### New Capabilities

无新 capability。

### Modified Capabilities

- `skill-read-on-demand`：catalog 渲染受条数 / 字符预算约束，超限截断或切 compact 并标注

## Impact

- **修改文件**：`src/fleetent/skills/registry.py`（`available_skills_prompt`）
- **测试**：`tests/unit/test_skill_registry.py`（超条数截断+警告、超字符切 compact、默认不影响小目录）
- **无破坏性变更**：新增 keyword 参数有默认值；调用点（normalizer / loop）无需改动；小 skill 库渲染逐字节不变
