## Context

租户 CLI 直写管理库（`tenancy_store.create_tenant` 等），与 HTTP `/admin/tenancy/*` 并行写同一套管理表。HTTP API 已全覆盖。本 change 删 CLI 并把边界原则写进 spec。

## Goals / Non-Goals

**Goals:** 删 5 条租户 CLI（HTTP-only）；固化"业务控制面不得直写管理库"边界原则；收紧 tenancy provisioning spec。

**Non-Goals:** 不动 node/seed/init-config/validate-config（bootstrap 例外）；不动 HTTP API（已就绪）；不改 `tenants`/`teams` schema；不处理 shared-memory（同性质，单独讨论）。

## Decisions

### D1：边界原则——CLI 直写管理库的准入

admin CLI 直写管理库（绕过 server）**仅限**三类：
- **真 bootstrap**：server 起来之前/之外必须能跑（`seed-builtin-admin` 建首个 admin、`init-config`、`validate-config`）
- **基础设施供给**：`agent-node-registry` spec 已界定 node 登记为"先于/独立于平台业务管理"的 ops 入口
- **危险宿主级维护**：`diagnostics` / `maintenance`（宿主上人工跑的低频危险操作）

**业务控制面操作**（租户/团队/审批人/用户归属及同类）MUST 走平台 HTTP API，MUST NOT 有绕过 server 的直写 CLI。判据是"是否必须在 server 之前/之外运行"，不是"有没有 HTTP"。

### D2：删文件而非留空模块

`tenancy.py` 整体删除（上一轮 `im.py`/`agents.py` 留空壳挂在 `_COMMAND_MODULES` 的教训：直接从 import + 元组移除并删文件）。无 re-export 兼容需求。

### D3：测试拆分保留

`test_tenancy_admin.py` 同时有 `*_cli` 与 `test_api_*`。删 `*_cli`（被测命令消失），保留 `test_api_*`（HTTP 是唯一入口，更要测全）。

### D4：tenancy-entities spec 收紧

原「最小 provisioning(admin)」写"admin CLI 或 API"。改为"平台 HTTP API"，去掉 CLI 选项，与边界原则一致。scenario 措辞从"admin 创建主体"保持（不绑定具体入口），实现上经 HTTP。

## Risks / Trade-offs

- **[BREAKING：租户 CLI 消失]** 若有脚本调 `fleetent admin create-tenant`，需改走 HTTP。→ 文档无引用（已 grep）；内网受控。
- **[provisioning 必须 server 在线]** 删 CLI 后建租户需 server + admin session。→ 这正是目标:业务操作走控制面;bootstrap（seed admin）仍是 CLI，链路不断。
