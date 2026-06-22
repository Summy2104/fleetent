## ADDED Requirements

### Requirement: forwarder 地址解析可被环境覆盖

platform 拨 node forwarder 的地址默认 SHALL 为内网 DNS 契约 `<node_id>.internal`（生产内网解析）。
为支持无此 DNS 的部署形态（如单机 dev：所有组件在同一 loopback），地址解析 SHALL 可被环境变量
覆盖：当 override 设置时用之，未设置时回落到默认契约。该覆盖 MUST NOT 改变默认契约行为，也
MUST NOT 改变 forwarder 的 node-key 鉴权与路由语义。

#### Scenario: 默认用内网 DNS 契约

- **WHEN** 未设置 forwarder 地址 override
- **THEN** platform 按 `<node_id>.internal`（既有默认端口）解析 forwarder 地址

#### Scenario: 单机环境用 override 解析

- **WHEN** 设置了 forwarder 地址 override（如指向 `127.0.0.1`）
- **THEN** platform 按 override 解析 forwarder 地址，使无内网 DNS 的单机环境也能拨通 forwarder，
  鉴权与路由行为不变
