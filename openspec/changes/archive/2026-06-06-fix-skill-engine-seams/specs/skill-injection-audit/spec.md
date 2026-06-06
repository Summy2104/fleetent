## MODIFIED Requirements

### Requirement: 管理台上传与编辑路径必须执行真实注入审计

管理 API 的上传（`POST /admin/skills`）与编辑（`PUT /admin/skills/{name}`）路径 SHALL 在持久化前对 skill 内容执行与 scan 路径相同的静态注入检测。`engine_audit(content)` seam SHALL 调用 `skill_audit.audit(content)` 返回真实审计结果，不得返回固定的 `{"verdict": "pass", "rules": []}`。

- `severe` 判决 SHALL 阻止 skill 进入 `active` 状态（置为 `quarantined`）
- `suspicious` 判决 SHALL 记录并允许上传，等待人工 force-publish 确认
- `pass` 判决 SHALL 正常发布

#### Scenario: 上传含注入模式的 Skill 被拒绝

- **WHEN** 通过管理 API 上传一个正文命中 `severe` 注入模式的 Skill
- **THEN** `engine_audit()` 返回 `{"verdict": "rejected", "rules": [...]}`
- **AND** 该 Skill 状态被置为 `quarantined`，不进入 active 可用集合

#### Scenario: 上传干净 Skill 正常发布

- **WHEN** 通过管理 API 上传一个正文不命中任何注入模式的 Skill
- **THEN** `engine_audit()` 返回 `{"verdict": "pass", "rules": []}`
- **AND** 该 Skill 状态为 `active`，重扫后可被 agent 使用

#### Scenario: engine_audit 调用真实审计函数

- **WHEN** 管理 API 调用 `engine_audit(content)`
- **THEN** 实际执行 `skill_audit.audit(content)` 的静态规则扫描，不返回固定 pass
