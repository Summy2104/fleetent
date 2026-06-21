## Context

fleetent 的 system prompt 由 `runtime/loop.py` 的 `_assemble_prompt`(loop.py:1432)组装:`agent.system_prompt`(或默认 `_SYSTEM`)+ `<available_skills>` catalog 构成可缓存的 stable prefix;per-request 的 `[Long-term context]`(memory + KB)随后由 `_append_system_context` 追加。命令入口分散在四处,各有不同的命令面:

- **TUI**:`tui/commands.py` 的 `parse_command` 解析 `/cmd`,客户端转成 JSON-RPC 方法,由 `tui/dispatch.py`(服务端)处理(如 `METHOD_SESSION_NEW`)。
- **IM(Slack/Telegram)**:`im_gateway/normalizer.py` 在 route 内用正则拦截命令(范式:`_match_approval_command`,normalizer.py:31 定义、:455 使用)。
- **CLI**:`fleetent "..."` 直接进入 `run_sync` / `run_stream`,当前无斜杠命令面。

agent 目录由 `paths.agent_home_dir(agent_id)` → `agents/<agent_id>/` 解析,`agent.yaml` 即在其中。

## Goals / Non-Goals

**Goals:**
- 新增 per-agent `user.md`,作为用户显式指令注入 stable prefix。
- `/user` 命令在 CLI / Slack / Telegram / TUI 四入口语义一致(查看 / 追加 / 清空)。
- `/user` 的全部业务逻辑收敛在**单一共享函数**,各入口只接命令面,杜绝 4 份重复实现。
- 写入后下一轮对话即生效,无需重启、不依赖 `AgentConfigIndex` 缓存失效。

**Non-Goals:**
- 不做 per-user 隔离(本期 per-agent 共享一份)。
- 不做「删除单条」指令。
- 不与 `memory/` 合并;不改 `prompt-cache-optimization` 与 `memory-layer` 既有要求。
- 不新增 `agent.yaml` 配置项。

## Decisions

### D1:单一共享命令处理函数,各入口接线
新增 `runtime/user_instructions.py`,暴露:
- `load(agent_id: str) -> str` —— 读 `agents/<agent_id>/user.md`,缺失返回 `""`,超限按字符上限截断。
- `handle_user_command(agent_id: str, text: str) -> str | None` —— 解析 `/user [...]`:非 `/user` 命令返回 `None`(交回正常对话);命中则执行查看/追加/清空并返回**给用户的回执文本**。

各入口仅在「正常进入 agent loop 之前」调用 `handle_user_command`,返回非 `None` 即直接把回执回给用户、**不进 loop**:
- **CLI**:入口处理用户输入前先调用,命中则打印回执并结束本次调用。
- **IM**:在 `normalizer.route` 内,紧邻 `_match_approval_command` 的拦截位置增加 `/user` 拦截(命中直接回复,不落 session、不跑 loop)。
- **TUI**:`tui/commands.py` 的 `KNOWN_COMMANDS` 增加 `"user"`;`tui/dispatch.py` 新增一个 JSON-RPC 方法(如 `METHOD_USER`)在**服务端**调用共享函数(文件在服务端,`agent_id` 由连接已知的 agent 绑定提供)。

*备选:在每个入口各写一份解析 —— 否决,违反单一职责且四处易漂移。*

### D2:`user.md` 注入位置 = stable prefix 内,system_prompt 之后、skills catalog 之前
在 `run_sync` / `run_stream` 解析出 `system_prompt`(loop.py:2188 附近)后、调用 `_assemble_prompt` 前,`load(agent_id)` 读取 user 指令,作为独立一段并入 base:

```
base = system_prompt
       + "\n\n[用户指令]\n" + user_md      # 新增,仅当非空
       + "\n\n" + <available_skills>
```

per-agent 共享 → 对该 agent 的所有用户稳定一致,保留可缓存性,符合 `prompt-cache-optimization`「稳定前缀在前」。明确**不进** `_append_system_context` 的 per-request 段,与 `memory-layer` 划清边界。

*备选:放 per-request 段 —— 否决,user.md 稳定,放可变段白白破坏缓存,也与 memory 语义混淆。*

### D3:独立读取,绕开 config 缓存
`user.md` 不进 `AgentFile` / `AgentConfigIndex`,每轮 run 由 `load()` 直接读文件。写入即对下一轮可见,天然规避缓存失效问题。

### D4:原子写 + 追加语义 + 字符上限
- 写采用 `tmp → replace`(复用 `session/manager.py` 的原子写范式)。
- `/user <内容>`:在文件末尾追加一行(已有内容后补 `\n`);`/user clear`:截断为空(或删文件)。
- 字符上限取硬编码常量 `_USER_MD_MAX_CHARS`(建议 4000,对齐 hermes USER.md 量级);`load()` 读取时截断,超限在末尾留可见省略标记。截断只在注入侧,不破坏磁盘原文。

### D5:`agent_id` 由各入口的既有 agent 绑定提供
共享函数以 `agent_id` 为唯一入参。CLI 由运行的 agent 名提供,IM 由 normalizer 已 stamp 的 `agent_name` 提供,TUI 由连接的 agent 绑定提供。无需新增 agent 解析逻辑。

## Risks / Trade-offs

- **[per-agent 共享被误当 per-user]** 一个用户 `/user` 改动影响该 agent 所有用户 → 回执文案明确「这是该 agent 的全局指令」;per-user 留作后续 change。
- **[四入口命令面不一致]** 接线分散易漏某入口 → 业务逻辑全在共享函数,入口只做「拦截→调用→回执」,specs 为四入口各列验收场景,tasks 逐入口 TDD。
- **[超长 user.md 拖垮 prefix / 撑爆缓存]** → D4 字符上限 + 注入侧截断兜底。
- **[并发写]** 同一 agent 多入口/多用户并发 `/user` 追加 → 本期文件级原子写保证不写坏,不保证「追加不丢」(罕见且影响小);如需可后续引入 per-file 锁,本期不做。

## Migration Plan

纯新增,无迁移。无 `user.md` 时 `load()` 返回空、注入段省略,行为与现状完全一致;回滚 = 移除注入与命令接线,残留 `user.md` 文件无副作用。

## Open Questions

无 —— 关键决策(归属粒度 / 与 memory 边界 / 命令命名与形态)已在提案前与用户敲定。
