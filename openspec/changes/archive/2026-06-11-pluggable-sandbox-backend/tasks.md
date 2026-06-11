# Tasks: pluggable-sandbox-backend

## 1. Spike：msb SDK 能力探查

- [x] 1.1 调研 `microsandbox` SDK 实际调用面 → **完成**，结论见 DECISIONS.md D-spike-1：实测 `microsandbox==0.5.6`（Apache-2.0，本地嵌入式 microVM，无 server/API key）；`Sandbox.create/exec(stdin=)/stop/get/remove/list`、`Volume.bind`、`Network.*`、`is_installed()` 全部确认；capability 回填 `persist_workspace=False`/`workspace_mount=True`/`orphan_cleanup=True`；proposal/design/specs 已据实更新

## 2. 后端抽象与 Docker 迁移（行为不变）

- [x] 2.1 Write failing tests for `backend.py`：`BackendCapabilities` 数据类、`BaseSandboxBackend.exec(session_id=...)` 连续性模板（fake backend 验证 env/cwd 跨 exec 连续、捕获失败降级 `bash -lc`、cwd marker 从输出剥离）
- [x] 2.2 Implement `backend.py`（ABC + capabilities + `ExecResult` 迁移，连续性状态 `_snap_ready`/`_cwd` 收进基类）使 2.1 转绿
- [x] 2.3 Write failing tests for Docker 迁移面：`backends.docker.DockerBackend` 存在且继承 ABC、capabilities 三项全真、`available()` 等价原 `docker_available()`、`client.SandboxClient` 为其 re-export 别名
- [x] 2.4 Implement `client.py` → `backends/docker.py` 整体迁移 + `client.py` 退化 shim；同步迁移既有 client 单测的 patch 目标至 `backends.docker`；跑 `tests/unit` 确认无新增失败

## 3. Capability 门控接入（Docker 全真，行为不变）

- [x] 3.1 Write failing tests for manager 降级：fake backend `persist_workspace=False` 时 `sweep_idle` 跳过 commit 直接 destroy + warn、`_image_for` 返 None；`workspace_mount=False` 时 `acquire` 不传 `workspace_host_path` + 记降级日志；全真 capability 时现状行为回归
- [x] 3.2 Implement `manager.py`：`client` 字段改 `backend: BaseSandboxBackend`，capability 分支（零 isinstance）
- [x] 3.3 Write failing tests for `cleanup_orphans` 门控：`orphan_cleanup=False` 静默跳过返 0 + 说明日志；True 时行为不变
- [x] 3.4 Implement `cleanup.py`（入参改 backend，capability 门控）
- [x] 3.5 Write failing tests for 探测与 health：`agent_app` 以 `available()` 驱动 mode 降级与清理/周期回收触发前提；`server.py` health sandbox 块为 `{mode, backend, backend_available}`
- [x] 3.6 Implement `runtime/agent_app.py` `_start_infra` + `server.py` health 块

## 4. 配置与工厂

- [x] 4.1 Write failing tests for 配置解析：`sandbox.backend` 缺省 docker、非法值 warn 回退 docker、可选 `sandbox.microsandbox.image` 读取；`AgentFile` 新增 `sandbox:` 嵌套节（pydantic 子模型）解析与缺省
- [x] 4.2 Implement sandbox `config.py` backend 选择加载 + `agent_config.py` `SandboxSettings` 节
- [x] 4.3 Write failing tests for factory 选型优先级（integration）：agent.yaml 显式值 > platform.yaml > 默认 docker；单体 agent 仅凭 agent.yaml 配全（无 platform.yaml）
- [x] 4.4 Implement `factory.create_backend`；接线 `builtin_tools._get_manager` 与 `agent_app` 经 factory 取后端

## 5. MicrosandboxBackend（API 基于实测 0.5.6，单测 mock SDK）

- [x] 5.1 Write failing tests（mock `microsandbox.Sandbox` 等符号）：create→`Sandbox.create` 映射 name/image/memory/cpus；Docker 专属硬化字段忽略不报错；`network` none/public_only/allow_all 1:1 映射 `Network.*`；destroy→`Sandbox.remove`、kill→`sandbox.stop` 且幂等；`available()` 经 `is_installed()` 返 False 时安全降级；未选定时不导入 `microsandbox` 包（延迟 import）
- [x] 5.2 Implement `backends/microsandbox.py` 生命周期映射 + `available()`（SDK 延迟导入）；同步把 `microsandbox` 加入 `pyproject.toml`（代码 import 依赖，提前于 7.1）
- [x] 5.3 Write failing tests for exec/挂载/枚举细节：exec 经 SDK 原生 `stdin=` 完整抵达（大 payload）；env 注入重跑 `is_sensitive_name` 过滤；workspace 经 `Volume.bind` 挂载 + `read_only`→`bind(readonly=)`；`list_workspaces` 经 `Sandbox.list` 前缀过滤；`inspect_config_hash` 恒返 None + 复用 debug 日志
- [x] 5.4 Implement exec(stdin) + env 防御过滤 + `Volume.bind` 挂载 + `Sandbox.list` 枚举 + `inspect_config_hash`；声明 capabilities（`persist_workspace=False` / `workspace_mount=True` / `orphan_cleanup=True`）

## 6. 文件工具降级路由

- [x] 6.1 Write failing tests：后端 `workspace_mount=False` 时文件工具走宿主围栏（IM 附件暂存可读、越界路径拒绝）；`workspace_mount=True` 时走容器执行（现状回归）
- [x] 6.2 Implement `file_sandbox_io` / `file_tools` 的路由判定消费 capability

## 7. 依赖、e2e 与收尾

- [x] 7.1 确认 `pyproject.toml` 的 `microsandbox` 依赖已加（5.2 落地）+ `uv.lock` 同步；PR 描述按规则说明必要性、Apache-2.0、自托管与虚拟化前提
- [x] 7.2 e2e：真实 microVM smoke（创建→exec→销毁 + run_code 链路），显式开启不进门禁（需 KVM/HVF + 预装 runtime）
- [x] 7.3 `make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 基线无新增失败 + `scripts/check_test_layers.py`
- [x] 7.4 更新 AGENTS.md / CLAUDE.md 架构节与环境变量表（`sandbox.backend`、microsandbox 部署前提、backends/ 目录结构）
