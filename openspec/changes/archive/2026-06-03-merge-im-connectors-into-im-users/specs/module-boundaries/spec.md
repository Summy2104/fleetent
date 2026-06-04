## MODIFIED Requirements

### Requirement: Module-owned data
每张持久化表 SHALL 有且只有一个 owner module。owner module SHALL 定义该表的 migration、store 访问和
public DTO。其他模块 MUST NOT 直接 query 或 mutate 另一个模块 owned table。

IM 相关表 `im_users`、`im_connectors`、`im_channel_allowlist` SHALL 由统一 IM 模块
（`platform/im_gateway_management`）作为唯一 owner module 拥有。该模块同时承载 IM 身份
映射与 connector 凭证，二者刻意置于同一 IM 模块边界内；旧的 `im_user_store` 与各
`im_connector_*` import 路径 SHALL 仅作为 compatibility shim 保留。

#### Scenario: 模块访问其他模块数据
- **WHEN** reflection 需要分析 memory 质量
- **THEN** 它通过 memory 模块 public API 读写 memory 数据，而不是直接对 `memory_items` 发 SQL

#### Scenario: 新表声明 owner
- **WHEN** 一个 OpenSpec change 新增持久化表
- **THEN** 该 change 在 implementation 开始前标明 owning module

#### Scenario: IM 表归属统一 IM 模块
- **WHEN** 任意模块需要读写 `im_users`、`im_connectors` 或 `im_channel_allowlist`
- **THEN** 它通过统一 IM 模块的 public API 访问，而不是直接对这些表发 SQL，也不 import IM 内部实现文件
