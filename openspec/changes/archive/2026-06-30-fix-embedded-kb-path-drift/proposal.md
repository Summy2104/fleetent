## Why

`2ac1edae`(move standalone kb home into tenant layout)把嵌入式 KB 物理布局从 `tenants/<t>/kb/{kb.db,kb_vectors.db}` 下移到 `tenants/<t>/kb/data/{...}`。这一刀改了代码、测试、大部分 spec 与文档,但留了两处不一致:

1. **spec 内部漂移**:它更新了 `tenant-scoped-db-routing` 的"KB 文件分组"requirement(→`kb/data/`),却**漏改同文件另两条 requirement**——"可换后端抽象"与"agent 侧 store 连接来自路由"的正文与场景仍写 `<tenant>/kb/kb.db` / `kb/kb_vectors.db`(line 35/39/51/66/72/78/84),与代码、测试(`test_tenant_router.py:77` 断言 `kb/data/kb.db`)及同文件的"KB 文件分组"requirement 自相矛盾。

2. **遗留半截迁移代码**:`tenant_router.ensure_tenant_kb_dir` 仍带一段 legacy 迁移(且有测试 `test_tenant_router.py:169`),只认更早的"租户根扁平"旧址(`tenants/<t>/kb.db`),既不覆盖紧邻的 `kb/` 根旧址(`tenants/<t>/kb/kb.db`)、又不在新 spec 的 clean-break 立场内——半迁移、易误导。

**取 clean-break(用户决定:本地无需保留的数据,旧库文件直接删除)**:不做任何自动数据迁移,把那段半截 legacy 迁移**删干净**,让代码/spec/测试统一成"不迁移";升级前如有需保留数据,运维自行移动或删除旧文件。

## What Changes

- **删除 legacy 迁移代码**:`ensure_tenant_kb_dir` 简化为"幂等建 `kb/data/` 目录"——移除"租户根扁平 → `kb/data/`"的 `Path.replace` 搬迁分支;不新增任何 `kb/` 根迁移。旧址文件保持原地(由运维自行删除)。
- **删除/改写对应迁移测试**:`test_tenant_router.py` 中断言 legacy-flat 自动迁移的用例(:169 起)移除/改写为"clean 建 `kb/data/`、旧址文件不被自动搬迁"。
- **修 spec 漂移**:`tenant-scoped-db-routing` 的"可换后端抽象"与"agent 侧 store 连接来自路由"两 requirement 内所有 `<tenant>/kb/kb.db` / `kb/kb_vectors.db` 更正为 `kb/data/...`;"KB 文件分组"requirement 增一句**显式 clean-break 声明**(legacy 旧址不自动迁移,运维自行处理)。

## Capabilities

### Modified Capabilities
- `tenant-scoped-db-routing`:KB 物理路径全文统一为 `kb/data/`(消除 spec 内部漂移);明确**不自动迁移** legacy 旧址布局(clean-break),`ensure_tenant_kb_dir` 仅幂等 provision `kb/data/`。

## Impact

- **owning area**:`src/fleetent/tenant_router.py`(`ensure_tenant_kb_dir`)+ `tenant-scoped-db-routing` spec + `test_tenant_router.py`。**不碰 standalone 路径解析、不碰 platform**。
- **行为变更**:`ensure_tenant_kb_dir` 不再搬迁任何 legacy KB 文件;新 home 直接在 `kb/data/` 起。**存量含旧址数据的 home 升级后不会自动接管旧数据**——clean-break 的刻意取舍(用户确认无需保留)。
- **owned tables / config / 跨模块依赖 / schema 迁移**:无。
- **测试**:`make test-pr`(含 `test_tenant_router`)+ `make test-integration-ci` 全绿;移除的迁移用例由"clean provision"用例替代。

## 未纳入(另议)
- `kb-service.yaml.example` 补"`data.home`=sqlite 本地后端存储根 / 未来 PG=schema·Qdrant=collection"纪律注释(纯文档)。
- Makefile / docker-compose 把 `tenants/default/kb/` 写死 → 多租户参数化(`TENANT=`)。
