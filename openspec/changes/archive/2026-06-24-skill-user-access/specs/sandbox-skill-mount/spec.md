## ADDED Requirements

### Requirement: skill 挂载源为该会话的过滤视图

当 agent 启用 per-skill 用户访问控制(`skill_user_access` 非空)时,沙箱 skill 挂载的**源** MUST 为**该会话的过滤视图**,而非整个 agent skills 根。过滤视图 MUST 只包含该会话**允许的 skill**(公开 skill + 该会话用户在私聊中被授权的受限 skill),由 skills/runtime 计算出"允许的 skill 名集合"后构建(硬链接投影,复用 `.views/<scope_key>/` 视图机制)。挂载点 `/workspace/skills`、只读策略、`SKILLS_DIR=/workspace/skills` 注入 MUST 保持不变。沙箱层 MUST NOT 自行解析授权(只接收允许集合 / 视图路径),授权判定留在 skills/runtime,以维持 agent/sandbox 解耦。`skill_user_access` 为空时,视图 MUST 等价于整个 skills 根(行为与未引入本特性一致)。

#### Scenario: 受限 skill 不进无权会话的视图
- **WHEN** 非授权用户 `Uc` 的会话创建容器,存在受限 skill `X`
- **THEN** 该会话 `/workspace/skills` 视图不含 `X` 的任何文件,容器内 `run_code`/`read_file`/`search` 都读不到也跑不了 `X`

#### Scenario: 授权用户私聊视图含其受限 skill
- **WHEN** 授权用户 `Ua` 的私聊会话创建容器
- **THEN** 视图含公开 skill 及 `Ua` 被授权的受限 skill,`run_code` 可正常执行其脚本

#### Scenario: 频道会话只挂公开 skill
- **WHEN** 频道线程会话(多人共享容器)创建容器
- **THEN** 视图只含公开 skill,受限 skill 一律不在其中

#### Scenario: 空配置等价整根挂载
- **WHEN** agent 未配置 `skill_user_access`,某会话创建容器
- **THEN** 挂载源等价于整个 skills 根,行为与未引入本特性一致

#### Scenario: 挂载点与 SKILLS_DIR 不变
- **WHEN** 使用过滤视图作为挂载源创建容器
- **THEN** 容器内挂载点仍为 `/workspace/skills`,`SKILLS_DIR` 仍为 `/workspace/skills`,skill 脚本的 `$SKILLS_DIR` 路径约定不受影响

### Requirement: 会话 skill 视图随 skill 与白名单变化重建

当 skill 集合发生热加载变更(重扫/reload)或某用户的 `skill_user_access` 白名单变化时,受影响会话的过滤视图 MUST 被重建,使后续容器/请求反映最新的允许集合。视图构建 MUST 幂等(可安全重复构建),会话/容器回收时其视图 MUST 被清理(仅移除链接,不影响真实 skill 文件)。

#### Scenario: 热加载后视图反映新 skill
- **WHEN** 运行期新增一个对某授权用户开放的 skill 并触发重扫,随后该用户会话再创建容器
- **THEN** 视图含该新 skill

#### Scenario: 回收会话清理其视图
- **WHEN** 某会话结束/容器回收
- **THEN** 其 `.views/<scope_key>` 视图目录被清理,真实 skill 文件不受影响
