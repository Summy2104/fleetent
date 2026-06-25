# skill-user-access Specification

## Purpose
为 agent 侧提供 per-skill 的用户访问白名单:agent 挂载的某些 skill 只允许特定用户访问/使用,使用同一 agent 的其他用户既看不到也用不了。受限 skill 仅在私聊(DM)中对白名单用户开放,并在 catalog、`read_skill`、沙箱 skill 视图三层闭合。纯 agent 侧、零 platform 依赖、无新表无迁移。

## Requirements
### Requirement: per-skill 用户访问白名单配置

`AgentFile` MUST 支持 `skill_user_access` 配置:一个从 skill 名到允许 user_id 列表的映射(agent.yaml)。一个出现在该映射中的 skill 为**受限 skill**;未出现的 skill 为**公开 skill**,对该 agent 的所有用户可见可用(向后兼容)。`skill_user_access` 缺省为空映射,缺省时所有 skill 皆公开、行为与未引入本特性时完全一致。身份使用 IM 原生 user_id(与连接器 `access.allow_users` 同源)。

#### Scenario: 空配置时所有 skill 公开
- **WHEN** agent 未设置 `skill_user_access`(或为空)
- **THEN** 每个 skill 对所有用户在清单、`read_skill`、脚本执行三层均可见可用,行为与未引入本特性一致

#### Scenario: 配置使 skill 受限
- **WHEN** agent.yaml 的 `skill_user_access` 把 skill `X` 映射到 `[Ua, Ub]`
- **THEN** `X` 成为受限 skill,仅 `Ua`/`Ub` 在私聊中可访问,其余用户不可见不可用

### Requirement: 受限 skill 的可见性判定(含 DM-only)

系统 MUST 提供单一的可见性判定:给定 skill 名、请求者 user_id、chat_type 与 `skill_user_access`,判断该 skill 是否对该请求可见。公开 skill 对任何用户、任何 chat_type 可见。受限 skill MUST 仅在**私聊(DM)**且请求者 user_id 在其白名单内时可见;在频道/群聊(chat_type 非 dm)中,受限 skill MUST 对所有用户不可见。catalog 渲染、`read_skill` 加载、会话 skill 视图构建三处 MUST 复用同一判定。

#### Scenario: 授权用户私聊可见
- **WHEN** 受限 skill `X` 白名单含 `Ua`,`Ua` 在私聊中
- **THEN** 判定为可见

#### Scenario: 非授权用户私聊不可见
- **WHEN** 受限 skill `X` 白名单不含 `Uc`,`Uc` 在私聊中
- **THEN** 判定为不可见

#### Scenario: 频道中受限 skill 对所有人不可见
- **WHEN** 受限 skill `X`,任一用户(含白名单内用户)在频道/群聊中
- **THEN** 判定为不可见(受限 skill 仅私聊提供)

#### Scenario: 公开 skill 不受影响
- **WHEN** skill `Y` 不在 `skill_user_access` 中,任一用户、任一 chat_type
- **THEN** 判定为可见

### Requirement: catalog 按用户过滤受限 skill

注入 `<available_skills>` 清单时,系统 MUST 对每个候选 skill 应用可见性判定(基于当前请求者 user_id + chat_type + agent 的 `skill_user_access`),不可见的 skill MUST NOT 出现在该请求的清单中。公开 skill 的渲染不受影响。

#### Scenario: 受限 skill 不进无权用户的清单
- **WHEN** 非授权用户 `Uc` 发消息,触发 catalog 注入,存在受限 skill `X`
- **THEN** `X` 不出现在 `Uc` 这条请求的 `<available_skills>` 中

#### Scenario: 授权用户私聊清单含受限 skill
- **WHEN** 授权用户 `Ua` 在私聊发消息,触发 catalog 注入
- **THEN** 受限 skill `X` 出现在 `Ua` 的清单中

### Requirement: read_skill 按用户拦截且不暴露存在性

`read_skill` 与 `read_skill_file` MUST 在加载前应用可见性判定(基于 `tool_context` 携带的请求者 user_id + chat_type + agent 的 `skill_user_access`)。对不可见的受限 skill,MUST 返回与"无此 skill"**逐字一致**的中性错误文本,MUST NOT 返回其内容,MUST NOT 以任何可区分的方式暴露该 skill 的存在。

#### Scenario: 非授权用户按名加载被中性拒绝
- **WHEN** 非授权用户对受限 skill `X` 调用 `read_skill("X")`(或带 file_path)
- **THEN** 返回与"无此 skill"完全相同的错误文本,不返回任何内容

#### Scenario: 授权用户私聊正常加载
- **WHEN** 授权用户在私聊对 `X` 调用 `read_skill`
- **THEN** 正常返回 `X` 的内容

#### Scenario: 频道中受限 skill 加载被中性拒绝
- **WHEN** 任一用户在频道中对受限 skill `X` 调用 `read_skill`
- **THEN** 返回与"无此 skill"完全相同的错误文本
