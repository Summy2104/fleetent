# deployment-pilot-install-checklist

## Why

Pilot MVP 需要一份可执行的安装、升级、备份、恢复、健康检查、排障和验收清单，避免真实试用前依赖零散
roadmap 或口头步骤。当前 deployment 文档已有升级、connector、diagnostics 和 observability 命令，但缺少
面向 pilot operator 的顺序化 checklist。

## What Changes

- 新增 `docs/deployment/pilot-install-checklist.md`。
- 在 deployment capability 文档中引用 pilot checklist。
- checklist 覆盖前置条件、配置、secret 边界、升级 / 备份、服务启动、健康检查、KB connector、observability、
  diagnostics、回滚、验收和问题上报。
- 增加文档测试，验证 checklist 包含 Pilot MVP 必要章节、关键命令和 secret 禁止事项。

## 模块边界影响

- owning package：`deployment` 文档能力；不改变 runtime package。
- public API surface：无新增 Python public API。
- owned tables：无新增。
- config namespace：无新增；引用现有 `database_url`、`knowledge_base.*`、`diagnostics.*`、
  `observability.*` 和 connector credential reference。
- cross-module dependencies：文档引用 admin CLI、upgrade script、observability public CLI 和 KB connector
  operations，但不增加代码依赖。
- migration / shim plan：无迁移，无 shim。

## 非目标

- 不生成 docker-compose / installer。
- 不新增 license、secret manager、scheduler 或 UI。
- 不把真实 secret、token、credential 示例写进文档或测试 fixture。
