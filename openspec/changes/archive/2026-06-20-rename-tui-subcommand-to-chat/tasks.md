## 1. 改命令名 tui → chat

- [x] 1.1 [测试] `tests/unit/test_main_subcommands.py`:把 `test_tui_subcommand_dispatches` 改/加为 `test_chat_subcommand_dispatches`(`argv=["chat","--help"]` 懒加载 `tui.app` 转发);断言 `fleetent tui` 不再被识别为客户端入口 → 红
- [x] 1.2 [实现] `__main__.py`:`if argv and argv[0] == "tui":` → `"chat"`
- [x] 1.3 [实现] `tui/app.py`:`ArgumentParser(prog="fleetent tui")` → `prog="fleetent chat"`;docstring 第 1 行 `(fleetent tui)` → `(fleetent chat)`
- [x] 1.4 [验证] `uv run pytest tests/unit/test_main_subcommands.py -x -q` → 绿;`fleetent chat --help` usage 显示 `fleetent chat`

## 2. 下游同步(脚本 / 文档 / 测试)

- [x] 2.1 [实现] `scripts/install-agent.sh`(2 处)、`scripts/install.sh`(1 处):`fleetent tui --url ...` → `fleetent chat --url ...`
- [x] 2.2 [实现] `tests/integration/test_install_agent_script.py`、`test_install_script.py`:断言串 `fleetent tui --url ...` → `fleetent chat --url ...`
- [x] 2.3 [实现] `README.md`(2 处)、`AGENTS.md`(1 处)、`.env.example`(注释):`fleetent tui` → `fleetent chat`
- [x] 2.4 [验证] `uv run pytest tests/integration/test_install_agent_script.py tests/integration/test_install_script.py -x -q` → 绿

## 3. 收尾验证

- [x] 3.1 [验证] `make test-pr` → 全绿
- [x] 3.2 [验证] `uv run pytest tests/integration -q` → 对照 main 基线无新增失败
- [x] 3.3 [验证] `make test-unit-ci` → unit 覆盖率 ≥ 76%
- [x] 3.4 [验证] `git grep -n "fleetent tui" -- src tests scripts README.md AGENTS.md .env.example openspec/specs` → 无残留(内部 `tui/` 包名、`FLEETENT_TUI_*` env、`tui-gateway` spec 名保留,不在此列)
- [x] 3.5 [验证] `openspec validate rename-tui-subcommand-to-chat`;archive 后 `opsx:verify` 确认 4 个 spec 与实现一致
