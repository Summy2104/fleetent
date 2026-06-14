# unify-identity-column-naming

## Why

agent_state.db 全库 10+ 个身份列统一用 `*_user_id` 后缀且语义一致（存 Principal.user_id 字符串：managed=内部 `users.id`、standalone=渠道原生 id、基础设施=`system` 哨兵；无 FK、跨库 opaque），唯独 `approvals.approver_actor` 是命名孤例——它是 R1 时期"Identity 端口落地前不依赖 platform 身份"的刻意命名，该动机已被 #4 identity-port 与 unify-im-identity-mapping 取代；`permission_gate` 内部变量本就叫 `approver_user_id`（写入点 `permission_gate.py:297` 即 `approver_actor=approver_user_id`），列名是唯一落后者。命名不统一徒增理解成本，上线前改名窗口仍开。顺带：`standalone-agent-approval` spec 仍保留「ensure_schema 自愈补列」requirement，但 retire-ensure-schema 已删除该代码（`approval_store.py` docstring 明写 "no ensure_schema"）——预存 spec 漂移一并清理。

## What Changes

- **列改名**：`runtime/agent_state_migrations.py` 在当前最大版本之后追加新版本 `ALTER TABLE approvals RENAME COLUMN approver_actor TO approver_user_id`（SQLite ≥3.25 原生支持；统一 Y 谱系下表形态单一，改名干净；Y 版本闸之外的遗留双列形态库不在处理范围）
- **代码同步**：`governance/approval_store.py`（SELECT 列、named params、dataclass/字典键）与 `governance/permission_gate.py`（写入参数）改用 `approver_user_id`；5 个测试文件同步（`test_approval_store` / `test_permission_gate` / `test_permission_gate_restart` / `test_standalone_approval` / `test_per_agent_approvals_schema`）
- **spec 清理**：`standalone-agent-approval` REMOVED「存量 approvals 表缺 approver_actor 列时 ensure_schema 自愈」（代码已不存在，schema 权威=统一 Y + 版本闸）；ADDED「身份列统一命名与语义」（approvals 审批人列名 `approver_user_id`，语义=Principal.user_id 字符串）
- **文档**（`docs/architecture/data-model.md` §3.3）：
  - 「actor 为不透明标签」措辞改为**统一身份列语义契约**：agent 侧所有 `*_user_id` 列 = Principal.user_id 字符串，命名空间随入口（managed=内部 id / standalone=渠道原生 id / 基础设施=system），无 FK
  - 顺带补四条已裁决的语义注记（同节同改，零额外成本）：`reflection_proposals.target_ref` 多态引用（memory→`memory_items.id`、skill→文件系统 skill 名，完整性由 apply 路径兜底）；`sub_agent_runs.run_id` 与 `traces.run_id` 同命名空间（按 run_id 可取子 agent 完整 trace 树）；库内 `session_id` 为约定引用、无时序保证（approvals 行可先于 `sessions` 索引行存在）；`budget_usage` 的 scope 枚举 `task|session|user|agent`（key 语义随 scope）
- **design 记录决策往返**：本次是对 R1 命名决策的有据回退（动机已被取代），理由链入档防止将来再翻回

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `standalone-agent-approval`: REMOVED ensure_schema 自愈 requirement（代码已随 retire-ensure-schema 移除）；ADDED approvals 审批人列统一命名与语义 requirement

## Impact

- **owning package**：`runtime`（agent_state_migrations 新版本）、`governance`（approval_store / permission_gate）
- **public API surface**：`approval_store` 返回字典/参数键 `approver_actor` → `approver_user_id`（内部协作面；standalone `/approvals` 端点响应字段若含该键需同步并在测试覆盖）
- **owned tables**：`agent_state.db.approvals` 列改名（嵌入式 Y 新版本，forward-only）
- **config namespace**：无
- **cross-module dependencies**：无新增；不触碰 agent/platform 边界
- **migration / shim plan**：Y 新版本 RENAME COLUMN（append 在当前最大版本之后，勿硬编码版本号——v29/v30 已被 typed-scheduled-task-delivery 占用）；不留旧列名兼容（上线前窗口，消费方全在本仓一次改净）
- **相邻切片**：无在跑 change 触碰 governance / agent_state_migrations（knowledge-base-standalone-service 不相干）
