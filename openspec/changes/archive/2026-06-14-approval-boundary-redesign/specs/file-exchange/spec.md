## MODIFIED Requirements

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
