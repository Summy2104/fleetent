## 1. fleetent-tui → fleetent tui 子命令

- [ ] 1.1 [测试] `tests/unit/test_main_subcommands.py` 加 `test_tui_subcommand_dispatches`(`argv=["tui","--help"]` 懒加载 `tui.app` 并转发)+ `test_tui_does_not_load_on_agent_run`(agent run 路径不 import tui.app)→ 红
- [ ] 1.2 [实现] `tui/app.py`:`main(argv: list[str] | None = None)`,`ArgumentParser(prog="fleetent tui")`,`parse_args(argv)`(None fallback sys.argv)
- [ ] 1.3 [实现] `__main__.py` 加 `if argv and argv[0] == "tui":` 懒加载 `from fleetent.tui import app as tui_app`,调 `tui_app.main(argv[1:])`
- [ ] 1.4 [验证] `uv run pytest tests/unit/test_main_subcommands.py -x -q` → 绿;`fleetent tui --help` usage 显示 `fleetent tui`

## 2. 移除 fleetent-tui console-script

- [ ] 2.1 [测试] `tests/unit/test_admin_entrypoint_cleanup.py`(或等价)加断言:`pyproject scripts` 不含 `fleetent-tui` → 红
- [ ] 2.2 [实现] `pyproject.toml` 删 `fleetent-tui` 入口;`uv sync` 生效
- [ ] 2.3 [验证] `uv run pytest <上述测试> -x -q` → 绿

## 3. 删孤儿文件 observability.py

- [ ] 3.1 [测试] `tests/unit/test_admin_cli_commands.py` 加 `test_observability_module_removed`:断言 `admin_cli` 无 `observability` 模块且不在 `_COMMAND_MODULES`(本就不在)→ 红/确认
- [ ] 3.2 [实现] 删 `src/fleetent/platform/admin_cli/observability.py`;`git grep -n "admin_cli.observability\|admin_cli import.*observability"` 确认无引用
- [ ] 3.3 [验证] `uv run pytest tests/unit/test_admin_cli_commands.py -x -q` → 绿

## 4. 下游同步

- [ ] 4.1 [实现] install 脚本:`scripts/install.sh` / `install-platform.sh` / `install-agent.sh` 把 `fleetent-tui --url ...` 改为 `fleetent tui --url ...`;"Installed: fleetent fleetent-tui" 改为 "Installed: fleetent"
- [ ] 4.2 [实现] `tests/integration/test_install_script.py` / `test_install_agent_script.py`:`for c in fleetent fleetent-tui` 改为只 `fleetent`(可加 `fleetent tui --help` 可用性断言);教程断言改 `fleetent tui`
- [ ] 4.3 [实现] `README.md` / `AGENTS.md`:`fleetent-tui` → `fleetent tui`;`.env.example` 注释提示改 `fleetent tui`(`FLEETENT_TUI_URL`/`FLEETENT_TOKEN` env 变量保留)
- [ ] 4.4 [验证] `uv run pytest tests/integration/test_install_script.py tests/integration/test_install_agent_script.py -x -q` → 绿

## 5. 作废 remove-tui-client

- [ ] 5.1 [实现] 删除 `openspec/changes/remove-tui-client/` 目录(前提相反、已被本决策否决)
- [ ] 5.2 [验证] `git grep -ln "remove-tui-client" -- ':!openspec/changes/archive'` 无悬挂引用(memory 另行更新,不在 repo)

## 6. 收尾验证

- [ ] 6.1 [验证] `make test-pr` → 全绿
- [ ] 6.2 [验证] `uv run pytest tests/integration -q` → 对照 main 基线无新增失败
- [ ] 6.3 [验证] `make test-unit-ci` → unit 覆盖率 ≥ 76%
- [ ] 6.4 [验证] `git grep -n "fleetent-tui" -- src tests scripts docs README.md AGENTS.md .env.example` → 无遗漏(仅 docs/archive 历史保留)
- [ ] 6.5 [验证] `openspec validate fold-tui-into-fleetent`;archive 后 `opsx:verify` 确认 agent-runtime-cli / tui-gateway / install-bootstrap / install-agent-script specs 与实现一致
