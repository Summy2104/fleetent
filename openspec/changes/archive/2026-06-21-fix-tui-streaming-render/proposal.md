## Why

实测 `fleetent chat` 终端客户端发现:agent 的流式回复**一闪而过、留不住**——文本短暂出现后被 prompt 重绘擦掉,用户看不到回复。根因:把**半行文本(无换行)**打印到运行中的 `PromptSession` 上方时,partial line 不会提交到终端 scrollback,prompt 下一次重绘的 `ESC[J`(erase-to-end)把它擦掉。

次生问题:工具调用/结果等结构化事件各带一个**前导 `\n`**,在事件之间堆出多余空行。

两者都让终端客户端实际不可用(回复看不见 / 排版脏),而单测只覆盖纯函数 `format_event`,从不驱动真实终端渲染,所以一直没被发现。

## What Changes

- **流式文本按完整行 emit**:`AppController` 累积 `text_delta` 内容,只在遇到换行 / 结构化事件 / `done` 时把**完整行**(带 `\n`)emit 出去;不再 emit 半行。
- **emit 经 `run_in_terminal`**:prompt 运行时,输出经 `run_in_terminal` 提交到 prompt 上方(进 scrollback),而非直接写进 prompt 渲染区被擦除。
- **结构化事件去前导 `\n`**:`render.format_event` 的 tool_call/tool_result/error/approval 不再带前导换行(分隔由 `AppController` 在渲染前 flush 流式行负责);`done` 不再产文本(由 app 层 flush 收尾)。
- **非破坏性**:事件协议、`/ws` 通信、斜杠命令、认证均不变;仅客户端渲染机制改变。

## Capabilities

### Modified Capabilities
- `tui-gateway`:强化「终端 TUI 客户端」的流式渲染要求——流式文本必须**持久显示**(不被 prompt 重绘擦除),且事件间不堆多余空行。

## Impact

- `src/fleetent/tui/app.py` — `_default_emit` 经 `run_in_terminal`;`AppController` 加 `_text_buf` + `_flush_complete_lines`/`_flush_text`;`on_event` 按完整行 emit;`patch_stdout()` 仅兜底 stray 输出。
- `src/fleetent/tui/render.py` — 结构化事件去前导 `\n`;`done` 返回 `None`。
- 测试:`tests/unit/test_tui_app.py`(累积/完整行/无空行)、`tests/unit/test_tui_render.py`(done 无文本、结构化无前导 `\n`)。
- owning package = `tui`(agent 运行时客户端);无表、无迁移、无 API/协议变更。
