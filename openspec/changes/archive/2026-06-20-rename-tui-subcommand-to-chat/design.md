## Context

`fleetent tui`(fold-tui-into-fleetent 刚落地)是连远程 `/ws` 的终端客户端。`tui` 是 UI 技术名、不直观;`chat` 是交互语义、且是未来双形态统一入口的注定名。趁无外部依赖直接改。

## Goals / Non-Goals

**Goals:** `fleetent tui` → `fleetent chat`(纯改名,行为不变);下游 + spec 同步。

**Non-Goals:** 不改内部 `tui/` 包名、`tui-gateway` capability、`/ws`、`FLEETENT_TUI_*` env 变量;不新增本地形态(deferred);不留 `tui` 别名。

## Decisions

### D1:只改用户可见命令名,实现层保持 `tui`

用户面:`fleetent chat`。实现面:`tui/` 包、`tui-gateway` spec、`/ws`、`FLEETENT_TUI_URL/TOKEN` 全留 `tui` 命名。理由:env 变量/包名改名是独立的 breaking + churn,与"命令名对用户友好"无关。命令名是契约,包名是实现。

### D2:不留 `tui` 别名

`fleetent tui` 刚落地、无外部脚本/用户依赖,直接改名最干净(与 admin/node/tui 的 clean-break 一致)。留别名只会让两个名长期并存。

### D3:spec 用 REMOVE+ADD 表达命令改名

agent-runtime-cli 那条 requirement 标题含命令名(`fleetent tui` 子命令),标题与正文都变——用 REMOVED 旧 + ADDED 新表达,比 MODIFY(标题须匹配)干净。其余 3 个 spec 的 requirement 标题不变、仅正文提及命令处改,用 MODIFY。

### D4:命名前瞻

将来做"本地进程内 REPL"(Claude Code 式)时,作为 `fleetent chat` 的默认本地形态长出来,远程形态保留为 `fleetent chat --remote`(或 `--url/--token`)。本 change 不实现,但 `chat` 名为此预留。

## Risks / Trade-offs

- **[轻 BREAKING]** `fleetent tui` 消失。→ 刚落地无依赖;文档/脚本同步改。
- **[命令名 chat 与包名 tui 不一致]** 用户面 chat、代码面 tui。→ 可接受:命令是契约、包是实现,二者不必同名;注释/docstring 标明即可。
