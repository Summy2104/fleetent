# unified-logging-setup 规格（delta）

## ADDED Requirements

### Requirement: 单一共享日志初始化函数
系统 SHALL 提供唯一的进程日志初始化函数 `setup_process_logging`（顶层基础设施模块 `fleetent/logging_setup.py`），接受朴素参数（console_level、file_level、directory、log_format），不依赖 platform Settings 或 agent.yaml 配置模型，内部完成三件套：configure_structured_logging、structlog.configure（保留 PrintLoggerFactory、不含 add_logger_name processor）、logging.basicConfig。该模块 MUST NOT import 业务能力模块或 `fleetent.platform.*`。

#### Scenario: 一处初始化三套生效
- **WHEN** 任一进程调用 `setup_process_logging(log_format="json")`
- **THEN** 自研 structured_logging 按给定级别/目录生效，structlog 输出为 JSON renderer，stdlib logging 经 basicConfig 收敛为 message-only 格式

#### Scenario: 依赖方向护栏
- **WHEN** 运行模块依赖护栏测试
- **THEN** `fleetent.logging_setup` 的 import 集合仅含 structured_logging、structlog 与 stdlib，不含业务模块与 platform

### Requirement: 旧初始化入口收敛为薄封装
`config.configure_logging(settings)` 与 agent 侧 `_configure_logging_from_agent(agent, home_dir)` SHALL 委托 `setup_process_logging`，自身只保留参数解包/目录解析逻辑，不再各自持有三件套实现。两者对外签名与既有行为（含 agent-log-format-wiring 规定的目录解析）不变。

#### Scenario: platform server 行为不变
- **WHEN** platform server 经 lifespan 调 `configure_logging(settings)` 启动
- **THEN** 日志级别、落盘目录、LOG_FORMAT 渲染行为与收敛前一致

#### Scenario: agent 目录解析行为不变
- **WHEN** agent.yaml 配置相对日志目录或留空
- **THEN** 仍分别按 agent home 解析或默认 `<home>/data/logs`（agent-log-format-wiring 既有场景全部保持通过）

#### Scenario: 三件套实现无重复
- **WHEN** 检视 src 内 structlog.configure 与 logging.basicConfig 的调用点
- **THEN** 各仅存在于 `fleetent/logging_setup.py` 一处

### Requirement: node 与 KB 服务进程初始化日志
node（`node/app.py`）、kb serve、kb worker 的进程入口 SHALL 在启动早期调用 `setup_process_logging`，参数来自环境变量（LOG_FORMAT、LOG_LEVEL），落盘目录使用默认解析。

#### Scenario: LOG_FORMAT 对 node 生效
- **WHEN** 以 `LOG_FORMAT=json` 启动 node 进程
- **THEN** node 进程内 structlog 输出为 JSON 格式（此前无效）

#### Scenario: kb serve / kb worker 同样生效
- **WHEN** 以 `LOG_FORMAT=json` 启动 kb serve 或 kb worker
- **THEN** 该进程日志初始化生效，行为与 node 一致

#### Scenario: 未设 env 时行为与现状兼容
- **WHEN** 不设置 LOG_FORMAT 与 LOG_LEVEL 启动 node/kb 进程
- **THEN** 控制台输出与收敛前默认行为一致（console 文本、info 级）

### Requirement: LOG_LEVEL 环境变量覆盖 console 级别
系统 SHALL 支持环境变量 `LOG_LEVEL`（取值为 structured_logging 级别名 silent/fatal/error/warn/info/debug/trace），在 `setup_process_logging` 内解析并覆盖 console_level 入参；file_level 不受影响（落盘保持独立配置）。非法取值 MUST fail-fast 抛出带合法取值列表的异常。

#### Scenario: env 覆盖入参
- **WHEN** 设 `LOG_LEVEL=debug` 且入参 console_level="info"
- **THEN** 控制台按 debug 级输出，文件级别不变

#### Scenario: 非法值启动失败
- **WHEN** 设 `LOG_LEVEL=verbose`
- **THEN** 初始化抛出异常，错误消息包含合法级别列表

### Requirement: uvicorn 启动点显式声明 log_level
src 内每个 uvicorn 服务启动点 SHALL 显式传 `log_level`（platform serve 与 kb serve 为 "info"，agent 保持 "info"，node forwarder 保持 "warning" 的刻意降噪），access log 保持 uvicorn 默认、不接管进结构化落盘。

#### Scenario: 无隐式默认
- **WHEN** 检视 src 内全部 uvicorn.run / uvicorn.Config 调用
- **THEN** 每处均显式携带 log_level 参数

### Requirement: 移除 json_file 死配置
`LoggingSettings.json_file` 字段 SHALL 删除。文件落盘恒为 JSONL（结构化日志既有行为），不受任何配置项控制。

#### Scenario: 字段不存在
- **WHEN** 检视 LoggingSettings 模型
- **THEN** 无 json_file 字段；配置文件中残留该 key 时因 extra=ignore 不报错
