## ADDED Requirements

### Requirement: 下发 per-agent skill 文件

`GET /nodes/{id}/desired-state` 的每个 agent 条目 SHALL 附带 `skills` 字段，携带该 agent 应加载的 skill 的**文件内容**，使 node 能把 skill 落到 agent 侧（agent 进程只读自己 home 的 `<home>/skills`，desired-state 此前只下发 `allowed_skills` 技能名、不含文件）。

- **结构**：`skills` 为数组，每元素 `{name, version, files}`；`files` 为数组，每元素 `{path, content_b64}`，`path` 为 skill 目录内的 POSIX 相对路径、`content_b64` 为该文件字节的 base64（二进制安全）；`version` 为该 skill 目录的内容 hash（复用 `_skill_dir_version`）。
- **收窄语义**（与运行时 `allowed_skills` / `materialize._allowed_skills_for` 一致）：agent 有 `agent_skills` 绑定 → 取其 `enabled` 子集；无绑定但 authored `allowed_skills` 非空 → 取该集；完全未收窄（无绑定且 authored 为空）→ 取整个 skill pool。
- **全局 disable 扣除**：`skills.global_enabled=0` 的 skill MUST NOT 出现在任何 agent 的 `skills`，即便它落在该 agent 的 allowed 集内。
- **非密**：skill 文件不是 secret，按既有非密载荷下发；既有 `config` 剥密规则（剔 `env` 字典与 `credential_ref`）不变，`skills` 不引入任何明文密钥。

#### Scenario: 绑定的 skill 随期望态下发文件

- **WHEN** pool 含 `alpha`、`beta` 两个 skill，agentA 经 `agent_skills` 绑定 enabled `alpha`，node 拉取期望态
- **THEN** agentA 条目 `skills` 仅含 `alpha`，其 `files` 含 `SKILL.md` 等文件的 `path` 与 `content_b64`（解码后与 pool 内一致），并含 `alpha` 的 `version`
- **AND** `beta` 不出现在 agentA 的 `skills`

#### Scenario: 未收窄的 agent 下发整个 pool

- **WHEN** agentB 无任何 `agent_skills` 绑定且 authored `allowed_skills` 为空，node 拉取期望态
- **THEN** agentB 的 `skills` 含 pool 中全部 skill 的文件内容

#### Scenario: 全局禁用的 skill 被扣除

- **WHEN** skill `gamma` 的 `global_enabled=0`，且 `gamma` 落在某 agent 的 allowed 集内
- **THEN** 该 agent 的 `skills` 不含 `gamma`

#### Scenario: skill 文件不含明文密钥

- **WHEN** 期望态返回任一 agent 的 `skills`
- **THEN** `skills` 仅含 skill 目录的文件内容，MUST NOT 含 model api key / IM token 等明文密钥（密钥仍只经 `secrets` 字段下发）
