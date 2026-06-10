## 1. 修复

- [x] 1.1 Write failing test: `_route_assistant_message` 构造的 NormalizedMessage 携带 `outbound_connectors={"slack": client}`
- [x] 1.2 Implement the one-line fix to pass

## 2. 收尾

- [x] 2.1 `make test-pr` 全绿；integration 对照基线无新增失败
