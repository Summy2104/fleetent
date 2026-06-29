## 1. 单租户不变量校验

- [ ] 1.1 写 unit 测试:agent knowledge bindings 含跨 tenant 条目时 load fail loudly(见红)
- [ ] 1.2 写 unit 测试:全部 binding 与 agent tenant 一致时通过,`long_term_ctx` 使用统一 tenant(见红)
- [ ] 1.3 在 agent config 加载 + materialize 两处加单租户校验;`long_term_ctx` 移除"取 `bindings[0]`"的脆弱假设、改用校验后的统一 tenant;跑 1.1–1.2 见绿

## 2. bind/unbind 触发 reconcile 重 materialize

- [ ] 2.1 写 integration 测试:bind/unbind 改 `agent_kbs` 后,受影响 agent 标记需 resync(见红)
- [ ] 2.2 写 integration 测试:reconcile 在该信号下从 `agent_kbs` 重 materialize 出更新后的 `knowledge.bindings`(见红)
- [ ] 2.3 platform bind/unbind 路径接入 resync 信号(复用/对齐既有 `resync_epoch` 范式);跑 2.1 见绿
- [ ] 2.4 node reconcile 在该信号下走 `_write_home` 重 materialize knowledge bindings;跑 2.2 见绿

## 3. session 边界生效

- [ ] 3.1 写 integration 测试:更新后的 bindings 在 agent 下一个 session 边界生效,进行中的对话不变 KB 范围(见红)
- [ ] 3.2 确认 agent 在 session 起点读取(可能已更新的)agent.yaml bindings;跑 3.1 见绿
- [ ] 3.3 写测试/检视:运行时不查询 `agent_kbs`(解耦护栏),无 platform DB 环境下仍可运行

## 4. 收尾验证

- [ ] 4.1 跑 `make test-pr` 与 `make test-integration-ci`,两者全绿(无新增失败)
- [ ] 4.2 ruff format/check 改动文件;module-boundaries 检查通过;`openspec validate kb-binding-reconcile` 通过
- [ ] 4.3 更新 `docs/capabilities/knowledge-base.md` / agent 文档:绑定变更经 reconcile、下个会话生效、单租户不变量(非代码产物,人工确认后再 commit)
