## ADDED Requirements

### Requirement: platform 只读 agent 侧库

platform 控制面 SHALL 经**只读连接**读 agent 侧物理库（per-agent / KB / 共享记忆），MUST NOT 写它们、MUST NOT 要求 agent 把数据反向推送/写入 platform 库（禁物化副本）。router SHALL 提供**只读模式句柄（mode=ro）**供 platform 使用。该只读 open **MUST NOT 触发 migrate**——现有 `open_kb_db` / `open_state_db` / `open_shared_memory_db` 是 migrate-on-open（会写 `user_version`），platform 投影 **MUST NOT 复用它们**，须走单独的不迁移只读 open（迁移只属 agent 写侧 / 部署侧）。

#### Scenario: 只读打开 agent 库

- **WHEN** platform 读某 agent/主体的库
- **THEN** 经 router 的只读句柄打开，结构上写不进去

#### Scenario: 只读 open 不迁移

- **WHEN** platform 只读打开一个 agent 库
- **THEN** 不执行任何 migrate（不改 `user_version`、不建/改表）；若库版本与代码不符，只读路径按现状读、把迁移留给 agent 写侧/部署侧，不在投影路径写库

#### Scenario: 读停机 agent 的历史

- **WHEN** 目标 agent 进程未运行
- **THEN** platform 仍能只读其库文件取历史（不依赖 agent 在跑）

### Requirement: 经共享读函数 + registry 发现

platform SHALL 经 **agent 侧 store 的共享只读查询函数**读取（不手写 SQL，schema 随读函数同仓同改），并经 `management.db` registry 发现主体/agent、遍历聚合跨 agent/主体的视图。

#### Scenario: 经读函数而非手写 SQL

- **WHEN** platform 读 agent 侧某 store
- **THEN** 调用该 store 的共享只读查询函数（喂只读连接），而非 platform 内手写 SQL

#### Scenario: registry 遍历聚合

- **WHEN** platform 需跨多 agent/主体聚合（如统计/审批列表）
- **THEN** 经 registry 枚举 → 逐个只读开 → 应用层聚合

### Requirement: 各资源投影语义

approvals 投影 SHALL join 身份（agent 侧不透明 actor → 真实身份经 #4/management 解析）；user memory 投影 SHALL 跨该 user 谈过的 agent 遍历（内容投影可选）；shared memory 投影 SHALL per-tenant 直读。

#### Scenario: approvals 投影解析身份

- **WHEN** platform 投影审批历史
- **THEN** 读 agent 侧 approval_store（只读）+ join 身份解析出"谁批的"（#4 落地后）

#### Scenario: shared memory per-tenant 直读

- **WHEN** platform 投影某主体共享记忆
- **THEN** 只读该主体 `shared_memory.db`，不遍历 agent
