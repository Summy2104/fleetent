## Why

agent 挂载的 skill 当前对该 agent 的**所有**用户一视同仁——任何能用这个 agent 的人都能在清单里看到、用 `read_skill` 加载、并经 `run_code` 跑其脚本。运营需要**按用户**限制某些 skill:某个挂载的 skill 只允许特定人访问/使用,同一 agent 的其他人**既看不到也用不了**。本变更在 agent 侧加 per-skill 用户白名单,并把"看不到 / 读不到 / 跑不了"三层都闭合。

## What Changes

- **新增配置 `AgentFile.skill_user_access: dict[str, list[str]]`**(agent.yaml):skill 名 → 允许的 user_id 列表。未列出的 skill = 对所有人开放(空 dict 行为完全不变,向后兼容)。身份用 IM 原生 user_id(与 `im.slack.access.allow_users` 同源);先只支持个人 user_id。
- **受限 skill = 仅私聊(DM-only)**:配了白名单的 skill 视为"受限"。频道(共享会话/容器,无法按人隔离)里受限 skill 对所有人不进清单、`read_skill` 拒绝;只在私聊里按发信人 user_id 放行。
- **catalog 按人过滤**:`available_skills_prompt` 接受当前请求的"可见 skill 判定"(user_id + chat_type 或等价的允许集),受限 skill 对无权用户/频道不渲染进 `<available_skills>`。
- **`read_skill` / `read_skill_file` 按人拦截**:按 `tool_context.principal.user_id` + `session_context.chat_type` 判定;无权访问返回**中性「无此 skill」**错误(不暴露存在性)。
- **run_code 闭合 = 沙箱 skill 挂载源改为 per-session 过滤视图**:挂载点仍 `/workspace/skills`(**不迁独立根、`$SKILLS_DIR` 不变、`SKILLS_DIR` 注入不变、skill 脚本里的 `/workspace/skills` 路径约定不破坏**),但 bind-mount 的**源**从"整个 agent skills 根"换成"该会话授权 skill 的 `.views/<scope_key>/` 硬链接过滤视图"(复用 file-exchange 的 `.views` 视图机制)。视图只含"公开 skill + 该会话用户被授权的受限 skill" → 受限 skill 物理上不在无权用户容器里,`run_code`/`read_file`/`search` 都够不到。

## Capabilities

### New Capabilities
- `skill-user-access`: per-skill 用户访问白名单——agent.yaml 配置、catalog 按 user_id+chat_type 过滤、`read_skill`/`read_skill_file` 按用户拦截(中性提示)、受限 skill 仅私聊(DM-only)。

### Modified Capabilities
- `sandbox-skill-mount`: skill 挂载源从"整个 agent skills 根"改为"该会话的过滤视图"——挂载点 `/workspace/skills` 与 `$SKILLS_DIR` 不变,但只把该会话用户被授权的 skill(公开 skill + 其授权的受限 skill)纳入视图,使无权 skill 物理不可达;沙箱层只接收"允许的 skill 名集合",授权计算留在 skills/runtime。

## Impact

- **owning packages**:`agent_config`(配置字段)、`skills/`(per-user 资格判定 + catalog 过滤 + `read_skill_file` 门控 + 过滤视图构建)、`tools/builtin_tools`(`read_skill` 门控)、`runtime/loop` + `im_gateway/normalizer`(透传 user_id/chat_type)、`integrations/sandbox`(挂载源接入过滤视图)。
- **public API surface**:`available_skills_prompt` 增可选 per-user 入参;`registry` 新增"某 skill 是否对某 user 可见(含 chat_type)"判定 + "构建会话过滤视图(给定允许 skill 名集合)"函数;`read_skill(name, file_path=, tool_context=)` 行为按用户收敛。
- **owned tables**:无。
- **config namespace**:`AgentFile.skill_user_access`(agent.yaml)。
- **cross-module dependencies**:`runtime`/`im_gateway`/`tools` → `skills` public API;`sandbox` 接收 skills/runtime 计算好的"允许 skill 名集合"(不反向依赖、不承载授权逻辑)。纯 agent 运行时,**零 `fleetent.platform.*` import**。
- **async lifecycle**:过滤视图为文件硬链接构建(非长生命周期活资源);若挂载/构建涉及异步资源,遵守 owner-task 契约。
- **与热加载交互**:skill 变更(`refresh_if_changed`/`reload`)或用户 allowlist 变化时,对应会话视图需重建。
- **migration / shim plan**:无表、无迁移;`skill_user_access` 默认空 → 现有部署行为字节级不变。
