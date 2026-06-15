## MODIFIED Requirements

### Requirement: 双物理根采纳单一有效根策略

skill 索引来自两个物理根——包内 `builtin_skills/`(平台自带)与用户 skills 根,而容器 `/workspace/skills` 只能 bind 一个宿主目录。系统 SHALL 采纳**单一有效根**策略:`/workspace/skills` 默认挂载用户 skills 根(运营可写、可定制),包内 builtin skill 的脚本资源经物化(复制进有效根)或等价兜底保证在该有效根下可达。

该有效根 MUST 与**当前 agent 的 skill 索引被扫描的同一个用户 skills 根**一致:在 `fleetent agent run <name>`(standalone 与 platform spawn 同路径)下,skill 索引扫描以 per-agent `home_dir/skills` 为用户根,故 skills 挂载在 `skill_mount.source` 未显式配置时 MUST 默认采用同一个 per-agent `home_dir/skills`,而非全局 `<base>/skills`。系统 MUST 确保:被 `<available_skills>` 目录列出的、带脚本/资源的可用 skill,其资源在 `$SKILLS_DIR` 下能被脚本访问到,无论该 skill 来自哪个物理根——即**挂载根与扫描根 MUST NOT 发散**。

`skill_mount.source` 被显式配置时仍以其为准(优先于 per-agent 默认);`skill_mount.enabled=false` 时仍不挂载。

#### Scenario: 用户根作为有效根挂载

- **WHEN** 同时存在包内 builtin skills 与用户 skills 根,容器创建
- **THEN** `/workspace/skills` 挂载用户 skills 根,`$SKILLS_DIR` 指向它

#### Scenario: builtin skill 资源在有效根可达

- **WHEN** 一个包内 builtin skill 出现在 `<available_skills>` 目录且其脚本依赖同目录资源,skill 脚本在容器内按 `$SKILLS_DIR/<name>/<资源>` 访问
- **THEN** 该资源可被读到(经物化或等价兜底进入有效根),不因其源自包内根而在容器内缺失

#### Scenario: agent-run 下挂载根采用 per-agent skills 根

- **WHEN** 经 `fleetent agent run <name>` 启动(home 为 `<base>/agents/<name>`),agent 的 `sandbox.skill_mount.source` 未显式配置,为某 scope 创建容器
- **THEN** skills 挂载源解析为 per-agent `<base>/agents/<name>/skills`(与 skill 索引扫描根同一个),`/workspace/skills` 挂入该目录,而非全局 `<base>/skills`

#### Scenario: per-agent skill 的脚本在容器内可执行

- **WHEN** per-agent skills 根下存在一个带脚本的 skill(如 `<home>/skills/common-ns-system-query/scripts/*`),agent 经 `read_skill` 看到它后用 `run_code` 在容器内按 `$SKILLS_DIR/common-ns-system-query/scripts/...` 执行
- **THEN** 该脚本文件在容器 `/workspace/skills` 下存在并可被执行,不再出现「索引可见但容器内缺失」

#### Scenario: 显式 source 配置优先于 per-agent 默认

- **WHEN** agent 的 `sandbox.skill_mount.source` 被显式配置为某宿主路径,经 agent-run 启动并创建容器
- **THEN** 挂载源采用该显式路径,per-agent `home_dir/skills` 默认不生效
