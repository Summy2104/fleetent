# sandbox-skill-mount Specification

## Purpose
TBD - created by archiving change sandbox-execution-world. Update Purpose after archive.
## Requirements
### Requirement: 宿主 skills 目录挂载到容器 /workspace/skills

在声明 `workspace_mount` capability 的后端上,系统 SHALL 在创建容器时把宿主 skills 根 bind-mount 到容器内固定路径 `/workspace/skills`,使 skill 脚本及其同目录资源在容器内可达。该挂载 MUST 默认以**只读**(ro)方式挂入(skill 资产由运营/作者维护,不应被 agent 运行时改写),并 MUST 可经配置切换为可写。挂载 MUST 与 per-scope workspace 挂载并存,二者互不覆盖。

#### Scenario: skills 默认只读挂入容器
- **WHEN** Docker 后端下为某 scope 创建容器,skill_mount 启用且 read_only 为默认值
- **THEN** 宿主 skills 根被以 ro 方式 bind-mount 到容器 `/workspace/skills`,容器内可读该目录、写入被拒

#### Scenario: 可配为可写挂载
- **WHEN** 配置将 skill_mount 的 read_only 置为 false 并创建容器
- **THEN** `/workspace/skills` 以可写方式挂入,容器内可写该目录

#### Scenario: 不支持挂载的后端不挂 skills
- **WHEN** 选定后端未声明 `workspace_mount`,为某 scope 获取工作区
- **THEN** 创建调用不携带 skills 挂载,降级态按 `sandbox-workspace-root` 的「降级态 skills 供给」条款保证 `$SKILLS_DIR` 可达

### Requirement: 注入 SKILLS_DIR 环境变量

容器创建时系统 SHALL 注入环境变量 `SKILLS_DIR=/workspace/skills`,使 skill 脚本以 `$SKILLS_DIR` 为根定位自身资源,而非硬编码宿主或容器绝对路径。该注入 MUST 与既有 `sandbox_env` 注入并存,MUST NOT 覆盖或被 `sandbox_env` 中同名变量静默替换(若冲突以平台注入的 `SKILLS_DIR` 为准并记录)。

#### Scenario: 容器内 SKILLS_DIR 指向挂载点
- **WHEN** Docker 后端下 skill_mount 启用,容器创建完成,在容器内读取 `SKILLS_DIR`
- **THEN** `SKILLS_DIR` 值为 `/workspace/skills`,指向已挂入的 skills 根

#### Scenario: SKILLS_DIR 与 sandbox_env 并存
- **WHEN** agent 的 `features.sandbox_env` 注入了若干非敏感变量,同时平台注入 `SKILLS_DIR`
- **THEN** 容器内既能读到 `sandbox_env` 的变量,也能读到 `SKILLS_DIR=/workspace/skills`

### Requirement: skills 挂载源纳入 config_hash 并过 is_blocked_mount

skills 挂载的**宿主源路径**与其只读/可写模式 SHALL 纳入容器的 `config_hash` 计算,使挂载源或模式变更后,既有容器在复用前被判定为配置失配而重建(与 workspace 挂载源一致的复用安全)。该宿主源路径 MUST 先经 `is_blocked_mount` 校验:落在敏感根(`~/.ssh`、`/etc`、`/root` 等)下的源 MUST 被拒绝挂载,不创建带该挂载的容器。

#### Scenario: 挂载源变更触发重建
- **WHEN** 某 scope 已有容器,随后 skills 挂载的宿主源路径(或只读/可写模式)发生变化,再次获取该 scope 容器
- **THEN** 既有容器因 config_hash 失配被销毁重建,新容器挂载新的 skills 源

#### Scenario: 敏感根下的 skills 源被拒
- **WHEN** 解析出的 skills 宿主源路径落在 `is_blocked_mount` 命中的敏感根下
- **THEN** 拒绝以该源创建挂载,返回明确错误,不创建带该挂载的容器

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

