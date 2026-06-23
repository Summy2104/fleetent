# e2e-multi-tenant-isolation

## Purpose

验证多 tenant managed 栈下的物理隔离与数据零串：两 tenant 各有独立数据路径，跨租户读路径不泄漏任何数据。

---

## Requirements

### Requirement: 多 tenant managed 栈 e2e fixture

项目 SHALL 提供一个 e2e fixture（如 `managed_stack_two_tenants`），在真实多进程 managed 栈下起 **两个 tenant**、各放置一个 agent，复用既有多进程起栈基建与确定性 LLM stub。该 fixture SHALL 以**新增**方式提供，**不重构**核心 `managed_stack` fixture（避免与并行 e2e 波撞 `conftest.py`）。

#### Scenario: 两 tenant 各起一 agent 并就绪

- **WHEN** e2e 用该 fixture 起栈
- **THEN** 两个 tenant 各自的 placed agent 被 spawn 且健康，两 tenant 的 per-tenant 数据根目录（`<data_dir>/<tenant>/...`）各自独立存在

### Requirement: 跨租户数据查询零串数据 e2e

SHALL 有一条 e2e 验证：在 tenant-a 侧写入的数据（KB 条目或 agent 侧记忆），经 tenant-b 的读取/检索路径**查不到**；反向亦然。

#### Scenario: tenant-a 写入对 tenant-b 不可见

- **WHEN** 向 tenant-a 写入一条可检索数据，再经 tenant-b 的检索/读取路径查询同一内容
- **THEN** tenant-b 查询返回零命中，证明跨租户读路径不串数据

### Requirement: 文件级物理隔离 e2e

SHALL 有一条 e2e 验证：两 tenant 的持久化文件（KB 库、agent 运行库、向量库）落在**各自独立的物理路径**（`<data_dir>/<tenant-a>/...` vs `<data_dir>/<tenant-b>/...`），互不覆盖、互不共享。

#### Scenario: 两 tenant 落盘路径互不重叠

- **WHEN** 两 tenant 的 agent 各自产生持久化数据后
- **THEN** 文件系统上存在分属两 tenant 的独立 SQLite 文件，且任一 tenant 的库文件不出现在另一 tenant 的目录下

### Requirement: e2e 跑独立 slow lane，不进 per-merge 门禁

本 change 的多进程 e2e SHALL 在独立 slow/nightly lane 运行（`make test-e2e`），**不**纳入 per-merge `make test-pr` 门禁。

#### Scenario: per-merge 门禁不含本 e2e

- **WHEN** 跑 per-merge 门禁
- **THEN** 不运行本 change 的多进程隔离 e2e（它们在独立 lane）
