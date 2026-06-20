## ADDED Requirements

### Requirement: 平台裸启动不依赖 agent 侧 state_db

`uvicorn fleetent.server:app` SHALL 能在干净环境裸启动成功(lifespan 跑完、`/health` 可达),SHALL NOT 依赖 agent 侧 `state_db` 被初始化。平台 lifespan SHALL NOT 执行 agent 侧的 approval reconcile(`reconcile_expired_approvals`)等需要 per-agent `state_db` 的操作——这类操作归 agent 进程 boot(approval 是 agent 侧数据)。

#### Scenario: 平台裸启动成功

- **WHEN** 在未 `set_state_db` 的干净进程里 `uvicorn fleetent.server:app` 启动
- **THEN** lifespan 跑完、`/health` 返回 200,**不抛 `approval_store: state_db not initialized`**

#### Scenario: agent 侧 reconcile 不在平台 lifespan

- **WHEN** 检视平台 lifespan
- **THEN** 不调用 `reconcile_expired_approvals` 等读 per-agent `approval_store` 的操作;过期审批清理由 agent 进程 boot(state_db 已接处)承担
