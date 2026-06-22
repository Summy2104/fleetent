## MODIFIED Requirements

### Requirement: 统一开库边界

系统 SHALL 经统一的 `db.py` 边界开库,业务层不得扩散裸 `sqlite3.connect` / `DB_PATH` re-export。开库 SHALL 经底座工厂按连接 URL scheme 选后端(`create_database` / `create_substrate` 升级为"按 scheme 分派"),默认 `sqlite://` → 本地 SQLite 后端(行为同现状)。store 层 SQL SHALL 继续用 named parameters(`:x`),不用 `?` 风格。

#### Scenario: 经边界按 scheme 开库

- **WHEN** 任一 store 经 `db.py` 工厂以连接 URL 开库
- **THEN** 工厂按 scheme 返回对应后端;无 scheme/`sqlite://` 得本地 SQLite 后端

#### Scenario: 不绕过边界

- **WHEN** 检视 store 层
- **THEN** 无新增裸 `sqlite3.connect` / `DB_PATH` re-export;开库统一经 `db.py` 工厂
