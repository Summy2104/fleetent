## Context

一轮平台侧 UI ↔ API ↔ 管理库表的三面对齐审计发现：核心业务域三面健康，但累积了一批可证伪的死代码。审计结论经第二轮证据核查后修正——多数「死表」其实已被历史迁移删除（`im_channel_allowlist`/090、`channel_agents`/087、`connectors.agent_id`/093、`model_routes`/086），真正还活着的只有少量孤儿代码、墓碑端点、stale 规格与一处死列。

本变更只做债务清理：删确证无用之物，结构与「后端齐·UI 缺」的半成品一律不动（按用户决策 A）。改动全部落在 `platform` 包与 `static/admin.html`，不触碰 agent 运行时，因此「无 platform 时 agent 仍能 `agent run`」的验证基线不受影响。

## Goals / Non-Goals

**Goals:**
- 删除无任何调用方的 observability 孤儿 API（整模块）。
- 删除已返回 404/409 的墓碑端点（provider routes ×3、skill proposals approve/reject ×2）及其 UI 入口。
- 删除调用不存在后端的坏死 UI（Chat playground、Stats reports 按钮）。
- drop 已被规格声明删除、却仍物理存在的 `im_users.allowed` 列。
- 把因上述删除而 stale 的规格（observability-admin-api、session-admin-ui、session-admin-console、stats-admin-ui、skill-proposal-review、skill-admin-ui）与代码现实对齐。

**Non-Goals:**
- 不缩减任何结构能力（多租户 / 多节点编排 / KB / 技能治理全留）。
- 不动「后端 + 表已齐、仅缺 UI」的半成品（agent IM 访问、默认 agent、API key 吊销、节点编排 UI、KB 内容生命周期）——单列「待接 UI」backlog。
- 不改 agent 运行时；不改 IM 身份解析的既有行为（解析仍走 `users.status`）。
- 不退役 CLI `observability` 命令（它仍是 observability 查询入口）。

## Decisions

**1. 删除单位 = 垂直切片，切片内部 UI → API → 表 顺序。**
依赖方向是 UI→API→表，安全删除必须逆依赖、自上而下：先摘 UI 引用，再删 API 路由/桩，最后落迁移删列。每个切片自成一个可独立验证的完整删除，避免「先删一批表再删一批 API」造成的破损中间态。备选：按层分三趟批量删——否决，中间态必破、过不了护栏测试。

**2. Provider 路由与 `im_users.allowed` 仅 code/schema 删除，不写 spec delta。**
`provider-admin-api` 规格已声明「routing truth 离开管理 DB」、`im-user-allowlist` 规格已声明「`im_users.allowed` flag removed」——规格已正确，代码/schema 落后。这两个切片是让实现追上规格，无 requirement 变化，故不产 delta。

**3. skill 提案审批：删桩 + 对齐 stale 规格，而非引入行为变更。**
审批已是 agent-owned、经 DM 投递的既定模型（R1 决策；平台只读下游投影）。代码早已是 409 桩，但 `skill-proposal-review`/`skill-admin-ui` 规格仍要求平台写入式 approve/reject——这是规格 stale。本次删桩 + 删按钮 + 收缩规格为「列表 + diff 只读」，是让三者一致，不改变任何运行时审批行为。

**4. session-admin-console 最小手术。**
playground 移除后，会话列表对 `origin=playground` 的排除是无害且仍正确的过滤（历史/其它来源的 playground-origin 会话仍应被排除），保留不动；仅在「Chat management permissions and audit」requirement 删去对 playground 试聊的提及。避免重写正在工作的治理规格。

**5. observability 整模块删除而非保留空壳。**
`observability_management/` 仅 `__init__.py` + `observability_admin_api.py` 两文件、无 store、唯一引用方是 `server.py` 注册行。整模块删除最干净，无 shim 需求（无人 import）。

## Risks / Trade-offs

- **[误删仍被使用的端点]** → 已由第二轮证据核查逐项确认无调用方（UI/CLI/测试全 grep）；删除后 `make test-pr` + 集成回归兜底。
- **[`im_users.allowed` 删列触及运行时身份解析]** → 唯一带迁移 + 代码的切片。先以 TDD 写「删列后 IM 身份解析仍走 `users.status`、insert 路径不再写 `allowed`」的红/绿；迁移为 forward-only drop column。
- **[migrations 撞号]** → 取当前最新版本号（已到 099）之后的下一号，apply 前 `git pull` 并核对 head；遵循「外部凭证库 Vault」记录的合并期撞号教训。
- **[archive 同步遗漏 spec delta]** → 已知 gotcha（apply 不一定完整合并 spec delta）；archive 阶段逐文件核对 6 个 delta 是否落入 `openspec/specs/`。
- **[stale 规格的语义判断错误]** → 若 skill 审批/observability 的「现实」与我判断相反（即规格才是目标、代码是回归），删除方向就错了。缓解：proposal 已显式声明依据（409/404 桩文案 + R1 决策 + 规格既有声明），apply 前请用户确认该前提。

## Migration Plan

- **DB**：新增一支 forward 迁移 `<next>_drop_im_users_allowed`，drop `im_users.allowed`。无 downgrade 数据恢复需求（列恒为 1、无信息量）。
- **部署顺序**：纯删除，无运行时灰度需求。合并即生效；旧客户端/脚本若曾调用被删端点将收到 404（原本即 404/409 或无路由，无回归）。
- **回滚**：代码层 `git revert`；DB 层该列删除不可逆但无数据价值，回滚仅需在迁移上补回空列（如确有需要）。
