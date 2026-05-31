## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `SandboxClient` 容器命名前缀 `sandbox-`（sandbox_client.py 行 29）与销毁路径 `destroy_workspace`（`docker rm -f`，行 60-68），确认清理可复用销毁
- [ ] 1.2 核实 `server.py` lifespan（行 66-67）作为启动钩子的现状（现有启动逻辑），确定清理调用的插入点，且与 SB3 Docker 探测/降级协调（探测复用还是独立）
- [ ] 1.3 确认前缀常量 `SANDBOX_NAME_PREFIX = "sandbox-"` 定义在 `sandbox_client.py`（已定调，与 SB2 收口统一），本 change `import` 复用，不重复定义

## 2. 枚举容器能力（sandbox_client.py）

- [ ] 2.1 Write failing tests：`list_containers("sandbox-")` 解析 `docker ps -a --filter name=... --format {{.Names}}` 多行输出为名称列表；无匹配返回空列表；Docker 不可用 / 命令非零时返回空列表且不抛异常（mock `asyncio.create_subprocess_exec`）。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement `list_containers`（命令构造 + 行解析 + 失败安全降级 + log），看到绿

## 3. 孤儿清理编排（sandbox_cleanup.py）

- [ ] 3.1 Write failing tests：`cleanup_orphans(client)` 对 `list_containers` 返回的每个 `sandbox-` 前缀容器调 `destroy_workspace` 并返回销毁计数；空列表返回 0；Docker 不可用（list 返回空）返回 0。mock SandboxClient。看到红
- [ ] 3.2 Implement `cleanup_orphans`（枚举 → 销毁 → 计数），看到绿
- [ ] 3.3 Write failing test 防误删：`list_containers` 返回中混入不以 `sandbox-` 开头的名称（模拟 Docker 子串匹配误纳入）时，该容器不被销毁（Python 侧 `startswith` 二次校验）。看到红
- [ ] 3.4 Implement 前缀二次校验，看到绿

## 4. 启动期触发接线（server.py）

- [ ] 4.1 Write failing tests：平台启动（lifespan）调用 `cleanup_orphans` 一次；清理抛异常时记录警告且启动不被阻断（mock `cleanup_orphans` 抛异常 + 断言启动完成）。看到红
- [ ] 4.2 Implement：lifespan 启动段 try/except 调用 `cleanup_orphans`，失败 log 警告继续启动，看到绿

## 5. 按需触发入口

- [ ] 5.1 Write failing test：`cleanup_orphans` 可被独立调用（不依赖 server/lifespan、不依赖任何调度器），返回销毁计数供手动触发使用。看到红
- [ ] 5.2 Implement 确保函数为可独立调用的纯编排入口（无调度器依赖），看到绿

## 6. 收尾

- [ ] 6.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [ ] 6.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 6.3 `uv run mypy src` 无新增错误
