## Context

`fleetent chat`(`tui/app.py`)用 prompt_toolkit:`PromptSession.prompt_async()` 在 `patch_stdout()` 下跑输入行,后台 ws 接收循环把每个 `event` 经 `on_event` → `render.format_event` → `_emit` 打印。

实测(CPR 精确的 pty+pyte harness)复现:agent 回复文本**闪一次即消失**。原始字节确认:文本写出后,prompt 重绘发 `ESC[J`(erase display to end)把它擦掉。

prompt_toolkit 源码佐证:`StdoutProxy._write` 注释——"as long as the newline hasn't been written, the text is again overwritten by the rendering of the input command line; therefore we buffer until a newline"。即**半行(无换行)文本不会被提交到 scrollback**,会被 prompt 渲染覆盖。

## Goals / Non-Goals

**Goals:**
- 流式回复在终端**持久显示**(不被 prompt 重绘擦除),输入行仍可编辑。
- 事件之间不堆多余空行。
- 不改事件协议 / `/ws` / 命令 / 认证。

**Non-Goals:**
- 不追求逐字符流式(按**完整行**刷新即可,语义上等同分块,且可靠)。
- 不把 TUI 改写为全屏 Application(更彻底但是大改,本 change 不做)。
- 不动服务端 dispatch / run_stream。

## Decisions

**D1 — 只 emit 完整行,半行先缓冲。** 根因是半行不入 scrollback。`AppController` 用 `_text_buf` 累积 `text_delta`;`_flush_complete_lines` 只把已含换行的整行 emit、保留尾部半行;`_flush_text(final=True)` 在结构化事件 / `done` 前把残留半行补 `\n` 收尾。结构化事件(自带尾随 `\n`)本就是完整行,直接 emit。

**D2 — emit 经 `run_in_terminal`。** prompt 运行时,`_default_emit` 用 `run_in_terminal(lambda: print_formatted_text(...))`——它挂起 app 渲染、把输出打到 prompt 上方(进 scrollback)、再重绘 prompt。比直写终端(被擦)或 `print_formatted_text(file=sys.stdout)`(经 StdoutProxy,但 print 的显式 flush 会强刷半行、且 raw=False 会乱码)都可靠。非运行态(连接前的状态行)直接 print。

**D3 — 为什么不是 `file=sys.stdout` / 逐 delta run_in_terminal。** 二者实测仍闪(忠实 harness:`samples 0010000…`):前者 print 的 flush 把半行强刷出去被擦;后者逐 delta 仍是半行。改成"完整行 + run_in_terminal"后 `samples 0001111…`(出现即持久)。

**D4 — 结构化事件去前导 `\n`。** 既然 app 层已在结构化事件前 flush 流式行(末尾带 `\n`),render 不需再带前导 `\n`;带了反而在无前文 / 连续结构化事件时堆空行。`done` 不再产文本,收尾由 `_flush_text` 负责,避免末尾空行。

### 模块边界影响(AGENTS.md 要求)

- **owning package**:`tui`(agent 运行时终端客户端)。
- **public API surface**:无变化(`on_event`/`_emit` 注入点签名不变;事件协议、`/ws`、命令不变)。
- **owned tables**:无。**config namespace**:无。
- **cross-module dependencies**:`tui` 依赖 prompt_toolkit + `tui.render`/`tui.backend`(既有);无新依赖,不 import platform。
- **migration / shim plan**:无 schema 迁移、无模块移动、无 shim。

## Risks / Trade-offs

- **非逐字符流式**:回复按完整行(多为一次性)出现,而非逐字。权衡:可靠 > 逐字动画;与 Slack 分块体验一致。
- **测试保真**:终端渲染无法用普通 pty 单测验证(缺 CPR);本 change 的单测锁 emit 序列契约(累积/完整行/无空行),真实渲染靠 CPR 精确 harness + 人工终端确认。emit 序列是渲染正确性的可单测代理。
- **agent 自身的段落空行**保留(是 agent 内容,非渲染瑕疵)。
