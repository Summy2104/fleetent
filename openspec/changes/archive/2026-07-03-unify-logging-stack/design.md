# unify-logging-stack — 设计

## Context

现状（2026-07-03 审计，全量静态扫描）：

- 三套 logger 并存：自研 `structured_logging.get_logger()` 53 文件（主流）、stdlib `logging.getLogger(__name__)` 33 文件、`structlog.get_logger()` 6 处遗留。同包混用（im_gateway = 3 structlog + 2 自研；integrations = 6 stdlib + 12 自研；platform = 7 stdlib + 3 自研）。
- 完整日志初始化（configure_structured_logging + structlog.configure + logging.basicConfig 三件套）只有两个入口：`server.py:277 → config.configure_logging(settings)` 和 `agent_app.py:687 → _configure_logging_from_agent(agent, home_dir)`，两者三件套代码逐字重复（`config.py:510-547` / `agent_app.py:320-366`）。
- node（`node/app.py`）、kb serve（`serve.py:579`）、kb worker（`worker.py:447`）、platform CLI、TUI 均不初始化：自研日志吃默认配置（console=info 文本 + file=debug JSONL 到 `paths.logs_dir()`），structlog 未配置，`LOG_FORMAT` 对它们无效。
- 异常日志 114 处 `error=str(exc)`（丢 traceback）；自研 Logger 的 `exception=exc` kwarg（`_exception_fields` 展开 error_type/stack/file/line）生产代码零使用。
- `LoggingSettings.json_file`（config.py:47）为死配置，全仓无读取处。

约束：

- `structured_logging` 有依赖护栏（`test_structured_logging_infra_boundary`）+ spec 要求"只依赖 fleetent.paths + stdlib"——**structlog 是三方库，共享 setup 不能放进 structured_logging.py**。
- `configure_logging(settings: Settings)` 绑死 platform `Settings`（pydantic-settings + platform.yaml），agent 侧因此复制而非复用——共享函数必须接**朴素参数**，不依赖任何一方的配置模型。
- node/ 不得 import platform；knowledge_base/ 已 import 顶层 `fleetent.config.Settings`（serve.py:93 / worker.py:79），顶层模块两侧皆可用。
- structlog 的 `PrintLoggerFactory` 与 `add_logger_name` 不兼容（config.py:521-524 注释的地雷），共享函数必须原样保留该 processor 省略；`cache_logger_on_first_use=True` 的测试污染由 conftest `_reset_structlog_config` 兜底（已存在）。

## Goals / Non-Goals

**Goals:**

- 一个共享 setup 函数，8 进程中 5 个服务型进程（platform server / agent / node / kb serve / kb worker）全部经它初始化，`LOG_FORMAT` 对全部 5 个生效。
- src 内 structlog 使用清零；stdlib logging 存量冻结、只减不增（棘轮）。
- 异常日志保栈：`error=str(exc)` 风格在 logger 调用中清零（棘轮守住）。
- 删 `json_file` 死配置；新增 `LOG_LEVEL` env；uvicorn access log 姿势显式化。

**Non-Goals:**

- 不迁移 33 处 stdlib logging 存量（只冻结禁增，迁移另起 change）。
- 不改 structured_logging 的落盘格式 / 脱敏 / 按天分文件机制。
- 不改 node 拉起 agent 的 stdout 继承（console 混流问题不在本 change）。
- platform CLI 与 TUI 不强制接入（CLI 面向用户 print 合理；TUI 有自建 sink），仅受益于默认配置不回归。
- 不动 tests/ 内的 stdlib/structlog 使用（棘轮只扫 src/）。

## Decisions

### D1: 共享 setup 落点 = 新顶层模块 `fleetent/logging_setup.py`

签名（朴素参数，不依赖任何配置模型）：

```python
def setup_process_logging(
    *,
    console_level: str = "info",
    file_level: str = "debug",
    directory: str | Path | None = None,
    log_format: str = "console",   # console | json，控制 structlog renderer
) -> None: ...
```

内部依次做三件套：`configure_structured_logging(...)` → `structlog.configure(...)`（含 PrintLoggerFactory、无 add_logger_name、`cache_logger_on_first_use=True`）→ `logging.basicConfig(format="%(message)s", level=INFO, handlers=[StreamHandler()])`。env 覆盖（见 D4）也在此函数内解析。

- 为什么不放 `structured_logging.py`：违反其"只依赖 paths+stdlib"spec 与护栏（structlog 是三方库）。
- 为什么不放 `config.py`：config.py 承载 platform Settings 模型，agent/node 侧复用会引入不必要的 pydantic-settings/platform.yaml 语义耦合；且历史上 agent 正是因此复制了一份。
- 替代方案（放 observability/ 包内）被否：observability/ 是 agent 运行时能力域，node 入口 import 它语义错位；顶层基础设施模块与 structured_logging.py 平级，最贴合"跨域日志底座"定位。
- 依赖方向：logging_setup 只 import structured_logging / structlog / stdlib，不 import 业务与 platform——纳入 module-dependency-guardrails 同款约束（在 unified-logging-setup spec 内声明）。

### D2: 两处旧入口改薄封装，行为不变

- `config.configure_logging(settings)` → 解包 Settings 后调 `setup_process_logging(...)`，签名与调用点（server.py:277）不动。
- `agent_app._configure_logging_from_agent(agent, home_dir)` → 保留其目录解析逻辑（相对路径对 agent home 解析、空值默认 `<home>/data/logs`，见 agent-log-format-wiring spec），解析完调共享函数。
- 三个新入口直接调共享函数：
  - node（`node/app.py main()`，在 `load_config()` 成功后、`log_service_startup` 前）：参数来自 env（`LOG_FORMAT` + `LOG_LEVEL`），directory 走默认 `paths.logs_dir()`。node/config.py 不加日志字段（node 配置面保持最小，env 足够容器场景）。
  - kb serve / kb worker（各自 `main()`，`configure_process_runtime()` 后）：同 node，env 驱动。

