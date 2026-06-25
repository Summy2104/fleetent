## Context

skill 访问现状:catalog 经 `available_skills_prompt()` 每条消息注入 `<available_skills>`(读模块级 `_index`);`read_skill(name, file_path=, tool_context=)` 按名加载,仅受 `audit_blocked` 门控;skill 脚本经 `run_code` 在 `$SKILLS_DIR=/workspace/skills` 下执行(`_READ_SKILL_GUIDANCE`)。沙箱把宿主 skills 根 ro bind-mount 到 `/workspace/skills`(`manager._resolve_skill_mount()` → `effective_skill_root()` → `SkillMount.host_src`),**对该 agent 所有会话挂的是同一份完整 skills 根**。

身份/会话事实:
- catalog 注入(`im_gateway/normalizer`)与 `read_skill`(`tool_context`)**都能拿到当前请求者**(`msg.user_id` / `principal.user_id`)与 chat_type(`session_context.chat_type`)→ **per-message = per-user,到处可控**。
- 沙箱容器是 **per-session**:DM `session=slack:dm:{user_id}:thread`(=按人);频道 `session=slack:thread:{channel}:thread`(=整线程多人共享一个容器)。
- file-exchange 已有 `.views/<scope_key>/` **硬链接视图** ro 挂载的成熟机制(per-scope 投影)。

约束:agent 运行时 MUST NOT import platform;沙箱不承载授权逻辑(只接收"允许的 skill 名集合");owner-task 异步生命周期;TDD。

## Goals / Non-Goals

**Goals:**
- 受限 skill 对无权用户**看不到(catalog)+ 读不到(read_skill)+ 跑不了(run_code)**,三层闭合。
- 私聊里按发信人精确隔离;频道里受限 skill 对所有人不提供(共享容器无法按人隔离)。
- 未配白名单的 skill 行为完全不变(向后兼容)。
- 纯 agent 侧、零 platform、不破坏 agent/sandbox 解耦、不破坏现有 `$SKILLS_DIR` 路径约定。

**Non-Goals:**
- 不支持 team/group(先只个人 user_id)。
- 不在频道内做 run_code 级按人隔离(架构上共享容器,不可行;受限 skill 限 DM)。
- 不迁移 skills 到独立根、不改 `$SKILLS_DIR`/`SKILLS_DIR` 注入/`_READ_SKILL_GUIDANCE`。
- 不改未配白名单 skill 的任何路径。

## Decisions

### D1:资格判定集中在 registry 一处
新增 `skill_visible_to_user(name, *, user_id, chat_type, access_map) -> bool`:
- skill 无 allowlist(`access_map` 无此名)→ 公开,任何人/任何 chat_type 可见 → True;
- 有 allowlist(受限)→ **仅 DM**(`chat_type == "dm"`)且 `user_id in allowlist` → True;否则 False(频道一律 False)。
`access_map` 即 `AgentFile.skill_user_access`(由调用方解析并传入,registry 不读 agent_config 全局,保持可测/无副作用)。catalog / read_skill / 视图构建三处都走它,判定逻辑只在一处。

### D2:catalog 按人过滤
`available_skills_prompt` 增可选入参(`user_id`、`chat_type`、`skill_user_access`);渲染前对每个候选 skill 调 `skill_visible_to_user`,不可见的不进清单。无入参(默认 None / 空 map)= 现状行为。注入点 `normalizer`/`run_stream` 把 `msg.user_id`+`session_context.chat_type`+`agent.skill_user_access` 传入。

### D3:read_skill / read_skill_file 按人拦截 + 中性提示
`read_skill`(`tools/builtin_tools`)在加载前用 `tool_context.principal.user_id` + `tool_context.session_context.chat_type` + 该 agent 的 `skill_user_access` 调 `skill_visible_to_user`;不可见 → 返回与"无此 skill"**完全一致**的中性错误文本(不区分"不存在"与"无权",避免泄漏存在性)。`read_skill_file` 同此前置判定。access_map 经 tool_context 携带(在 loop 组装 tool_context 时注入,避免 tools 反查 agent_config)。

### D4:DM-only 由 D1 内建
受限(有 allowlist)的 skill 在 `chat_type != "dm"` 时 `skill_visible_to_user` 恒 False → 频道里 catalog 不渲染、read_skill 拒绝、视图不纳入(三处一致)。无需单独的频道分支。

### D5:run_code 闭合 = 沙箱挂载源换成 per-session 过滤视图
- registry 新增 `build_session_skill_view(scope_key, allowed_names, *, skills_dir=None) -> str`:在 `<skills_root>/.views/<scope_key>/` 下,为 `allowed_names` 里的每个 skill **硬链接**其目录内容(复用 file-exchange `.views` 模式),返回该视图目录路径。`allowed_names` = 对该会话用户/chat_type,经 `skill_visible_to_user` 过出的 skill 名集合(公开 + 其授权受限)。
- `manager._resolve_skill_mount()` 的 `host_src` 从 `effective_skill_root()` 改为该会话视图路径:沙箱层接收 runtime 算好的 `allowed_names`(或直接接收已构建的视图路径),**不读 agent_config、不做授权**。挂载点/ro/`SKILLS_DIR` 全不变。
- 视图在该会话首次取沙箱时构建;skill 热加载(`reload`)或用户 allowlist 变化时重建(删旧链接重建,廉价);会话/容器回收时清理视图目录(只删链接)。
- 频道:`allowed_names` 只含公开 skill(受限项被 D1 过滤掉)→ 整线程容器只挂公开 skill。

### D6:身份与 file-exchange scope_key 对齐
视图键沿用沙箱既有 `scope_key`(DM=按用户会话;频道=按线程)。这正是"DM 干净、频道共享"的根因,也使受限 skill 限 DM 成为唯一自洽选择。

## Risks / Trade-offs

- **频道无法按人隔离 run_code** → 受限 skill 限 DM(D4);频道里干脆不提供,语义自洽。
- **视图与热加载/allowlist 变更不同步** → reload/allowlist 变化触发对应会话视图重建;构建是幂等的硬链接重建。
- **硬链接跨文件系统失败** → 与 file-exchange 同约束(skills 根与 .views 同卷);失败回退记录告警,降级为"该会话不挂受限 skill"(fail-closed,宁可少挂不可错挂)。
- **沙箱获得授权语义的风险** → 不会:沙箱只收 `allowed_names`/视图路径,`skill_visible_to_user` 与 access_map 解析都在 skills/runtime,解耦不破。
- **中性提示** → 与"无此 skill"逐字一致,防止经报错差异探测受限 skill 存在性。
- **向后兼容** → `skill_user_access` 空(默认)时:catalog 入参为空 map → 全部可见;视图 `allowed_names` = 全部 skill → 等价整根挂载;行为字节级不变。

## Migration Plan

- 纯增量:一个默认空的 agent 配置字段 + registry 判定/视图函数 + 三处接线。无 DB、无 platform、无迁移。
- 默认空 map → 现有部署零行为变化。回滚 = 移除接线 + 字段。

## Open Questions

无(声明位置=agent.yaml、身份=IM user_id、受限⇒DM-only、中性提示、仅 user_id、不迁根、一个 change——均在 brainstorm 敲定)。
