# Tasks: kb-cli-verb-grouping

> 纯命令表面重命名 + 分发重构，无行为变更。一刀切、无兼容别名。
> **只改命令调用串（``fleetent` `kb-serve`` 等前缀），不改文件名 `kb-service.yaml` / `kb-service.env.example`。**
> TDD Hard Gate 作用于 §1（分发）：先红后绿。

## 1. 分发重构 + 命令改名（代码）

- [x] 1.1 [test-red] 加/改 `tests/unit` 里 `__main__` 分发测试：断言 `fleetent kb serve|worker|ingest|extract|init-config` 各分派到对应模块 `main`，且旧 ``fleetent` `kb-serve`|kb-worker|kb-ingest|kb-extract|kb-service` **不再被识别**（走到 usage/未知命令）。跑 `uv run pytest tests/unit -k "main or entrypoint or dispatch" -x -q` → **见红**。
- [x] 1.2 [impl] `src/fleetent/__main__.py`：删除 5 处 `if argv[0]=="kb-worker/kb-service/kb-serve/kb-ingest/kb-extract"`，替换为单一 `if argv[0]=="kb":` 块，按 `argv[1:2]` 分派 `serve/worker/ingest/extract/init-config` 到各自 `main(argv[2:])`（对齐现有 `node` 分派写法）；未知/缺子命令打印 `Usage: fleetent kb serve|worker|ingest|extract|init-config` 退 1。跑同命令 → **见绿**。
- [x] 1.3 [impl] 各 KB CLI 模块 argparse 的 `prog=` 用名对齐：`extract_cli.py`（`prog="`fleetent` `kb-extract`"`→`"fleetent kb extract"`）、`ingest_cli.py`、`serve.py`、`worker.py`、`service_init_config.py` 同理。跑 `uv run pytest tests/unit -k "extract or ingest or serve or worker" -q` 见绿。

## 2. Makefile

- [x] 2.1 `Makefile`：`kb-worker` target 命令行 `uv run `fleetent` `kb-worker` …`→`uv run fleetent kb worker …`；`kb-serve` 同理→`kb serve`；`dev-bootstrap` 的 `uv run fleetent `kb-service` `init-config``→`uv run fleetent kb init-config`；`dev-reset` 提示文案里的 `kb-worker`/`kb-serve` 字样一并改（注意：make **target 名**可保留 `kb-worker`/`kb-serve` 不改，只改它们**执行的命令行**——除非你也想改 target 名，本 change 默认不改 target 名以缩小面）。

## 3. 测试全量同步

- [x] 3.1 grep `tests/` 中以 subprocess/argv 调 `kb-serve`/`kb-worker`/`kb-ingest`/`kb-extract`/`kb-service init` 的用例（entrypoint 冒烟 `_entrypoint_smoke.py`、e2e `_kb_helpers.py`/`test_kb_chain.py` 等），改到 `kb <verb>`。直接 `import <mod>.main([...])` 的单测不受命令名影响、不用改。跑受影响 e2e/集成见绿。

## 4. 文档全量同步

- [x] 4.1 逐个改这些 docs 的命令调用示例（`fleetent kb-* → fleetent kb <verb>`，**保留 `kb-service.yaml` 文件名**）：`docs/operations/pilot-runbook.md`、`pilot-install-checklist.md`、`pilot-acceptance-guide.md`、`local-managed-stack.md`、`docs/deployment/compose.md`、`docs/capabilities/knowledge-base.md`、`config-management.md`、`docs/architecture/agent-home-layout.md`、`data-model.md`、`target-architecture.md`、`docs/roadmaps/kb-memory-substrate-roadmap.md`。

## 5. spec 场景串同步

- [x] 5.1 `agent-runtime-cli` 的 delta 已在本 change（``fleetent` `kb-worker``→`fleetent kb worker` 命名要求）。
- [x] 5.2 机械改以下 spec 场景/要求文里的命令调用串到 `kb <verb>`（requirement 行为不变，仅调用串；**保留 `kb-service.yaml` 文件名**）：`kb-standalone-ingest`、`kb-ingest-worker`、`knowledge-base`、`deployment`、`container-deployment`。**不碰** `env-init-commands`（其 `kb-worker init-config` 描述的是已退役命令，属既有 drift）。

## 6. 收尾门禁（全绿才算完）

- [x] 6.1 全库零残留：`grep -rn "`fleetent` `kb-serve`\|`fleetent` `kb-worker`\|`fleetent` `kb-ingest`\|`fleetent` `kb-extract`\|`kb-service` `init-config`" src tests docs Makefile openspec` **零命中**；且 `kb-service.yaml` / `kb-service.env.example` 文件名仍在（未误改）。
- [x] 6.2 `openspec validate kb-cli-verb-grouping --strict`
- [x] 6.3 `uv run mypy src`（已执行；main 同基线失败，无本 change 新增错误）
- [x] 6.4 `make test-pr` + `make test-integration-ci`，判据"对照 main 基线无新增失败"。
- [x] 6.5 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`（仅命令改名，不应触动边界）。
- [x] 6.6 手验：`uv run fleetent kb --help`(或无参) 打印子命令 usage；`uv run `fleetent` `kb-serve`` 报未识别。
- [ ] 6.7 tasks.md 全 `[x]`；功能分支 `openspec archive kb-cli-verb-grouping`（同步 `agent-runtime-cli` + 被改动的其余 KB spec）；commit（含 Co-Authored-By 签名）+ 推分支；**不 merge main，等 Randy 定夺**。
