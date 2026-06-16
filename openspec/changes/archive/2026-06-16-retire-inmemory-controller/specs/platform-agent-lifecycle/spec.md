## REMOVED Requirements

### Requirement: Start and stop agent processes without monitoring

**Reason**: 进程启停的内存 controller（`AgentController` + `lifecycle_admin_api` 的 `/start`、`/stop`、`/runtime-status`）脆弱（不持久、不监管、platform 重启留孤儿），已被分机编排取代：期望态由声明式 `agent_admin_state.status`（C2 desired-state API 消费）表达，node supervisor（C3）按期望态在 node 本地 reconcile 进程（PID 真相 + 幂等 + 崩溃重拉）。
**Migration**: 启停改为改 agent 的 `status`（enable/disable/archive，见 `agent-lifecycle-toggle`），由 node supervisor 调谐为真实进程；"是否在跑"经 node 的实际态上报（C2 `POST /nodes/{id}/status`）读取，替代 `/runtime-status`。`platform-agent-lifecycle` 的 materialize 相关需求不受影响、继续保留。
