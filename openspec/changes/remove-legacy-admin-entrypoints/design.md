## Context

`slim-admin-cli` 已落地 main。残留：`im.py`/`agents.py` 空模块、`fleetent-admin`/`fleetent-node` shim、以及 agent-runtime-cli spec 缺新入口覆盖。本 change 收口。

## Goals / Non-Goals

**Goals:** 删空模块 + 删 shim（本轮，无宽限期）+ 同步下游测试/spec + 补 agent-runtime-cli 入口 spec。

**Non-Goals:** 不改 `__main__.py` 的 admin/node 分发逻辑（已正确）；不动 `fleetent-tui`（独立 change）；不删仍 CLI-only 的管理/维护命令。

## Decisions

### D1：shim 本轮删除，确认内部已迁移

shim 删除是 BREAKING。前置确认：slim-admin-cli 已把 `Makefile`、`scripts/install*.sh`、`README.md`、`AGENTS.md`、`docs/` 全部从 `fleetent-admin` 迁到 `fleetent admin`。apply 时先 `git grep -n "fleetent-admin\|fleetent-node" -- ':!openspec/changes'` 复核：除本 change 要删的 pyproject/_shims/测试外，不应有功能性残留（remove-tui-client 的 artifacts 除外，那是另一条线）。

### D2：空模块直接删文件，不留 shim

`im.py`/`agents.py` 的 `register()` 已空、`handle()` 返回 False，无任何命令。直接从 `_COMMAND_MODULES` import 列表与元组移除，删文件。无 re-export 兼容需求（它们从来不是 public API）。

### D3：补 agent-runtime-cli spec —— 修 slim 的 drift

slim 的 agent-runtime-cli delta 里「`fleetent admin` 子命令组 / `fleetent node start`」ADDED requirement 未被 apply 合并，致这两个正规入口当前零 spec 覆盖。本 change 借删 shim 之机补上（不含 shim requirement，因为 shim 正被删）。这样 spec 与"删 shim 后唯一入口是 `fleetent admin`/`fleetent node start`"一致。

### D4：测试反向对齐

- `test_shims.py`：删（被测对象消失）。
- `test_admin_entrypoint_cleanup.py`：把"`fleetent-admin` 指向 shim"的断言改为"`fleetent-admin`/`fleetent-node` 不在 `pyproject scripts`"；保留"legacy `fleetent.admin` 模块不可导入"断言。
- `test_deployment_docs.py`：相关断言随文档现状更新。

## Risks / Trade-offs

- **[BREAKING：旧命令立即消失]** 外部若仍有脚本调 `fleetent-admin`/`fleetent-node` 会硬失败、无迁移提示。→ 内部已迁移（D1 复核）；内网受控、用户面可控。
- **[install-bootstrap 与 remove-tui-client 重叠]** 两 change 都改安装清单。→ 本 change 先落地，remove-tui-client 解封时 rebase。
