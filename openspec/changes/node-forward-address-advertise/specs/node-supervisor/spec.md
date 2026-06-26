## ADDED Requirements

### Requirement: node 心跳上报自身可达地址

node SHALL 支持一个**可选**配置 `FLEETENT_NODE_ADVERTISE_HOST`，声明该 node 对 platform 可达的地址（IP 或主机名；一机一 node，即本机地址）。当该配置非空时，node SHALL 在既有 `POST /nodes/{id}/status` 心跳 payload 中以 `forward_host` 字段上报该地址，供 platform 持久化并用于出站转发寻址（见 `agent-node-registry`）。

该配置未设置时，node SHALL NOT 在心跳中包含 `forward_host`（payload 向前兼容，platform 端寻址回落约定 / override）。地址随每轮心跳上报，使 node 网络地址变更后能自愈刷新。

#### Scenario: 配置了 advertise host 则心跳携带

- **WHEN** node 配置 `FLEETENT_NODE_ADVERTISE_HOST=10.38.8.143` 并发送 status 心跳
- **THEN** 心跳 payload 含 `forward_host: "10.38.8.143"`

#### Scenario: 未配置则心跳不携带

- **WHEN** node 未设置 `FLEETENT_NODE_ADVERTISE_HOST` 并发送 status 心跳
- **THEN** 心跳 payload 不含 `forward_host`（或为空），platform 端寻址回落约定 / override