### D3: structlog 清零但保留 structlog.configure

6 处使用（im_gateway/slack.py、telegram.py、normalizer.py、outbound.py、skills/registry.py、tools/plugin_loader.py）迁到 `structured_logging.get_logger("<component>")`，调用点 `.warning(` → `.warn(`、kwargs 风格不变（structlog 与自研同为 event+kwargs，机械替换）。

`structlog.configure` 仍留在 logging_setup 内：三方依赖仍可能经 structlog 输出，配置保证其格式跟随 LOG_FORMAT。替代方案（连 structlog 配置一起拆掉）被否——省不了依赖（传递依赖仍在），却失去对三方输出的格式控制。

棘轮：src 内 `import structlog` 仅允许 `fleetent/logging_setup.py` 一处（护栏测试断言）。

### D4: LOG_LEVEL env 只覆盖 console_level

`LOG_LEVEL`（取值 = structured_logging 的级别名 silent/fatal/error/warn/info/debug/trace）覆盖 console_level；**file_level 不受它影响**（落盘保持 debug 全量，容器里调 console 噪音不牺牲事后排查）。解析在 setup_process_logging 内：显式入参 < env（env 优先，便于容器 override 配置文件）。非法值 fail-fast 抛 ConfigError 语义的 ValueError（宁可启动失败也不静默吃错级别）。

### D5: 异常保栈棘轮用 AST 扫描，不用正则

`error=str(...)` 在 API 响应 payload（dict/JSONResponse）里是合法用法，纯文本 grep 会误伤。护栏测试 AST 遍历 src：调用节点满足「func 是 attribute 且 attr ∈ {error, warn, fatal, warning, exception, critical}」且「keyword 参数名 == error 且值为 `str(...)` 调用」→ 违规。目标计数 0（TDD 红绿门：先写测试断言 0 见红 → 全量替换 `error=str(exc)` → `exception=exc` 见绿）。

替换语义：自研 Logger 站点 `error=str(exc)` → `exception=exc`（`_make_record` pop 出来展开）；stdlib 站点（属冻结存量）若命中同模式，改 `logger.exception(...)` 或 `exc_info=True`——预计极少，逐个处理。

### D6: stdlib 棘轮 = 冻结文件清单

仿 `_KNOWN_TRANSITIVE_PLATFORM_LEAKS` 模式：护栏测试内置 frozenset 存量清单（33 个文件），断言「src 内出现 `logging.getLogger` 的文件集合 ⊆ 清单」——新增即红，删掉存量后从清单移除（only-shrink，注释注明）。`import logging` 本身不禁（Level 常量等合法用途），只钉 getLogger。

### D7: access log 姿势 = 显式声明，不重定向

四处 uvicorn 启动点统一为**显式传 log_level**：platform serve（platform_cli/serve.py，现在什么都不传）补 `log_level="info"`；agent（agent_app.py:830，已 "info"）与 forwarder（node/app.py:23，已 "warning"，噪音抑制是刻意的）保持；kb serve 补 `log_level="info"`。access_log 保持 uvicorn 默认开启、不接管进结构化落盘——接管需要自定义 logging handler 桥接，收益低（access log 是 stdout 采集器的菜），不做。

### D8: json_file 直接删字段

`LoggingSettings.json_file` 删除。pydantic `extra="ignore"`（Settings 层）下，已写该 key 的配置文件不会炸；`LoggingSettings(BaseModel)` 默认 extra=ignore 同样安全。不留 deprecation 期——死配置从未生效过，删除无行为变化。

## Risks / Trade-offs

- [114 处机械替换让 PR 变宽、review 负担大] → 替换是单一模式（`error=str(exc)` → `exception=exc`），独立成一个 commit 与其它改动隔离；AST 棘轮测试即是验收判据，reviewer 只需抽查。
- [structlog 站点迁移改 `.warning`→`.warn` 时漏改 kwargs 兼容性] → 自研与 structlog 同为 event+kwargs 风格，逐文件跑该文件相关最窄测试；im_gateway 有既有单测覆盖。
- [node/kb 新增初始化改变现有 stdout 格式，可能影响依赖 console 输出的既有 e2e/脚本] → 默认 LOG_FORMAT=console 时 structured_logging 控制台输出与现状一致（未配置时本就是同一 `_write_console`）；变化仅在 structlog/basicConfig 生效后三方库输出格式，e2e harness 断言的是业务输出非日志格式。跑 `make test-integration-ci` 对照基线。
- [AST 棘轮有误报/漏报边界（如 error=str() 嵌套表达式）] → 棘轮只需守住主流模式；漏报的花式写法交给 code review，误报（若有）以显式白名单注释处理。
- [LOG_LEVEL fail-fast 可能让配错 env 的容器起不来] → 刻意为之（与"不吞异常"项目纪律一致）；错误消息列出合法取值。
- [清单式 stdlib 棘轮在文件改名/移动时烦人] → 与 `_KNOWN_TRANSITIVE_PLATFORM_LEAKS` 同款代价，项目已接受此模式；改名时同步改清单即可。

## Migration Plan

无数据迁移、无 schema 变更。部署面：node/kb 容器新识别 `LOG_LEVEL`（可选，不设则行为同今天的默认级别）；`LOG_FORMAT=json` 开始对 node/kb 生效——**这是期望的行为修复而非回归**，采集器侧若已按纯文本解析 node/kb stdout 需知晓（目前无此依赖）。回滚 = revert commit，无状态残留。

## Open Questions

- 无（access log 是否接管结构化落盘已在 D7 拍板：不接管）。
