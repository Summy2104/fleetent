# Tasks: sandbox-workspace-scope-split

> 高风险重构。每个实现 task 前必须先写测试见红、再实现见绿(TDD 硬门)。
> 不碰 `sandbox-lifecycle`「命名/碰撞」块与 `sandbox-workspace-mount` key 派生无碰撞条款(地基已改)。
> 不改 `action_gate.resolve_action_mode` 契约、不改 registry risk 常量。

## 1. workspace_scope 语义收敛(数据隔离与镜像解耦)

- [ ] 1.1 写 unit 测试:`acquire` 的容器名/路径 key 仅由 `workspace_scope` 派生,镜像选择不随 `workspace_scope` 改变(同一 per-agent 镜像开关 + 后端能力下,`session` 与 `agent` 取得相同镜像选择结果)——先见红
- [ ] 1.2 在 `integrations/sandbox/manager.py` 把 `Scope`→`WorkspaceScope`(保留 `Scope = WorkspaceScope` re-export 别名),`acquire` 拆出镜像选择为独立分支,容器名/路径 key 收敛到 `workspace_scope`,`_Entry.scope` 类型同步(见绿)
- [ ] 1.3 写 unit 测试:`config.load_sandbox_lifecycle` 把 `workspace_scope` 正名生效,旧键 `sandbox.scope` 被读取并映射到 `workspace_scope`(读旧键 + warn,按新语义生效)——先见红
- [ ] 1.4 在 `integrations/sandbox/config.py` 把 `SandboxLifecycle.scope` 正名为 `workspace_scope`,加旧键兼容映射(per-field 校验、缺省安全)(见绿)
- [ ] 1.5 跑通 1.1/1.3 相关最窄命令;确认 `release_session`/`invalidate`/`container_name`/`forget` 的 key 推导随语义收敛同步,同 key→同名→同目录不变式保持

## 2. 多用户强制 session 数据隔离

- [ ] 2.1 写 unit 测试:多用户运行形态下配置 `workspace_scope: agent` 被纠正为 `session` 并记录告警;单用户 standalone 下 `agent` 保留——先见红
- [ ] 2.2 实现多用户校验:生效 `workspace_scope` 在多用户形态强制 `session`(启动期纠正 + warn),复用既有运行形态信号判定多用户(见绿)
- [ ] 2.3 写 integration 测试:多用户部署中同一 agent 的两个不同 session 经 `acquire` 取得名称不同、相互隔离的容器与不同 workspace 宿主子目录,一方写入 `/workspace` 对另一方不可见(原 agent scope 共享行为消失)
- [ ] 2.4 跑通 2.3;确认删除 `agent` 数据隔离档后多用户路径不再落到共享目录/容器

## 3. 声明式离线 build 不可变镜像(替换 commit-from-running)

- [ ] 3.1 写 unit 测试:`_image_for` 只看 per-agent 镜像持久化开关 + 后端 `persist_workspace` 能力(查声明式不可变镜像标签),与 `workspace_scope` 解耦;无声明式镜像回退基础镜像——先见红
- [ ] 3.2 在 `integrations/sandbox/manager.py` 改 `_image_for` 查声明式不可变镜像、不再查 commit 产物;镜像选择分支只由持久化开关 + 后端能力驱动(见绿)
- [ ] 3.3 写 unit 测试:`sweep_idle` 对闲置容器**不调用** `commit_workspace`、纯按 `idle_hours` 销毁;`session` 容器不参与回收——先见红
- [ ] 3.4 改 `sweep_idle` 移除 commit-then-destroy,纯按存活/闲置回收(见绿)
- [ ] 3.5 写 unit 测试:后端声明式 build 原语产出**不可变**镜像;`persist_workspace=False`(microsandbox)下 `_image_for` 永远回退基础镜像并记录热启动不成立日志——先见红
- [ ] 3.6 在 `backend.py` + `backends/docker.py` 新增/改用声明式 build 原语(从 `setup_command` 构建不可变镜像),`commit_workspace`(running-container commit)退出生命周期热路径;`backends/microsandbox.py` 声明 `persist_workspace=False` 热启动不成立(见绿)
- [ ] 3.7 写 integration 测试:声明式离线 build 产出不可变镜像、运行期只读启动且复用不重装依赖;容器被回收/重建后新容器**不含**上一会话写入容器层的内容(不可变性回归)
- [ ] 3.8 跑通 3.7,覆盖 Docker(支持热启动)与 microsandbox(运行期重新就绪)两分支

## 4. agent.yaml per-agent 镜像/ setup_command schema

- [ ] 4.1 写 unit 测试:`agent_config.SandboxSettings` 新增 per-agent 镜像持久化开关 + `setup_command`,缺省关闭/空(默认行为不变),非法值/未知键(`extra=forbid`)被拒——先见红
- [ ] 4.2 在 `agent_config.py` 扩展 `SandboxSettings`(schema-only 校验)(见绿)
- [ ] 4.3 跑通 4.1;确认默认 agent.yaml 不声明时行为与重构前一致

## 5. 边界与收尾

- [ ] 5.1 跑 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 无新增跨包 internal import;确认 `integrations/sandbox`/`tools`/`runtime` 均 MUST NOT import `fleetent.platform.*`
- [ ] 5.2 无-platform 冒烟:在无 platform、platform 表不存在环境下 `fleetent agent run` 仍可完成一轮含沙箱执行的对话(`workspace_scope` 默认 session、无声明式镜像回退基础镜像)
- [ ] 5.3 `uv run ruff format` + `uv run ruff check` 改动文件、`uv run mypy src` 通过
- [ ] 5.4 `make test-pr` 全绿(对照 main 基线无新增失败)+ `uv run pytest tests/integration -q` 无新增失败
- [ ] 5.5 `openspec validate sandbox-workspace-scope-split --strict` 通过
