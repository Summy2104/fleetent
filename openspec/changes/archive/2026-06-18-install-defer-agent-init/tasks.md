# Tasks

> 纯部署脚本 + spec 改动，无 src 代码。TDD：先改/写测试见红 → 改脚本见绿。脚本改动另跑 `bash -n` 语法校验。

## 1. install-agent.sh：去 agent-id + 去 init + 教程（测试先行）

- [x] 1.1 定位/梳理 install-agent.sh 的现有测试（若有专属测试文件如 `tests/integration/test_install_agent_script.py`；否则在 install 测试中）。写/改测试断言新契约：无位置参数运行 → 装 binary + 设 FLEETENT_HOME + **不产出** `agents/<id>/` home + 退出 0 + 输出含教程关键词（`fleetent agent init`、`agent run`）；传位置参数 `install-agent.sh some-id` → 非零退出 + usage 含"agent-id 已移除"；不跑 alembic。先见红。
- [x] 1.2 改 `scripts/install-agent.sh`：`parse_args` 删 agent-id 位置解析（出现位置参数→报错+usage+exit 2）；删 `init_agent` 调用；`print_success`→四步教程；`usage()` 改签名 `[--dir PATH]` + 创建 agent 指引。`bash -n scripts/install-agent.sh` 通过。跑 1.1 见绿。

## 2. install.sh：去默认 agent seed + 去 --agent-id（测试先行）

- [x] 2.1 改 `tests/integration/test_install_script.py`：从 `SUPPORTED_FLAGS` 去掉 `--agent-id`；`test_help_*` 不再要求 `--agent-id`；删/改 `test_agent_id_flag_targets_named_agent`；`test_full_run_*` / `test_agent_only_*` 断言**不再产出默认 `agents/default/` home**、改为输出含创建 agent 教程；platform/db/editable/幂等等用例保持。先见红。
- [x] 2.2 改 `scripts/install.sh`：删 `--agent-id`/`AGENT_ID`；agent 分支不再 `bash install-agent.sh "$AGENT_ID"`，改为确保 home + 打印教程（不重装 binary，保留 editable）；`usage()` 去掉 `--agent-id`。`bash -n scripts/install.sh` 通过。跑 2.1 见绿。

## 3. 文档同步

- [x] 3.1 检索并更新仓库内示例 `install-agent.sh <agent-id>` / "默认 agent home" 的文档（README / docs/deployment / install 相关），改为"装运行时后 `fleetent agent init <id>`"。`tests/integration/test_deployment_docs.py` 等 doc 测试若断言旧文案则同步。

## 4. 收尾验证

- [x] 4.1 `make test-pr` 全绿；`uv run pytest tests/integration/test_install_script.py -q`（及 install-agent 专属/doc 测试）无新增失败。
- [x] 4.2 实跑冒烟（隔离 HOME，不污染真实 ~/.fleetent）：`FLEETENT_HOME=$(mktemp -d) bash scripts/install-agent.sh` → 确认无 `agents/` 产物、输出教程；`bash scripts/install-agent.sh x` → 非零+usage。
- [x] 4.3 标记所有 checkbox 为 `[x]`，准备 archive。
