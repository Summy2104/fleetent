## 0. 前置确认

- [ ] 0.1 记录当前基线：相关 unit tests 为 151 个，unit coverage 约 64%，相关全量测试 coverage 约 93%
- [ ] 0.2 确认目标是补齐轻量单元测试，不改生产行为、不新增 CI coverage gate
- [ ] 0.3 确认相关模块统计口径：`fleetent.intelligence`、`fleetent.observability`、`fleetent.memory_layer`、`fleetent.config`、`scripts.upgrade`

## 1. Observability pure aggregation unit tests

- [ ] 1.1 Write failing tests: `observability.performance` 对缺失 / 非法 elapsed、缺失 model/tool name、排序和 percentile 的纯聚合逻辑有 unit 覆盖
- [ ] 1.2 Write failing tests: `observability.usage` 对缺失 tokens、非法 elapsed、unknown model 和过滤容错有 unit 覆盖
- [ ] 1.3 Implement: 补齐测试所需的最小可注入 fixtures 或 helper；不改生产行为
- [ ] 1.4 Verify green: 运行 `uv run pytest tests/unit -x -q`

## 2. Vector provider boundary unit tests

- [ ] 2.1 Write failing tests: HTTP embedding provider 的 request payload、authorization header、dimensions / malformed response 错误分支有 unit 覆盖
- [ ] 2.2 Write failing tests: HTTP rerank provider 的 request payload、rank / score 解析、timeout / malformed response / provider error 有 unit 覆盖
- [ ] 2.3 Implement: 补齐测试；如需抽 helper，仅限 provider 内部纯函数或可注入 client，不改变 public API
- [ ] 2.4 Verify green: 运行 `uv run pytest tests/unit -x -q`

## 3. Reflection and memory decision unit tests

- [ ] 3.1 Write failing tests: reflection finding 过滤、maintenance proposal risk gate、redaction 和 unsupported shared-memory / KB suggestion 不写 User Memory 的边界有 unit 覆盖
- [ ] 3.2 Write failing tests: memory invalid action、跨用户保护、TTL refresh、stale / expired filtering 的轻量单元路径有覆盖
- [ ] 3.3 Implement: 补齐测试；避免 mock 过深导致测试只验证 mock 调用
- [ ] 3.4 Verify green: 运行 `uv run pytest tests/unit -x -q`

## 4. Connector failure branch unit tests

- [ ] 4.1 Write failing tests: Google Drive connector 对 auth failure、unsupported MIME、malformed file metadata、export/download failure 和 archive_missing summary 的 unit 覆盖更完整
- [ ] 4.2 Write failing tests: Confluence connector 对 Cloud auth failure、429 retry exhausted、malformed page payload、scope validation 和 archive_missing summary 的 unit 覆盖更完整
- [ ] 4.3 Implement: 补齐测试；继续使用 fake client，不连接真实 SaaS
- [ ] 4.4 Verify green: 运行 `uv run pytest tests/unit -x -q`

## 5. Coverage measurement and docs

- [ ] 5.1 Verify: 运行相关 unit coverage 命令，确认 scoped unit coverage >= 75%
- [ ] 5.2 Verify: 运行相关全量测试，确认 integration / evaluation 行为未被削弱
- [ ] 5.3 更新 `docs/capabilities/intelligence-roadmap.md`，记录 unit hardening 完成状态和剩余测试策略
- [ ] 5.4 运行 `uv run ruff format src tests`
- [ ] 5.5 运行 `uv run ruff check src tests`
- [ ] 5.6 运行 `uv run mypy src`
- [ ] 5.7 运行 `uv run pytest -x -q`
- [ ] 5.8 运行 `openspec validate 2026-06-02-intelligence-unit-test-hardening --strict`
- [ ] 5.9 运行 `git diff --check`
