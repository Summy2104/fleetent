## 1. Source organization roadmap

- [x] 1.1 盘点 `src/fleetent` 当前平铺模块、已模块化目录和大文件热点
- [x] 1.2 新增 `docs/architecture/source-module-organization-roadmap.md`
- [x] 1.3 文档写明目标 package map、owner 边界和依赖方向
- [x] 1.4 文档写明迁移优先级、首批实现型 specs 和不提前迁移范围
- [x] 1.5 文档写明 compatibility shim 策略和测试要求

## 2. Spec updates and verification

- [x] 2.1 更新 `openspec/specs/module-boundaries/spec.md`
- [x] 2.2 运行 `openspec validate 2026-06-02-source-module-organization-roadmap --strict`
- [x] 2.3 运行 `git diff --check`
