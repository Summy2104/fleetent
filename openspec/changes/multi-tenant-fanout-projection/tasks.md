## 1. 多主体 fan-out

- [ ] 1.1 写失败测试：路由按 agent 配置 `tenant_id`（`agent_tenant`） 解析到 `<tenant>/`（非 default 硬编码）；T1 agent 够不到 T2 库（跨主体物理隔离）
- [ ] 1.2 实现：`SQLiteTenantBackend` 去 default 硬编码、按真实主体路由；解除"单主体先行"，跑绿 1.1
- [ ] 1.3 写失败测试 + 实现：主体目录 provisioning（router 幂等 lazy 建父目录 / agent_lifecycle 注册）

## 2. platform 只读投影（§7 实现）

- [ ] 2.1 写失败测试：router 提供只读句柄（写入被拒）；读停机 agent 库取历史 OK
- [ ] 2.2 实现：router 只读模式（mode=ro）；agent 侧 store 暴露共享只读查询函数；跑绿 2.1
- [ ] 2.3 写失败测试 + 实现：platform 经 registry 遍历 + 只读读函数聚合（统计/审批列表等）；approvals join 身份、memory 跨 agent、shared per-tenant 直读
- [ ] 2.4 跑既有 platform console/统计测试改走只读投影、行为不变

## 3. 收尾

- [ ] 3.1 依赖护栏：platform 只读 agent（允许）、agent ✗→ platform、agent 物理够不到别主体；不物化副本
- [ ] 3.2 跨主体隔离 + 只读投影端到端 + `make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 基线无新增失败 + `openspec validate multi-tenant-fanout-projection --strict`
