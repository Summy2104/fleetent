## ADDED Requirements

### Requirement: 目标 package 结构为权威定义

`docs/architecture.md` SHALL 把张洋负责能力域的目标 package 结构记录为权威目标:`runtime/`、`model/`、`tools/`、`skills/`、`session/` 各为独立能力包,`sandbox` 位于 `integrations/sandbox/`。这是定义本身(本蓝图交付),不要求代码此刻已达成。

#### Scenario: 架构文档列出目标结构
- **WHEN** 查阅 `docs/architecture.md` 的目标 package map
- **THEN** 其中列出上述 7 个能力包归属,且 sandbox 明确归 `integrations/sandbox/`

### Requirement: 迁移约定为强制规范

后续逐包迁移 SHALL 遵守以下约定:每个能力域是一个 package 且公共 API 收口于 `__init__.py`;跨包只 import 公共 API、不引用另一包内部模块;迁入时去冗余前缀命名(对齐 `mcp/client.py`);迁移期旧扁平路径的 re-export shim 不承载业务逻辑。这些约定自本蓝图确立起对所有逐包迁移 change 生效,并在其 review 中被检查。

#### Scenario: 逐包迁移 change 符合约定
- **WHEN** 任一逐包迁移 change 实现完成、提交 review
- **THEN** 其新增 package 带 `__init__.py` 公共 API、无跨包内部 import、命名已去前缀、旧路径 shim 仅 re-export

### Requirement: 迁移为行为不变的纯结构搬迁

本系列每个迁移 SHALL 是纯结构搬迁,不改变运行时行为、公共契约或数据库 schema。

#### Scenario: 迁移前后行为一致
- **WHEN** 任一逐包迁移完成
- **THEN** 全量测试(`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q`)在其前后均通过,且无 schema 变更
