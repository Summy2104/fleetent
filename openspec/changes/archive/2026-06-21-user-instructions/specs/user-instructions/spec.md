## ADDED Requirements

### Requirement: 用户指令文件存储
系统 SHALL 为每个 agent 维护一份用户指令文件,路径为 `agents/<agent_id>/user.md`,与该 agent 的 `agent.yaml` 同目录,经 `paths.agent_home_dir(agent_id)` 解析。该文件为 per-agent 共享(同一 agent 的所有用户共用一份),属纯 agent 侧产物,MUST NOT 写入任何 platform 管理表。

#### Scenario: 文件位置解析
- **WHEN** 加载 agent_id 为 `default` 的用户指令
- **THEN** 系统读取 `agents/default/user.md`

#### Scenario: 文件不存在时为空
- **WHEN** `agents/<agent_id>/user.md` 不存在
- **THEN** 加载返回空字符串,不抛异常

### Requirement: 用户指令注入 system prompt 的稳定前缀
系统 SHALL 在组装 system prompt 时,将用户指令内容作为 stable prefix 的一部分注入,位置在 `system_prompt`(或默认 `_SYSTEM`)之后、`<available_skills>` catalog 之前。用户指令 MUST NOT 注入到 per-request 的 `[Long-term context]` 段。当用户指令为空时,注入段整体省略,system prompt 与未引入本特性时完全一致。

#### Scenario: 非空指令注入到前缀
- **WHEN** `user.md` 含「永远用中文简短回答」,且发起一次对话
- **THEN** 组装后的 system message 在基础 system_prompt 之后、skills catalog 之前包含该指令文本

#### Scenario: 空指令不改变 prompt
- **WHEN** `user.md` 为空或不存在,且发起一次对话
- **THEN** 组装后的 system message 不含用户指令段,与未启用本特性时逐字一致

#### Scenario: 不进入 per-request 长期上下文段
- **WHEN** 同一轮对话既注入用户指令又注入 memory/KB 长期上下文
- **THEN** 用户指令出现在稳定前缀,`[Long-term context]` 段不含用户指令内容

### Requirement: 用户指令字符上限截断
系统 SHALL 对注入的用户指令施加字符上限(硬编码常量,建议 4000 字符)。超过上限时,加载在注入侧截断并保留可见省略标记;磁盘原文不被改写。

#### Scenario: 超长内容注入侧截断
- **WHEN** `user.md` 内容超过字符上限,且发起一次对话
- **THEN** 注入 system prompt 的用户指令被截断到上限内并带省略标记,而磁盘 `user.md` 原文保持完整

### Requirement: 用户指令独立于配置缓存
系统 SHALL 在每轮对话组装时直接读取 `user.md` 文件,不经 `AgentConfigIndex` / `AgentFile` 缓存。对 `user.md` 的写入 MUST 在下一轮对话生效,无需重启进程或刷新配置缓存。

#### Scenario: 写入后下一轮生效
- **WHEN** 通过 `/user` 追加一条指令后,在同一进程内发起下一轮对话
- **THEN** 新追加的指令出现在该轮的 system prompt 中

### Requirement: /user 命令查看当前指令
系统 SHALL 支持 `/user`(无参数)命令,回显当前 `user.md` 内容并直接返回给用户,不进入 agent loop、不落入会话历史。当内容为空时,返回「尚未设置用户指令」类提示。

#### Scenario: 查看非空指令
- **WHEN** `user.md` 含内容,用户输入 `/user`
- **THEN** 系统返回该内容作为回执,且不触发一次 agent 对话

#### Scenario: 查看空指令
- **WHEN** `user.md` 为空或不存在,用户输入 `/user`
- **THEN** 系统返回「尚未设置用户指令」类提示

### Requirement: /user <内容> 追加指令
系统 SHALL 支持 `/user <内容>` 命令,将 `<内容>` 作为一行追加到 `user.md` 末尾(已有内容后补换行分隔),采用原子写(`tmp → replace`),并返回追加成功的回执。该命令不进入 agent loop。

#### Scenario: 向空文件追加
- **WHEN** `user.md` 不存在,用户输入 `/user 永远用中文回答`
- **THEN** `user.md` 被创建且含「永远用中文回答」,系统返回追加成功回执

#### Scenario: 向已有内容追加
- **WHEN** `user.md` 已含一行指令,用户输入 `/user 回答要简短`
- **THEN** `user.md` 在原内容之后新增「回答要简短」一行,原有内容保留

### Requirement: /user clear 清空指令
系统 SHALL 支持 `/user clear` 命令,将 `user.md` 清空(内容置空或删除文件),采用原子写或安全删除,并返回清空成功的回执。该命令不进入 agent loop,且对已为空的文件幂等。

#### Scenario: 清空非空文件
- **WHEN** `user.md` 含内容,用户输入 `/user clear`
- **THEN** 后续 `load()` 返回空,系统返回清空成功回执

#### Scenario: 清空空文件幂等
- **WHEN** `user.md` 不存在,用户输入 `/user clear`
- **THEN** 不抛异常,返回清空成功(或已为空)回执

### Requirement: /user 命令跨入口可用
系统 SHALL 在 CLI、Slack、Telegram、TUI 四个入口均支持 `/user` 命令,且四入口的查看/追加/清空语义一致。全部业务逻辑收敛在单一共享函数 `handle_user_command(agent_id, text) -> str | None`;各入口仅在进入 agent loop 之前调用它,返回非 `None` 即把回执返回用户而不跑 loop,返回 `None` 表示非 `/user` 命令、按正常对话处理。

#### Scenario: 共享函数识别非命令
- **WHEN** 调用 `handle_user_command(agent_id, "你好")`
- **THEN** 返回 `None`,表示交由正常对话处理

#### Scenario: 共享函数识别命令
- **WHEN** 调用 `handle_user_command(agent_id, "/user clear")`
- **THEN** 执行清空并返回非 `None` 的回执文本

#### Scenario: IM 入口拦截不落 loop
- **WHEN** 用户经 Slack/Telegram 发送 `/user 永远用中文回答`
- **THEN** normalizer 在进入 agent loop 前拦截、执行追加并回复回执,该消息不触发一次 agent 对话

#### Scenario: TUI 入口可用
- **WHEN** 用户在 TUI 输入 `/user`
- **THEN** `user` 被识别为已知命令并经服务端共享函数返回当前指令内容
