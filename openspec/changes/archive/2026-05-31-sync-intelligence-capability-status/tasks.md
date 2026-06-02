## 1. 文档状态同步

- [x] 1.1 更新 `docs/capabilities/vector-store.md`，标明 foundation 已完成和真实后端缺口
- [x] 1.2 更新 `docs/capabilities/memory.md`，移除旧 JSONL/top-20 现状描述，标明 SQLite semantic store 已完成和质量缺口
- [x] 1.3 更新 `docs/capabilities/long-term-ctx.md`，标明 foundation 已完成和 KB/预算策略缺口
- [x] 1.4 更新 `docs/capabilities/knowledge-base.md`，标明当前只有迁移计划，运行时代码未开始
- [x] 1.5 更新 `docs/capabilities/reflection.md`，标明 foundation 已完成和 report 质量/消费缺口
- [x] 1.6 更新 `docs/capabilities/observability.md`，标明已完成子域和 trace 覆盖缺口
- [x] 1.7 更新 `docs/capabilities/deployment.md`，标明已有部署地基和 on-prem 交付缺口

## 2. 横向信息补充

- [x] 2.1 每个模块补充下一批候选 specs
- [x] 2.2 每个模块补充自动化效果验证缺口
- [x] 2.3 每个模块补充未来服务化 / 独立目录判断

## 3. 验证

- [x] 3.1 运行 `openspec validate sync-intelligence-capability-status`
- [x] 3.2 运行 `openspec validate module-boundaries`
- [x] 3.3 运行 `git diff --check`
