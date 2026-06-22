## Context

`fleetent-tui`(`tui/app.py`)是连远程 `/ws` 的纯瘦客户端,独立 console-script。这条 CLI 合并线的最后一个游离入口。本 change 只挪入口,不碰客户端语义、不碰 `/ws` 服务端、不决定终端渠道形态。

## Goals / Non-Goals

**Goals:** `fleetent-tui` → `fleetent tui` 子命令(行为不变);删孤儿 `observability.py`;作废 remove-tui-client;下游同步。

**Non-Goals:** 不新增本地进程内 REPL(Claude Code 式,deferred);不动 `/ws` 服务端、客户端 UI 逻辑、TUI 协议;不改 env 变量。

## Decisions

### D1:挪入口的机制(对齐 admin/node 模式)

`__main__.py` 加 `if argv and argv[0] == "tui":` 懒加载 `tui.app`,调 `main(argv[1:])`。`tui/app.py` 的 `main()` 改 `main(argv: list[str] | None = None)`,`parser = ArgumentParser(prog="fleetent tui")`,`parser.parse_args(argv)`(None 时 fallback sys.argv)。与 admin_cli/main 的参数化一致。

### D2:直接删 console-script,不留 shim

与 admin/node 的最终态一致(本轮直接删、内网受控)。`fleetent-tui` 入口从 pyproject 删除,BREAKING,文档/脚本同步改 `fleetent tui`。不引入 shim(admin/node 的 shim 上一轮也已删,保持一致)。

### D3:命名用 `tui`,不用 `chat`

本 change 是纯打包合并、deferred 了形态决策。`tui` 是当前实际(远程 WS 客户端),用它最诚实;`chat` 留给未来"本地+远程双形态"那步引入。不在挪入口时就改语义名。

### D4:孤儿 observability.py 一并删

`admin_cli/observability.py` 自 slim 移出 `_COMMAND_MODULES` 后无人 import(已核实),与之前清掉的 `im.py`/`agents.py` 同类。纯死文件删除,无 spec/行为影响。属同一"CLI 入口清理"范畴,作独立 task 组捎上。

### D5:作废 remove-tui-client

该 PARKED change 前提是删 TUI 客户端;本决策相反(保留+挪入口)。其待决问题("终端渠道远程 WS vs 本地 stdio")本 change 仍 defer,但"删客户端"这个具体提案已被否决,删除其 change 目录避免矛盾留存。相关 memory(agent-mgmt-cli-multichannel)另行更新。

## Risks / Trade-offs

- **[BREAKING:fleetent-tui 消失]** 脚本/文档需改 `fleetent tui`。→ 已逐处列入下游同步;内网受控。
- **[误删客户端]** 本 change 保留客户端,易与 remove-tui-client 混淆而误删 app/backend 等。→ design 明确:只挪入口,`tui/` 客户端模块全留。
- **[install 测试]** test_install_*.py 断言装了 `fleetent-tui`;改为只断言 `fleetent`(+ 可选 `fleetent tui --help` 可用)。
