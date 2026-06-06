## 1. Runtime 模块迁移与补齐

- [x] 1.1 Write failing tests for runtime.loop logging: 验证 run 开始/结束 info、每轮迭代 debug、工具调用 debug/trace、模型切换 warn 事件在 `_logger` 上被调用
- [x] 1.2 Migrate runtime/loop.py to get_logger("runtime.loop"): 删除 structlog 导入，替换所有 logger 调用，新增事件（run 开始/结束、每轮迭代、工具调用发起/完成/结果、LLM 请求/响应、模型切换）
- [x] 1.3 Write failing tests for runtime.context logging: 验证压缩触发 info、压缩异常 warn 事件
- [x] 1.4 Migrate runtime/context.py to get_logger("runtime.context"): 删除 structlog 导入，替换所有 logger 调用，新增压缩触发 info
- [x] 1.5 Write failing tests for runtime.agent_app logging: 验证 agent_runtime_booted info、mcp_register_failed warn 事件
- [x] 1.6 Migrate runtime/agent_app.py to get_logger("runtime.agent_app"): 删除 structlog 导入，替换调用
- [x] 1.7 Write failing tests for runtime.sub_agent logging: 验证子 agent 启动/完成 info、任务失败 warn、非法状态跳转 warn 事件
- [x] 1.8 Migrate runtime/sub_agent.py + sub_agent_lifecycle.py to get_logger("runtime.sub_agent"): 删除 stdlib logging 导入，printf 转 kwargs，新增启动/完成 info
- [x] 1.9 Write failing tests for runtime.snapshot logging: 验证加载成功 info、不存在 warn、失败 error 事件
- [x] 1.10 Add get_logger("runtime.snapshot") to runtime/snapshot.py: 在 load_active/load_active_db/load_version 函数中新增日志
- [x] 1.11 Write failing tests for runtime.budget logging: 验证预算耗尽 warn 事件
- [x] 1.12 Add get_logger("runtime.budget") to runtime/budget.py: 在 BudgetChecker.check() 耗尽分支新增 warn
- [x] 1.13 Write failing tests for runtime.loop_detector logging: 验证首次检测 warn、终止触发 error 事件
- [x] 1.14 Add get_logger("runtime.loop_detector") to runtime/loop_detector.py: 在两个检测分支新增日志
- [x] 1.15 Write failing tests for runtime.guardrails logging: 验证短路 warn、停止 error 事件
- [x] 1.16 Add get_logger("runtime.guardrails") to runtime/tool_guardrails.py: 在 short_circuit/stop 分支新增日志
- [x] 1.17 Write failing tests for runtime.hygiene logging: 验证有修复时 warn、校验失败 error 事件
- [x] 1.18 Add get_logger("runtime.hygiene") to runtime/message_hygiene.py: 在 sanitize() changed 分支和 MessageContractError 捕获处新增日志
- [x] 1.19 Write failing tests for runtime.error logging: 验证 classify() 记录 debug 事件
- [x] 1.20 Add get_logger("runtime.error") to runtime/error_classifier.py: 在 classify() 新增 debug 日志

## 2. TUI 模块迁移与补齐

- [x] 2.1 Write failing tests for tui.transport logging: 验证连接建立 info、断开 info、关闭出错 warn 事件
- [x] 2.2 Migrate tui/transport.py to get_logger("tui.transport"): 删除 stdlib logging，替换调用，新增连接建立/断开 info
- [x] 2.3 Write failing tests for tui.backend logging: 验证重连 info、非法帧 warn、接收异常 warn 事件
- [x] 2.4 Migrate tui/backend.py to get_logger("tui.backend"): 删除 stdlib logging，替换调用，新增重连 info
- [x] 2.5 Write failing tests for tui.dispatch logging: 验证 run 失败 warn 事件
- [x] 2.6 Migrate tui/dispatch.py to get_logger("tui.dispatch"): 删除 stdlib logging，替换调用
- [x] 2.7 Write failing tests for tui.app logging: 验证启动 info、退出 info 事件
- [x] 2.8 Migrate tui/app.py to get_logger("tui.app"): 删除 stdlib logging，替换调用，新增启动/退出 info

## 3. Sandbox 模块迁移与补齐

- [x] 3.1 Write failing tests for sandbox.client logging: 验证 Docker 探测失败 warn、容器创建/销毁 info、代码执行完成 debug 事件
- [x] 3.2 Migrate integrations/sandbox/client.py to get_logger("sandbox.client"): 删除 stdlib logging，printf 转 kwargs，新增代码执行完成 debug
- [x] 3.3 Write failing tests for sandbox.config logging: 验证配置加载 info、scope 无效 warn、YAML 失败 warn、资源字段无效 warn 事件
- [x] 3.4 Migrate integrations/sandbox/config.py to get_logger("sandbox.config"): 删除 stdlib logging，printf 转 kwargs，新增配置加载 info
- [x] 3.5 Write failing tests for sandbox.cleanup logging: 验证跳过非前缀 warn、清理完成 info 事件
- [x] 3.6 Migrate integrations/sandbox/cleanup.py to get_logger("sandbox.cleanup"): 删除 stdlib logging，printf 转 kwargs
- [x] 3.7 Write failing tests for sandbox.enablement logging: 验证模式无效 warn、YAML 失败 warn 事件
- [x] 3.8 Migrate integrations/sandbox/enablement.py to get_logger("sandbox.enablement"): 删除 stdlib logging，printf 转 kwargs

## 4. Agent Lifecycle 与 IM Gateway 补齐

- [x] 4.1 Write failing tests for agent_lifecycle.controller logging: 验证 start info、stop info、重复 start warn、stop 不存在 warn 事件
- [x] 4.2 Add get_logger("agent_lifecycle.controller") to platform/agent_lifecycle/controller.py: 在 start()/stop() 新增日志
- [x] 4.3 Write failing tests for agent_lifecycle.materialize logging: 验证物化成功 info、失败 error、yaml 写入 debug 事件
- [x] 4.4 Add get_logger("agent_lifecycle.materialize") to platform/agent_lifecycle/materialize.py: 在物化主函数新增日志
- [x] 4.5 Write failing tests for agent_lifecycle.api logging: 验证 start/stop 请求 info、失败 warn 事件
- [x] 4.6 Add get_logger("agent_lifecycle.api") to platform/agent_lifecycle/lifecycle_admin_api.py: 在路由处理函数新增日志
- [x] 4.7 Write failing tests for im_gateway.slack logging: 验证 slack_connector_unconfigured warn、slack_connector_error warn 事件
- [x] 4.8 Migrate im_gateway/slack_supervisor.py to get_logger("im_gateway.slack"): 删除 structlog 导入，替换调用
