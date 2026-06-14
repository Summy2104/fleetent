> 排序依据：护栏先红（钉住违例）→ 宿主基建 → 纳编 → 删全局栈（护栏转绿）→ 重连/关停接线 → 契约文档 → 门禁与实机验收。
> 实机验收（8.2/8.3）在合并 + dev-intern 重新部署后执行。

## 1. 护栏先行（先红）

- [x] 1.1 写测试（unit）：`test_module_dependency_guardrails.py` 新增「模块级活异步资源单例」护栏——扫描 `src/fleetent` 模块作用域的 `AsyncExitStack` 实例化/持有（与既有护栏同风格，AST 或行级扫描）—— 现存 `integrations/mcp/client.py:_exit_stack` → **见红**（保持红直至 task 4 完成）

## 2. 会话宿主基建

- [x] 2.1 写测试（unit）：stub transport CM 记录 `__aenter__`/`__aexit__` 的 `asyncio.current_task()`；task A 打开宿主、task B 触发关闭 → enter/exit 同（宿主）task、无跨 task scope 异常；打开失败（CM enter 抛错）→ 异常传播给打开方、无驻留 task；close 幂等；close 先于 ready 的竞态正常收尾 —— 见红
- [x] 2.2 实现 `_SessionHost` + `_host_session`（ready future / close_event / teardown 异常宿主内自吞并 warning）—— 见绿
- [x] 2.3 该层窄命令复跑确认绿

## 3. 打开路径纳编

- [x] 3.1 写测试（unit）：`_open_session_for` 走宿主——`_active_sessions[(scope,id)]` 存宿主句柄、返回可用 session、沿用 `connect_timeout`；既有 MCP 单测层（注册/调用/降级/重连）复跑无新增失败 —— 见红（指 host 断言部分）
- [x] 3.2 改 `_open_session_for` spawn 宿主 + await ready；调用面（注册、`_call_via_session`、`_list_all_tools` 等）经宿主取 session，签名不变 —— 见绿
- [x] 3.3 该层窄命令复跑确认绿

## 4. aclose_all + 删除全局栈（护栏转绿）

- [x] 4.1 写测试（unit）：`aclose_all()` 并发关闭全部宿主（task done、registry 清空）；stub CM `__aexit__` 抛 RuntimeError → 仅 warning、不外泄、其余宿主照常关；卡死宿主超时（monkeypatch `_HOST_CLOSE_TIMEOUT`）→ cancel 兜底、有界完成 —— 见红
- [x] 4.2 实现 `aclose_all()`；删除 `_exit_stack`/`get_exit_stack()` 与死代码 `close()`（grep 确认零调用方）—— 见绿，**且 task 1.1 护栏同时转绿**
- [x] 4.3 该层窄命令复跑确认绿；grep 自查：`client.py` 无 `AsyncExitStack`、全仓无 `get_exit_stack` 引用

## 5. 懒重连关旧

- [x] 5.1 写测试（unit）：`_reopen_session` 后旧宿主 task `done()`、注册表无孤儿；旧宿主关闭抛错 → 仅日志、重开照常 —— 见红
- [x] 5.2 `_reopen_session` 先限时关旧宿主再开新 —— 见绿
- [x] 5.3 该层窄命令复跑确认绿

## 6. 关停接线 + 舱壁

- [x] 6.1 写测试（unit/integration）：`_drain_and_exit` 调用序 = `rt.stop()` → 排干等待 → `aclose_all()`（stub 组件记录顺序）；`_stop_step` 包裹下任一步抛错/挂起（超时）→ warning + 后续步骤照常、函数正常返回 —— 见红
- [x] 6.2 实现 `_stop_step` 舱壁；`AgentRuntime.stop()` 内 IM/调度各步独立包裹；`_drain_and_exit` 排干后追加 `aclose_all()`；`server.py` lifespan shutdown 追加 `aclose_all()` —— 见绿
- [x] 6.3 该层窄命令复跑确认绿

## 7. 契约固化

- [x] 7.1 AGENTS.md 架构契约区追加「长生命周期异步资源 owner-task 契约」（含范式指引：IM supervisor / MCP 会话宿主），并在 Gotchas 区补一条 anyio task 亲和性说明
- [x] 7.2 复核 `docs/`（如有 MCP 连接生命周期描述）与本 change 一致

## 8. 收尾门禁 + 实机验收

- [x] 8.1 `make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 基线无新增失败
- [x] 8.2 实机（合并部署后）：dev-intern 连续 20 次 `kill -USR1`（或 `fleetent agent restart`）→ 每次 journal 无 traceback、`Main process exited` 不出现 status=1、服务每次恢复且 Slack 连接器重连成功
- [x] 8.3 实机（合并部署后）：运行中阻断 armada（http MCP）出网 → 进程存活、该服务按既有 degrade 语义降级、其余工具可用
