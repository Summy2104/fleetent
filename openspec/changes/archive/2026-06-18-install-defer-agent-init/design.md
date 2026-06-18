## Context

`scripts/install-agent.sh` 当前流程：`parse_args`（**agent-id 必填**）→ `ensure_uv` → `check_python` → `install_tool`（`uv tool install --force --from . fleetent`）→ `setup_home_env`（设并持久化 `FLEETENT_HOME`）→ `init_agent`（跑 `fleetent agent init <id>`）→ `precheck_docker` → `print_success`（含运行步骤）。

`scripts/install.sh`（开发者一键、editable）：`install_editable` → platform 分支（`install-platform.sh --skip-db` + 自己跑 alembic）→ agent 分支（`bash install-agent.sh "$AGENT_ID"`，靠它 scaffold 默认 agent）→ 结尾提示。它有 `--agent-id`（默认 `default`）。注意：agent 分支调 `install-agent.sh` 的 `install_tool` 会以 `--from .`（非 editable）覆盖前面的 editable 安装——本次改动顺带消除这一隐患。

`scripts/install-platform.sh` 独立、不改。

## Goals / Non-Goals

**Goals:**
- `install-agent.sh` 只装 runtime + 设 home + 环境探测，**不 init agent**，结尾打印创建 agent 的教程。
- 去掉 `install-agent.sh` 的必填 agent-id 位置参数（仅 `--dir`）；传入位置参数时报错提示已移除。
- `install.sh` 不再 seed 默认 agent home，agent 分支也只装+给教程；移除 `--agent-id`。
- 两脚本幂等；platform 链路不受影响。

**Non-Goals:**
- 不改 `install-platform.sh`、不改 `fleetent agent init` 命令本身、不改任何 `src/` 代码。
- 不重命名脚本。
- 不改 DB/配置模板/uv 装载等其它 install-bootstrap 行为。

## Decisions

1. **install-agent.sh**：删 `AGENT_ID` 变量与其在 `parse_args` 的位置参数解析；位置参数出现时 `log_error`「agent-id 参数已移除，用 fleetent agent init 创建」+ usage + 非零退出。删 `init_agent` 调用。`print_success` 改为打印四步教程（init/编辑/run/tui）。`usage()` 同步更新（签名 `[--dir PATH]`，去掉 agent-id 说明，加创建 agent 指引）。保留 `ensure_uv`/`check_python`/`install_tool`/`setup_home_env`/`precheck_docker`。
2. **install.sh**：删 `--agent-id` 与 `AGENT_ID`；agent 分支不再 `bash install-agent.sh "$AGENT_ID"`（避免 `--from .` 覆盖 editable，也不再 seed 默认 agent）。agent 分支收敛为：确保 `FLEETENT_HOME` 后打印同一份创建 agent 教程（runtime 已由 `install_editable` 装好）。结尾汇总仍说明 editable + 状态目录。
3. **教程文本共享**：两脚本打印同一段四步教程。可各自内联（脚本独立、不引依赖），文案保持一致。
4. **幂等**：去掉 init 后，install-agent.sh 重复运行只是重装 binary + 重设 home，天然幂等。

## Risks / Trade-offs

- **BREAKING（部署脚本接口）**：`install-agent.sh <agent-id>` 旧用法失效。缓解：位置参数显式报错并指引 `fleetent agent init`；帮助/教程说明。文档（README/部署文档）若示例 `install-agent.sh <id>` 需同步更新（纳入 tasks）。
- **install.sh editable 隐患修复**：移除嵌套的非-editable 安装是顺带的正向修复，但改变了 install.sh agent 分支行为——以测试锁定 install.sh 完成后不产出默认 agent home。
- **测试形态**：install 脚本的现有测试可能 assert「默认 agent home 存在」「缺 agent-id 退出」——需反转为「不产出 agent home」「教程文本存在」「传位置参数报错」。先红后绿。
- 纯脚本+spec 改动，无 src 影响；`make test-pr`（unit 层）大概率不覆盖脚本行为，主要靠 install 相关 integration/doc 测试 + 脚本 `bash -n`/实跑 dry。
