## 1. 更新架构文档(docs/architecture.md)

- [x] 1.1 把「目标 package map」细化为 7 个能力包:`runtime/`、`model/`、`tools/`、`skills/`、`session/` 各独立,sandbox 明确为 `integrations/sandbox/`;补一句 sandbox 归 integrations 的理由(工具执行后端,与 mcp/connectors 同类)
- [x] 1.2 在迁移规则区补齐本蓝图约定:公共 API 收口 `__init__.py`、跨包只用公共 API、去冗余前缀命名(对齐 `mcp/client.py`)、迁移期 shim 不承载逻辑且迁完统一删
- [x] 1.3 在「当前模块地图」标注其为迁移目标态,并与目标 map 对齐(消除 `integrations/sandbox/` 等文档/代码不一致的表述)

## 2. 固化迁移顺序与后续 change 清单

- [x] 2.1 核对 proposal/design 中的迁移顺序(sandbox → session → skills → model → tools → runtime)与 6 个逐包 change 名一致;无歧义

## 3. 清理重复设计稿

- [x] 3.1 删除 `docs/superpowers/specs/2026-06-03-flat-to-package-refactor-design.md`(等价内容已并入本 change 的 proposal/design)

## 4. 校验

- [x] 4.1 `uv run openspec validate runtime-package-blueprint --strict` 通过
- [x] 4.2 架构文档与本蓝图自洽:无遗留与新结构矛盾的旧目标 map 表述;package 命名/约定与 spec 不变量一致
