## MODIFIED Requirements

### Requirement: agents 表是 agent 配置的单一当前态真相源

agent 的全部配置 SHALL 以**当前态**形式存于 `agents` 表的列上,无版本化、无 `active_version_id` 间接层。运行时字段(`system_prompt`、`allowed_tools`、`model_overrides`、`memory_namespace`、`skills_dir`)与 caps 字段(`features`、`plugins`、`allowed_skills`、`config_overrides`、`supports_dm`、`supports_groups`、`icon`)统一住在 `agents` 行内。配置的所有读取方(materialize、credential 槽解析、控制台投影)MUST 直接读 `agents`,不得经任何版本指针解析。

物化时对 `config_overrides` 的合并若校验失败而回退到 base（丢弃 override 以保证 deploy/preview 不崩），系统 SHALL 记录一条可诊断的 ERROR 日志（含 agent 名与具体校验错），MUST NOT 静默丢弃——避免一处无关坏字段（如悬空 model route）静默清空 IM/凭据等其它绑定却无任何信号。

#### Scenario: 编辑配置就地更新 agents 行

- **WHEN** 平台控制台修改某 agent 的 system_prompt / allowed_tools / model_overrides / memory_namespace / skills_dir 或 caps 字段
- **THEN** 系统就地 UPDATE 该 agent 的 `agents` 行,不创建任何新版本、不改任何版本指针

#### Scenario: materialize 从 agents 读全部配置字段

- **WHEN** 平台为某 agent 物化 agent.yaml(直接物化或 node desired-state)
- **THEN** 运行时字段与 caps 字段全部取自该 agent 的 `agents` 行,且物化产物与改动前语义一致

#### Scenario: 无效 config_overrides 回退时记录 ERROR 而非静默

- **WHEN** 某 agent 的 `config_overrides` 与 base 合并后 `AgentFile` 校验失败,物化回退到 base
- **THEN** 系统记录一条含 agent 名与校验错详情的 ERROR 日志,而非静默丢弃 override(该 override 里其它合法绑定如 IM 凭据被连带丢弃这一事实因此可诊断)
