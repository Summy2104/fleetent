# unify-logging-stack — 任务清单

> 每个实现任务严格 TDD：先写测试见红（最窄命令 `uv run pytest <file>::<test> -x -q`），再实现见绿。组间按 1→6 依赖顺序执行。

## 1. 共享初始化模块 `fleetent/logging_setup.py`

- [x] 1.1 【测试】新增 `tests/unit/test_logging_setup.py`：`setup_process_logging` 三件套生效（structured_logging 配置被替换、structlog renderer 随 log_format 切换 json/console、basicConfig 收敛）；LOG_LEVEL env 覆盖 console_level 而 file_level 不受影响；非法 LOG_LEVEL fail-fast 且错误消息含合法级别列表 —— 见红
- [x] 1.2 【测试】在 `tests/unit/test_module_dependency_guardrails.py` 新增 `fleetent.logging_setup` 依赖护栏：import 集合仅含 structured_logging / structlog / stdlib，无业务模块与 platform —— 见红（模块尚不存在）
- [x] 1.3 【实现】创建 `src/fleetent/logging_setup.py`：`setup_process_logging(*, console_level, file_level, directory, log_format)`，内部三件套（structlog 保留 PrintLoggerFactory、刻意省略 add_logger_name 并保留 config.py:521-524 的地雷注释），LOG_LEVEL env 解析 —— 1.1/1.2 见绿

## 2. 旧入口收敛为薄封装（行为不变）

- [x] 2.1 【测试】确认既有覆盖并补缺：`config.configure_logging` 与 agent 侧目录解析（agent-log-format-wiring 既有场景）测试基线全绿留档；新增"三件套实现无重复"护栏（src 内 structlog.configure 与 logging.basicConfig 调用点各仅 logging_setup 一处）—— 见红
- [x] 2.2 【实现】`config.configure_logging` 改为解包 Settings 后委托 `setup_process_logging`；`agent_app._configure_logging_from_agent` 保留目录解析、委托共享函数 —— 2.1 见绿且既有测试无新增失败

## 3. node / kb serve / kb worker 入口接入

- [x] 3.1 【测试】unit 测试：node `main()`（mock load_config/backend/provider）、kb serve `main()`、kb worker `main()` 启动早期各调用一次 `setup_process_logging`，参数来自 LOG_FORMAT / LOG_LEVEL env；未设 env 时以默认参数调用 —— 见红
- [x] 3.2 【实现】三个入口接线（node 在 load_config 成功后、log_service_startup 前；kb 两进程在 configure_process_runtime 后）—— 见绿

## 4. structlog 清零 + 双棘轮护栏

- [x] 4.1 【测试】新增护栏 `tests/unit/test_logging_stack_guardrails.py`：src 内 `import structlog` 仅允许 `fleetent/logging_setup.py` —— 见红（现存 6 处违例）
- [x] 4.2 【实现】迁移 6 个文件（im_gateway/slack.py、telegram.py、normalizer.py、outbound.py、skills/registry.py、tools/plugin_loader.py）到 `structured_logging.get_logger`，`.warning(` → `.warn(`，kwargs 风格不变；逐文件跑其相关既有测试 —— 4.1 见绿
- [x] 4.3 【测试+实现】同文件新增 stdlib 棘轮：内置 `logging.getLogger` 存量文件冻结清单（以实现时实际扫描结果为准，注释声明 only-shrink 约定），断言实际集合 ⊆ 清单 —— 先以空清单见红，填入存量后见绿
- [x] 4.4 【测试】依赖 structlog 配置的既有测试排查：`structlog.testing.capture_logs` 的 2 个测试文件随 4.2 迁移改写；conftest `_reset_structlog_config` 保持不动 —— 相关文件测试全绿

## 5. 异常保栈全量替换（独立 commit，与其它组隔离）

- [x] 5.1 【测试】新增 AST 护栏（并入 test_logging_stack_guardrails.py）：扫描 src 内 logger 调用（方法名 ∈ {error, warn, warning, fatal, critical, exception}）的 `error=str(...)` kwarg，断言计数 0，报告文件与行号；非 logger 调用（API payload 等）不在扫描范围 —— 见红（现存约 114 处）
- [x] 5.2 【实现】全量替换：自研 Logger 站点 `error=str(exc)` → `exception=exc`；stdlib 站点命中者改 `logger.exception(...)` 或 `exc_info=True`（预计极少，逐个确认）—— 5.1 见绿；`make test-unit` 无新增失败

## 6. 小清理 + 收尾

- [x] 6.1 【测试】LoggingSettings 无 `json_file` 字段、含该 key 的配置文件不报错（extra=ignore）；uvicorn 显式 log_level 护栏（src 内全部 uvicorn.run / uvicorn.Config 调用均显式携带 log_level）—— 见红
- [x] 6.2 【实现】删除 `LoggingSettings.json_file`（config.py:47）；platform serve 与 kb serve 的 uvicorn 启动点补 `log_level="info"`（agent/forwarder 保持现值）—— 见绿
- [x] 6.3 【文档】AGENTS.md 环境变量段新增 `LOG_LEVEL`；Gotchas 视需要补"日志初始化统一走 logging_setup"一条（非代码产物，人工确认后提交）
- [x] 6.4 【验证】change 收尾：`make test-pr` + `make test-integration-ci` 全绿（对照 main 基线无新增失败）
