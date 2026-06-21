# Tasks

> TDD Hard Gate:每个实现 task 前先写测试并见红,再写实现见绿。测试 task 一律排在对应实现 task 之前。
> 文件级 I/O 测试用 `tmp_path + monkeypatch`(纯 markdown 序列化,非 DB),归 unit;涉及 loop/normalizer/dispatch 协作的归 integration。

## 1. 核心模块:加载 + 截断 + 命令处理

- [x] 1.1 写测试(unit):`load(agent_id)` —— 文件不存在返回空串;读取 `agents/<agent_id>/user.md` 内容;超过 `_USER_MD_MAX_CHARS` 时注入侧截断并带省略标记,磁盘原文不变。用 `monkeypatch` 重定向 agents 目录到 `tmp_path`。
- [x] 1.2 实现 `runtime/user_instructions.py` 的 `load(agent_id) -> str`:经 `paths.agent_home_dir(agent_id) / "user.md"` 读取,缺失返回 `""`,按常量上限截断。
- [x] 1.3 写测试(unit):`handle_user_command(agent_id, text)` 解析分支 —— 非 `/user` 文本返回 `None`;`/user` 无参返回当前内容(空时返回「尚未设置」提示);`/user <内容>` 追加;`/user clear` 清空。
- [x] 1.4 实现 `handle_user_command(agent_id, text) -> str | None`:解析 `/user [...]`,分发查看/追加/清空,返回回执文本或 `None`。
- [x] 1.5 写测试(unit):追加用原子写(`tmp → replace`),向空文件与已有内容追加均正确换行分隔;`clear` 清空且对不存在文件幂等。
- [x] 1.6 实现追加与清空的原子写逻辑(复用 session/manager 的 `tmp → replace` 范式)。

## 2. 注入 system prompt(稳定前缀)

- [x] 2.1 写测试(unit,run_stream 路径同既有 run_stream 单测约定):组装的 system message 在 `system_prompt` 之后、`<available_skills>` 之前包含 `user.md` 内容;`user.md` 为空时该段省略且与基线逐字一致(`_assemble_prompt` 纯函数 + run_stream mock LLM)。
- [x] 2.2 实现:`_assemble_prompt` 增 `user_instructions` 形参,折入 base(`system_prompt` → `[用户指令]` 段 → skills catalog);`run_sync` / `run_stream` 按 `agent_name` 调用 `user_instructions.load` 接入。
- [x] 2.3 写测试:写入后下一轮 run 直接读到新内容(load 每轮读盘,append→load 在进程内即时可见,已由核心单测 + run_stream 注入测试覆盖)。
- [x] 2.4 实现/确认:`load()` 每轮直接读文件,不进 `AgentFile`/`AgentConfigIndex`。

## 3. 入口接线:IM(Slack / Telegram)

- [x] 3.1 写测试(unit,route() mock):`/user ...` 在进入 loop 前被拦截、调用 `handle_user_command`、回复回执,不跑 loop;普通消息照常注入 user.md 到 system 段。
- [x] 3.2 实现:`im_gateway/normalizer.py` route 内,访问门通过后增加 `/user` 拦截分支(容忍前导 @mention);system_content 组装处折入 user.md。

## 4. 入口接线:TUI

- [x] 4.1 写测试(unit):`tui/commands.py` 的 `KNOWN_COMMANDS` 含 `"user"`,`parse_command("/user clear")` 解析为 `Command(name="user", args=["clear"])`。
- [x] 4.2 实现:`KNOWN_COMMANDS` 增加 `"user"`。
- [x] 4.3 写测试(unit):`tui/dispatch.py` 的 `METHOD_USER` 在服务端调用 `handle_user_command`(agent_id 取 `Connection.agent_name`),返回回执;`send` 把 `agent_name` 传入 `run_stream`。
- [x] 4.4 实现:协议层 `METHOD_USER`;`Connection.agent_name`;dispatch 分支;`_stream_run` 传 `agent_name`;ws_gateway 注入 `agent_name`;客户端 `backend.user` + `app.py` `/user` 分支 + `/help`。

## 5. 入口接线:CLI

- [x] 5.1 写测试(unit):CLI 入口处理用户输入前调用 `handle_user_command`,命中 `/user` 命令则输出回执并结束、不跑 loop;非命令照常进入对话。
- [x] 5.2 实现:`__main__.py` 一次性 CLI 进入 `run()` 前接入共享函数(按默认 agent 解析 agent_id)。

## 6. 收尾

- [x] 6.1 跑 `make test-pr`(unit + 层边界 + 改动文件 ruff)全绿(3256 passed)。
- [x] 6.2 跑 `uv run pytest tests/integration -q` 对照 main 基线,无新增失败(2110 passed, 1 skipped, 0 failed)。
- [x] 6.3 `uv run ruff format` + `uv run ruff check` + `uv run mypy src`(改动文件)无新增问题。
