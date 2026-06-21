# Tasks

> TDD Hard Gate:每个实现 task 前先写测试并见红,再写实现见绿。测试 task 一律排在对应实现 task 之前。
> 文件级 I/O 测试用 `tmp_path + monkeypatch`(纯 markdown 序列化,非 DB),归 unit;涉及 loop/normalizer/dispatch 协作的归 integration。

## 1. 核心模块:加载 + 截断 + 命令处理

- [ ] 1.1 写测试(unit):`load(agent_id)` —— 文件不存在返回空串;读取 `agents/<agent_id>/user.md` 内容;超过 `_USER_MD_MAX_CHARS` 时注入侧截断并带省略标记,磁盘原文不变。用 `monkeypatch` 重定向 agents 目录到 `tmp_path`。
- [ ] 1.2 实现 `runtime/user_instructions.py` 的 `load(agent_id) -> str`:经 `paths.agent_home_dir(agent_id) / "user.md"` 读取,缺失返回 `""`,按常量上限截断。
- [ ] 1.3 写测试(unit):`handle_user_command(agent_id, text)` 解析分支 —— 非 `/user` 文本返回 `None`;`/user` 无参返回当前内容(空时返回「尚未设置」提示);`/user <内容>` 追加;`/user clear` 清空。
- [ ] 1.4 实现 `handle_user_command(agent_id, text) -> str | None`:解析 `/user [...]`,分发查看/追加/清空,返回回执文本或 `None`。
- [ ] 1.5 写测试(unit):追加用原子写(`tmp → replace`),向空文件与已有内容追加均正确换行分隔;`clear` 清空且对不存在文件幂等。
- [ ] 1.6 实现追加与清空的原子写逻辑(复用 session/manager 的 `tmp → replace` 范式)。

## 2. 注入 system prompt(稳定前缀)

- [ ] 2.1 写测试(integration):`run_sync` / `run_stream` 组装的 system message 在 `system_prompt` 之后、`<available_skills>` 之前包含 `user.md` 内容;`user.md` 为空时该段省略且 prompt 与基线逐字一致;用户指令不出现在 `[Long-term context]` 段。
- [ ] 2.2 实现:在 `runtime/loop.py` 解析 `system_prompt` 后(loop.py:2188 附近)调用 `user_instructions.load(agent_id)`,将非空指令并入 `_assemble_prompt` 的 base(`system_prompt` → `[用户指令]` 段 → skills catalog)。`run_sync` 与 `run_stream` 两条路径都接入。
- [ ] 2.3 写测试(integration):写入后下一轮 run 直接读到新内容(验证绕开 `AgentConfigIndex` 缓存)。
- [ ] 2.4 实现/确认:`load()` 每轮直接读文件,不进 `AgentFile`/`AgentConfigIndex`。

## 3. 入口接线:IM(Slack / Telegram)

- [ ] 3.1 写测试(integration):`normalizer.route` 收到 `/user ...` 时,在进入 agent loop 前拦截、调用 `handle_user_command`、回复回执,且不落 session、不触发对话(参照 `_match_approval_command` 测试范式)。
- [ ] 3.2 实现:在 `im_gateway/normalizer.py` route 内、`_match_approval_command` 拦截邻近处增加 `/user` 拦截分支。

## 4. 入口接线:TUI

- [ ] 4.1 写测试(unit):`tui/commands.py` 的 `KNOWN_COMMANDS` 含 `"user"`,`parse_command("/user clear")` 解析为 `Command(name="user", args=["clear"])`。
- [ ] 4.2 实现:`KNOWN_COMMANDS` 增加 `"user"`。
- [ ] 4.3 写测试(integration):`tui/dispatch.py` 新增的 JSON-RPC 方法(如 `METHOD_USER`)在服务端调用 `handle_user_command`(agent_id 取连接绑定的 agent),返回回执。
- [ ] 4.4 实现:`tui/dispatch.py` + 协议层新增 `METHOD_USER` 分支,服务端调用共享函数。

## 5. 入口接线:CLI

- [ ] 5.1 写测试(integration):CLI 入口处理用户输入前调用 `handle_user_command`,命中 `/user` 命令则输出回执并结束、不跑 loop;非命令照常进入对话。
- [ ] 5.2 实现:在 CLI agent 入口(`fleetent` run 路径)进入 loop 前接入共享函数。

## 6. 收尾

- [ ] 6.1 跑 `make test-pr`(unit + 层边界 + 改动文件 ruff)全绿。
- [ ] 6.2 跑 `uv run pytest tests/integration -q` 对照 main 基线,无新增失败。
- [ ] 6.3 `uv run ruff format` + `uv run ruff check` + `uv run mypy src` 改动文件无新增问题。
