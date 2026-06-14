# file-exchange Specification

## Purpose
TBD - created by archiving change unified-file-exchange. Update Purpose after archive.
## Requirements
### Requirement: 每个 stdio MCP server 绑定有效文件根并映射 /exchange 命名空间

系统 SHALL 在启动每个 stdio MCP server 时确定其**有效文件根**（effective file root）并建立逻辑映射 `/exchange/<server_id>/ → <有效文件根>`：server 未显式声明文件位置时，有效文件根 MUST 为约定注入的 `<agent_home>/exchange/<server_id>/data`；server 在 agent.yaml 显式声明了 `XDG_DATA_HOME`（或经可选 `file_root` 显式声明产物目录）时，有效文件根 MUST 为该显式位置（存量树原地收编，零文件迁移）。映射 MUST 在 server 注册时建立，并被 fence 解析、结果路径改写与登记共用同一来源。

#### Scenario: 未配置 server 使用约定根

- **WHEN** agent.yaml 中某 stdio server 未声明 XDG/file_root
- **THEN** 其有效文件根为 `<agent_home>/exchange/<server_id>/data`，`/exchange/<server_id>/a/b.txt` 解析到该目录下 `a/b.txt`

#### Scenario: 显式 XDG 的存量树原地收编

- **WHEN** server 在 agent.yaml 显式声明 `XDG_DATA_HOME` 指向既有 xdg 树
- **THEN** 有效文件根为该显式位置，`/exchange/<server_id>/…` 解析到其中，不发生任何文件迁移

### Requirement: artifacts 台账自动登记工件归属

系统 SHALL 在 agent_state.db 以嵌入式 forward-only 迁移维护 `artifacts` 表，行字段至少含 `{artifact_id, server_id, rel_path, scope_key, session_id, user_id, filename, size, created_at}`。归属/可见性 key `scope_key` MUST 取触发该 MCP 调用的 run 的 **workspace scope key**（`workspace_scope == session` → `session_id`；`== agent` → `agent_name`，与 `/workspace` 同源），并 MUST 经单一 key 派生权威解析。`session_id` 与 `user_id` MUST 记录产生该调用的具体会话与用户，**仅作审计真相，不参与访问判定**。登记 MUST 由系统自动完成（结果改写命中或调用窗口 diff）。台账 MUST NOT 成为模型接口：工具参数与提示中 MUST NOT 要求模型提供 artifact_id，模型仅使用 `/exchange` 路径。

#### Scenario: 迁移自动建表与列追加

- **WHEN** 旧版本 agent_state.db 被新版本进程打开
- **THEN** migrate-on-open 应用 `artifacts` 表创建（v32）与 `scope_key` 列追加（v33）并递增 `PRAGMA user_version`，既有表数据不受影响

#### Scenario: 登记归因到当前 run 的 scope

- **WHEN** scope_key 为 K 的 run 调用某 MCP 工具，调用产生了新文件
- **THEN** 台账新行的 `scope_key` 为 K，且 `session_id`/`user_id` 为该次调用的具体会话与用户

### Requirement: /exchange 路径解析附带归属校验

fence 解析 `/exchange/<server_id>/<rel_path>` 时 SHALL 查台账校验归属：按 `(server_id, rel_path, scope_key=当前 run scope_key)` 命中登记行 → 放行；未命中（无该 scope 归属行或路径未登记）→ MUST 拒绝并返回说明文本，MUST NOT 回退为裸文件系统访问，MUST NOT 退化为"按路径取最新行"。该校验 MUST 对所有 host 侧 file 工具（read_file/write_file/edit_file/search_content/search_files/send_file）的**免审批直跑访问**一致生效。跨 scope 访问的唯一豁免 MUST 是"已经过 permission gate 批准的 `send_im_message` files 投递"（人工批准即跨 scope 授权）。`send_file` MUST NOT 拥有跨 scope 审批逃生口——`send_file` 恒免审批、恒回当前对话发起人、无审批回路，故其解析到跨 scope 工件时 MUST 直接拒绝。无审批回路的 LOW 工具（read/search 等）以及 `send_file` 对跨 scope 工件 MUST 始终拒绝。已登记但 host 文件已不存在时 MUST 返回明确的"工件已不存在"错误而非静默失败。

#### Scenario: 本 scope 工件放行

- **WHEN** scope_key 为 K 的 run 调用 `read_file("/exchange/srv/a.xlsx")`，该文件台账 `scope_key` 为 K
- **THEN** 解析到有效文件根下的真实文件并正常读取

#### Scenario: send_file 跨 scope 工件硬拒绝

- **WHEN** scope_key 为 K2 的 run 调用 `send_file("/exchange/srv/a.xlsx")`，该工件台账 `scope_key` 为 K1（K1 ≠ K2）
- **THEN** 解析直接拒绝并返回说明文本，文件未被发送，且 MUST NOT 因 send_file 而触发审批升级（send_file 无审批回路）

#### Scenario: 跨 scope 工件经 LOW 工具拒绝

- **WHEN** scope_key 为 K2 的 run 经 read_file/search 等无审批回路工具引用台账 `scope_key` 为 K1 的 `/exchange` 文件（K1 ≠ K2）
- **THEN** 解析拒绝并返回指引 send_im_message 审批路径的说明文本，文件未被读取

#### Scenario: 跨 scope 工件经已审批 send_im_message 放行

- **WHEN** scope_key 为 K2 的 run 调用 `send_im_message(target=他人, files=["/exchange/srv/a.xlsx"])`（工件台账 scope_key 为 K1），且该调用已过 permission gate 批准
- **THEN** 工件投递成功——审批本身即跨 scope 授权

#### Scenario: 同路径跨 scope 不串味

- **WHEN** scope_key K1、K2 的 run 各自在同一 `(server_id, rel_path)` 登记过工件，K2 的 run 解析该路径
- **THEN** 命中 K2 自己的归属行（而非按路径取到 K1 的最新行），不发生越权或误拒

#### Scenario: 未登记路径拒绝

- **WHEN** 模型构造一个台账中不存在的 `/exchange` 路径
- **THEN** 解析拒绝，不触达文件系统

#### Scenario: 工件文件已被删除

- **WHEN** 台账行存在但对应 host 文件已被 server 删除
- **THEN** 工具返回"工件已不存在"的明确错误

### Requirement: scope 归属视图维护

系统 SHALL 为每个 scope_key 维护归属视图目录 `<agent_home>/exchange/.views/<scope_key>/`（`scope_key` 与 `/workspace` 同源）：工件登记时 MUST 向归属 scope 的视图目录补硬链接并保持 `<server_id>/<rel_path>` 相对结构；同路径重登记（inode 变化）时 MUST 刷新链接。视图目录 MUST 在容器创建前确保存在（可为空）。硬链接不可建（如有效文件根跨文件系统）时，该 server 的工件消费 MUST 走 staging 降级路径并记录日志，MUST NOT 静默丢失。

#### Scenario: 登记即上架

- **WHEN** scope_key 为 K 的容器已创建并挂载其视图目录，随后一个新工件登记 `scope_key` 为 K
- **THEN** 视图目录内出现硬链接，容器内 `/exchange` 下该文件即时可见

#### Scenario: 跨 scope 物理不可见

- **WHEN** scope_key K1、K2 的容器各自挂载各自视图
- **THEN** K1 的容器内不存在 K2 的任何工件路径

#### Scenario: 跨文件系统降级

- **WHEN** 某 server 的有效文件根与视图目录不在同一文件系统，硬链接失败
- **THEN** 该工件标记走 staging 降级，记录说明日志，后续容器消费经 staging 复制完成

