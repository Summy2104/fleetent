## 1. KB 级 extraction_enabled 开关

- [ ] 1.1 写 integration 测试:嵌入式迁移后 `knowledge_bases` 有 `extraction_enabled` 列、默认 0(见红)
- [ ] 1.2 在 `core/migrations.py` 追加嵌入式 forward-only 迁移加列(版本号取末尾下一个整数,勿硬编码);跑 1.1 见绿
- [ ] 1.3 KB 定义/创建路径支持设置 `extraction_enabled`(读写),unit/integration 覆盖

## 2. ingest 后 opt-in 入队 extraction

- [ ] 2.1 写 integration 测试:开启的 KB ingest 后入队一条 `extraction` job(payload 含 document_id),不阻塞 ingest(见红)
- [ ] 2.2 写 integration 测试:未开启的 KB ingest 后不入队任何 extraction job(见红)
- [ ] 2.3 写 integration 测试:re-ingest 覆盖开启 KB 的文档 → 删旧+插新后为新 document 重新入队 extraction(见红)
- [ ] 2.4 实现 ingest 完成后按 `extraction_enabled` 经既有入队 seam 写 `extraction` job(worker ✗→platform,经 db.py);跑 2.1–2.3 见绿

## 3. worker 消费 extraction job

- [ ] 3.1 写 integration 测试:有 `extraction` job + worker 在跑 → 调 run_entity_extraction 写 entities/mentions/relations、置 done(见红)
- [ ] 3.2 写 integration 测试:extraction job 失败达上限 → 文档 chunks 仍可 search,图谱仅缺该文档实体,无致命错误(见红)
- [ ] 3.3 worker 增加 `extraction` job_type 分支调 run_entity_extraction,沿用既有 claim/done/retry;跑 3.1–3.2 见绿
- [ ] 3.4 确认抽取走 model policy `kb_extraction` task 的 HTTP route;测试用 stub/deterministic extractor,不接真实 LLM;确认无硬编码云默认

## 4. 收尾验证

- [ ] 4.1 跑 `make test-pr` + `make test-unit-ci`(含 76% 覆盖率关)+ `make test-integration-ci`,判"对照 main 基线无新增失败、覆盖率不破 76"
- [ ] 4.2 ruff format/check 改动文件;module-boundaries 检查通过;`openspec validate kb-extraction-auto-enqueue` 通过
- [ ] 4.3 更新 `docs/capabilities/knowledge-base.md`:extraction 按 KB opt-in 自动入队、worker 消费、on-prem 默认自托管抽取模型、默认关(非代码产物,人工确认后再 commit)
