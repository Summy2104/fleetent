## Why

sandbox 的使命是「保护主机系统不受恶意或失控代码影响」，但当前 `SandboxClient._resource_flags`（`integrations/sandbox/client.py`）产出的 `docker run` 标志仅有 `--memory` / `--cpus` / `[--network none]` / `[--read-only]` / `--tmpfs /tmp`——缺少业界沙箱默认的容器加固。后果是几条真实可利用的逃逸/拒绝服务路径全部敞口：

- **fork 炸弹**：无 `--pids-limit`，容器内可无限 fork，拖垮宿主进程表。
- **撑爆宿主内存**：`--tmpfs /tmp` 无 `size=` 上限，而 tmpfs 由宿主 RAM 支撑，往 `/tmp` 写大文件即可耗尽宿主内存。
- **容器内 root + 全能力**：未 `--cap-drop`、未 `--security-opt no-new-privileges`、未 `--user`，代码以 root 持全部 Linux capability 运行，一旦存在容器逃逸点，爆炸半径最大化。
- **僵尸进程堆积**：无 `--init`，PID 1 不回收子进程，配合 pids-limit 易触顶。

hermes-agent 与 openclaw 的 Docker 后端默认都做了这些加固；fleetent 全缺。本 change 补齐，且按 scope 分层（session 最严、agent 为装依赖留最小放行），全部可配置。

## What Changes

- 扩展 `SandboxResources`（`integrations/sandbox/config.py`）新增加固字段，沿用既有「逐字段校验 + 非法回退安全默认」加载模式，从 `sandbox.resources` / `sandbox.agent_scope` 配置段读取：
  - `pids_limit`（默认 256）→ `--pids-limit`
  - `tmpfs_size_mb`（默认 64）→ `/tmp` 改为 `--tmpfs /tmp:rw,nosuid,size={n}m`（限大小 + `nosuid`）
  - `cap_drop_all`（默认 True）→ `--cap-drop ALL`
  - `cap_add`（默认空）→ 每项一个 `--cap-add`
  - `no_new_privileges`（默认 True）→ `--security-opt no-new-privileges`
  - `init`（默认 True）→ `--init`
  - `run_as_user`（session 默认 `"65534:65534"`，即 nobody）→ `--user`
- `build_resources_by_scope` 设定 **agent scope 覆盖**：`cap_add=(CHOWN, DAC_OVERRIDE, FOWNER, SETUID, SETGID)`（pip 装依赖所需）、`run_as_user=None`（root，写系统 site-packages）；session scope 用上述最严默认。
- `SandboxClient._resource_flags` 据上述字段追加加固标志；`--tmpfs /tmp` 升级为带 `nosuid,size=` 的形式。
- **BREAKING（仅内部行为）**：默认 `docker run` 命令变更——所有沙箱容器自此带 cap-drop、no-new-privileges、pids-limit、tmpfs 限额、init，session scope 以 nobody 运行。需同步更新 `tests/unit/test_sandbox_client.py` 既有断言。对外工具契约（`run_code` 输入输出）不变。
- 不改：network 三态模型、`read_only` / `exec_timeout` 既有需求、生命周期 scope、启用 mode。

## Capabilities

### New Capabilities
- `sandbox-container-hardening`: Docker 沙箱容器创建时 SHALL 应用按 scope 分层的安全加固标志（pids 限制、tmpfs 限额+nosuid、能力收敛、no-new-privileges、init、非 root），各项可配置、非法值回退安全默认；agent scope 为安装依赖保留最小必要放行。

### Modified Capabilities
<!-- 不修改既有 spec 的需求。本 change 新增的是与 sandbox-resource-limits 并列的加固标志，
     既有 memory/cpus/network/read_only/exec_timeout 的需求与行为不变（仅 SandboxResources 数据结构
     新增字段，属实现细节）。加固标志作为 Docker 后端新增能力，落在新 capability 下以 ADDED 表达。 -->

## Impact

- **代码**：
  - `src/fleetent/integrations/sandbox/config.py`：`SandboxResources` 新增加固字段 + 各自加载校验；`build_resources_by_scope` 设 agent 覆盖（cap_add / run_as_user）。
  - `src/fleetent/integrations/sandbox/client.py`：`_resource_flags` 追加加固标志，`--tmpfs /tmp` 升级带选项。
- **配置**：`sandbox.resources` / `sandbox.agent_scope` 新增可选加固字段，全部缺省即安全默认。
- **测试**：扩充 `tests/unit/test_sandbox_config.py`（新字段加载/默认/非法回退/agent 覆盖）与 `tests/unit/test_sandbox_client.py`（断言加固标志按 scope 出现，更新既有 flag 断言）。docker CLI 全 mock，配置路径 monkeypatch 到 tmp_path，属 unit 层。
- **文档**：新建 `docs/capabilities/sandbox-improvements.md`（四参考项目对比结论 + 本批 4 个 change 的决策与取舍，供 review）；校正 `docs/capabilities/sandbox.md` 过期的「规划中」标注与「资源限制硬编码」描述。
- **不影响**：`run_code` 工具契约、agent_loop、permission_gate、session 生命周期；不引入新依赖。
