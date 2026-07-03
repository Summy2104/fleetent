# unify-logging-stack

## Why

2026-07-03 日志审计发现：项目三套 logger 体系并存（自研 structured_logging 53 文件 / stdlib logging 33 / structlog 6 处遗留），8 个进程入口只有 platform server 和 agent 两个真正初始化日志——node、kb serve、kb worker 在容器部署下 `LOG_FORMAT` 与 logging 配置全部失效；初始化代码在 `config.py` 与 `runtime/agent_app.py` 逐字复制两份；114 处异常日志用 `error=str(exc)` 丢弃 traceback。混用已造成两起真实事故（node/im_edge stdlib API 误用 TypeError、structlog 测试配置污染 flake）。刚完成 dockerize，node/KB 恰是最需要 JSON stdout 的进程，需要一次收口。

## What Changes

按依赖顺序四步（同属日志能力域、文件基本不重叠，故合一个 change）：

1. **共享初始化 + 进程覆盖**：把 `config.py:510-547` 与 `agent_app.py:328-367` 两份重复的 setup 块（configure_structured_logging + structlog.configure + logging.basicConfig）抽成共享函数；node、kb serve、kb worker 入口接入初始化，使 `LOG_FORMAT` 与 logging 配置对它们生效。
2. **单一体系收敛 + 棘轮护栏**：清零 6 处 structlog 使用（im_gateway/slack.py、telegram.py、normalizer.py、outbound.py、skills/registry.py、tools/plugin_loader.py 迁至自研 logger）；新增棘轮护栏测试——stdlib `logging.getLogger` 现有存量冻结为已知清单、只减不增，structlog 在 src 内清零后禁止任何使用。
3. **异常日志保栈**：约 114 处 `error=str(exc)` 机械替换为自研 Logger 的 `exception=exc` kwarg（自动展开 error_type/stack/file/line），以棘轮测试（违规计数归零）做红绿门。
4. **小清理**：删除 `LoggingSettings.json_file` 死配置（定义于 config.py，无任何读取处）；新增 `LOG_LEVEL` 环境变量覆盖 console_level/file_level；统一四个 uvicorn 进程的 access log 姿势。

不改变：structured_logging 的落盘格式（按天 JSONL + error 独立文件）、脱敏逻辑、per-agent 日志目录归属（agent 数据落 agent 侧的架构契约）、node 不捕获 agent 子进程 stdout 的现状（console 混流问题另行处理，不在本 change 范围）。

## Capabilities

### New Capabilities

- `unified-logging-setup`: 全进程统一日志初始化——单一共享 setup 函数，platform server / agent / node / kb serve / kb worker 全部经它初始化；LOG_LEVEL env 覆盖；access log 统一姿势；json_file 死配置移除。
- `logging-stack-convergence`: 单一日志体系约束——src 内 structlog 使用为零；stdlib logging.getLogger 存量棘轮（冻结清单、只减不增）；新代码只准用 fleetent.structured_logging。

### Modified Capabilities

- `structured-logging`: 新增 requirement——异常日志必须保留 traceback：捕获异常处记日志须用 `exception=exc` kwarg，`error=str(exc)` 风格存量清零并以棘轮禁止新增。

## Impact

- **Owning package**: `fleetent.structured_logging`（共享 setup 函数落点；若因 structlog 依赖与"只依赖 paths+stdlib"护栏冲突，则新建顶层 `fleetent/logging_setup.py` 基础设施模块承载，design.md 定夺）。
- **Public API surface**: 新增一个共享初始化函数（暂名 `setup_process_logging(...)`）；`config.configure_logging` 与 `agent_app._configure_logging_from_agent` 改为其薄封装，对外行为不变。`LoggingSettings.json_file` 字段删除（**BREAKING** 仅限配置文件写了该 key 的情况——pydantic 默认忽略未知 key 则无感）。
- **Owned tables**: 无。
- **Config namespace**: `observability.logging.*` 不变；新增 env `LOG_LEVEL`（可选，覆盖 console_level/file_level）；删除 `observability.logging.json_file`。
- **Cross-module dependencies**: node/、knowledge_base/ 入口新增对共享 setup 模块的 import（顶层基础设施，不违反 agent→platform 禁令）；im_gateway/、skills/、tools/ 的 structlog import 移除。structured_logging 的依赖护栏（只依赖 paths+stdlib）必须保持绿。
- **Migration / shim plan**: 无数据迁移。两处旧初始化入口保留为薄封装（不留死代码路径）；structlog 不从依赖清单移除（第三方库仍可能引用），仅 src 内禁用。
- 受影响代码面：src 内约 120+ 文件（其中 ~114 处为 exception= 机械替换），tests 侧新增 2-3 个棘轮护栏测试、可能触碰依赖 structlog capture_logs 的 2 个测试文件。
