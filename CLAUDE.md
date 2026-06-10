@AGENTS.md

## Unit 测试边界（速查）

unit 只可覆盖：只读 legacy shim / public API / path constant 级别的代码逻辑。
unit 不得涉及真实 DB file、schema、CRUD 或 store/runtime 协作；禁止 `sqlite3` 建文件、`DB_PATH` 连持久路径、`_init_db()` 建表、`DATABASE_URL=sqlite:///...` 覆盖 DB URL。
