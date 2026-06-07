## ADDED Requirements

### Requirement: 清单注入受条数与字符预算约束

`available_skills_prompt` 渲染的 `<available_skills>` 清单 MUST 受条数上限（`max_skills`，默认 150）与字符上限（`max_chars`，默认 18000）约束，防止 skill 库增长后 system prompt 静默膨胀、吃掉 prompt cache 预算。

- 当 eligible skill 数超过 `max_skills` 时，清单 MUST 仅保留前 `max_skills` 个，并在指令之前置一行截断警告（含已显示数 N 与总数 M），使模型知晓清单不完整。
- 当渲染后的清单字符数超过 `max_chars` 时，MUST 切换为 compact 格式（仅 `name` + `location`，省去 `description`），在更小体积下保留可发现性。
- 默认值足够大，使现有部署（skill 数远小于 150 且字符远小于 18000）的渲染结果逐字节不变。
- 被截断而未列出的 skill 仍可经 `read_skill` 按名加载（清单是发现层，非授权边界）。

#### Scenario: 超条数上限时截断并警告

- **WHEN** eligible skill 数超过 `max_skills`
- **THEN** 清单仅含前 `max_skills` 个 skill
- **AND** 指令前出现一行截断警告，标注已显示数与总数

#### Scenario: 超字符上限时切 compact 格式

- **WHEN** 完整格式（含 description）渲染后超过 `max_chars`
- **THEN** 清单改用 compact 格式（仅 name + location，省 description）

#### Scenario: 小目录不受影响

- **WHEN** eligible skill 数远小于 `max_skills` 且渲染字符远小于 `max_chars`
- **THEN** 清单为完整格式、无截断警告，渲染结果与引入预算前完全一致
