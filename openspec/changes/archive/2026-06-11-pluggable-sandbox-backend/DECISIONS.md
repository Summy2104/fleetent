# 实施期问题与决策记录（autonomous apply）

本文档记录在 `/opsx:apply` 自动实施期间遇到的问题、做出的决策与依据，供事后审批。
按时间顺序追加，每条标注任务号、问题、决策、依据。

---

## 实施开始

- 分支：`feat/pluggable-sandbox-backend`
- worktree：`.worktrees/pluggable-sandbox-backend/`
- 起点：main @ 2abc2683
- 模式：全自动 TDD（红→绿），逐任务组提交

---

## D-spike-1（任务 1.1）：microsandbox SDK 实际架构与设计假设有重大出入 → 据实调整

**问题**：proposal/design 假设 microsandbox 是「client-server」模型——配 `sandbox.microsandbox.server_url` 连一个自托管 `msb server`，API key 走 `.env` 的 `MSB_API_KEY`。spike 安装真包（PyPI `microsandbox==0.5.6`）并自省 API，发现现实完全不同。

**实测结论（0.5.6，权威，非文档推测）**：

| 维度 | 设计假设 | 实测现实 |
|------|---------|---------|
| 架构 | client-server，连 msb server | **本地嵌入式**：`Sandbox.create()` 直接以子进程拉起 microVM（pyo3/Rust 原生 wheel，libkrunfw 嵌入），无 server、无 server_url、无 API key |
| 依赖 | 薄 HTTP 客户端 | **平台原生编译 wheel**（macos arm64 / manylinux x86_64+aarch64），31MB，无 Python 传递依赖 |
| License | MIT | **Apache-2.0**（仍属许可宽松、可自托管、非 AI 框架，合规） |
| 可用性探测 | server 可达 | `microsandbox.is_installed()`（无 runtime 时安全返 `False` 不抛）+ `version()` |
| stdin | 需 base64 分块绕过 ARG_MAX | **`exec(..., stdin=...)` / `shell(..., stdin=...)` 原生支持** → base64 方案作废 |
| host 挂载 | 假设可能不支持 | **`Volume.bind(path, *, readonly, noexec, nosuid, nodev)` 支持 host 绑定挂载 + 硬化旗标** |
| 实例枚举 | 假设可能不支持 | **`Sandbox.list()` 支持** |
| 依赖固化 | 无对应物 | 无 image-commit；有 `Snapshot`/`SnapshotHandle`（语义不同，列未来工作） |
| network | none 映射 | **`Network.none()/allow_all()/public_only()` 与现有 `NetworkPolicy` 枚举 1:1 干净映射** |
| 生命周期 | start/run/stop | `Sandbox.create(name, image=, cpus=, memory=, network=, volumes=)`；`exec(cmd, args, *, cwd, env, timeout, stdin)`→`ExecOutput{stdout_text, stderr_text, exit_code, success}`；`stop(timeout=)` 优雅 / `kill()` 强制；`get(name)`/`remove(name)`/`list()` |

**决策**：采纳 **Option A——据实把 microsandbox 后端适配到 0.5.6 本地嵌入式模型**，不退回旧版本去凑 client-server。理由：

1. 0.5.x 是该工具当前唯一在维护的形态，旧 client-server API（`PythonSandbox(server_url, api_key)`）在 0.5.6 已不存在（module 只导出 `Sandbox`）
2. 本地嵌入式同样满足用户原始动机「无 Docker / 不允许 docker.sock 的内网」——它是另一套隔离机制（microVM），恰是可插拔后端的价值
3. **架构（ABC + capability + factory）零改动**——capability 机制设计的本意就是吸收这种后端不确定性，spike 任何结论都不动架构，只回填取值
4. 实测能力比设计假设更强：`workspace_mount=True`、`orphan_cleanup=True` 均可达

**对 artifacts 的具体修订**（已据此更新 proposal/design/specs/tasks）：

- **配置**：删除 `sandbox.microsandbox.server_url` 与 `MSB_API_KEY`。microsandbox 后端无需连接配置；可选 `sandbox.microsandbox.image`（默认基础镜像）。`available()` = `is_installed()` 探测（runtime 未安装即降级 OFF，复用既有降级路径）。**不自动 `install()`**（重量级、需联网拉 libkrunfw）——由运维预装，后端只探测
- **capability 回填**：`persist_workspace=False`（确定）、`workspace_mount=True`（`Volume.bind`）、`orphan_cleanup=True`（`Sandbox.list`）
- **stdin**：删除 base64 分块需求与任务，改用 SDK 原生 `stdin=` 参数
- **license**：proposal MIT → Apache-2.0
- **部署前提新增**：microsandbox 后端需宿主提供硬件虚拟化（Linux KVM `/dev/kvm` / macOS HVF）+ 预装 microsandbox runtime；不满足时 `is_installed()` 返 False → mode 降级 OFF（与 Docker 不可用同路径，不阻断启动）
- **测试**：单测 mock SDK（`microsandbox.Sandbox` 等符号），不需真实 microVM / KVM；真实 microVM smoke 进 e2e 显式开启
- **依赖落地时机**：`microsandbox` 在实现后端时（任务 5.2）即加入 pyproject（代码 import 依赖它），不拖到 7.1；spike 期已 `uv pip install` 到 venv 供开发

**影响评估**：纯本后端内部实现 + 配置面调整，不影响 Docker 后端、不影响 ABC 契约与 manager 决策点。降级矩阵中 `workspace_mount`/`orphan_cleanup` 由「待回填」变为确定 True，对应 spec 的降级条款仍保留（供未来不支持挂载的第三后端复用，且 microsandbox 若在无 KVM 环境探测失败时整体走 OFF，不触发这些细粒度降级）。

---

## D-impl-1：任务 3.5/3.6 与任务 4 调换顺序（probe/health 依赖 factory）

**问题**：tasks.md 原排 3.5/3.6（探测 + health 后端无关化）在 4（配置 + factory）之前。但实现时发现 backend-neutral 探测必须经 factory 选出配置后端——`enablement.get_effective_mode()` 当前硬编码 `SandboxClient()`（Docker），agent_app 的 `cleanup_orphans(SandboxClient())` 同理；health 块要报告 `backend` 名也需 factory 选型结果。

**决策**：先做 4（config + factory），再做 3.5/3.6（用 factory 选出的后端驱动探测/清理/health）。TDD 纪律不变，仅调换组顺序。

**附带发现**：`app.state.sandbox_mode` / `sandbox_docker_available` 在现有代码中从未被赋值——platform server 不跑 sandbox（platform-control-plane），health 块恒走默认（OFF/False）。真实探测在 `enablement.get_effective_mode()`（被 loop/normalizer/agent_app 消费）。故 health 块字段改名为诊断面调整，无运行时行为变化。
