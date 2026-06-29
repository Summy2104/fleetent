## 1. Worker 存活可观测

- [ ] 1.1 写 integration 测试:有活跃 worker(近期有 job claim 推进)时,存活判定为活跃(见红)
- [ ] 1.2 写 integration 测试:无 worker(超过过期阈值无 claim 推进且有 pending)时,存活判定为无活跃 worker(见红)
- [ ] 1.3 实现存活判定(默认 claim-age 启发:查 `kb_ingest_jobs` 的 pending + 最近 `claimed_at` 推进),经 `db.py` 边界、worker ✗→ platform;跑 1.1–1.2 见绿

## 2. admin 非终态状态区分降级

- [ ] 2.1 写 integration 测试:job 入队 + 有活跃 worker 但超时未完成 → 端点返回 `in_progress`/`queued`(见红)
- [ ] 2.2 写 integration 测试:job 入队 + 无活跃 worker → 端点返回 `degraded`(或等价明确标记),可区分于正常排队(见红)
- [ ] 2.3 在 `_wait_for_kb_ingest_job` 超时返回前接入存活判定,产出 in_progress / degraded;不改轮询窗口/超时/入队 seam;跑 2.1–2.2 见绿
- [ ] 2.4 确认未新增任何绕过队列的 in-process ingest 执行路径(检视 + 测试)

## 3. 部署接线

- [ ] 3.1 在容器/compose 形态新增/确认 `kb-worker` 受管常驻服务(与 dockerize-deploy-stack 协同),判定逻辑不依赖启动方
- [ ] 3.2 文档/示例:部署需常驻 kb-worker;无 worker 时导入/同步显示 degraded 的预期

## 4. 收尾验证

- [ ] 4.1 跑 `make test-pr` 与 `make test-integration-ci`,两者全绿(无新增失败)
- [ ] 4.2 ruff format/check 改动文件;`openspec validate kb-ingest-worker-reliability` 通过
- [ ] 4.3 更新 `docs/capabilities/knowledge-base.md` 或 worker 文档:worker 存活可观测 + degraded 语义(非代码产物,人工确认后再 commit)
