## Context

`agent_admin_api.py` 有两个共用 `_build_agent_yaml(agent)` 的端点：
- `GET /admin/agents/{name}/agent-yaml`（`export_agent_yaml`，~line 154）— 只把渲染后的 yaml 文本放进响应体回显，**不写盘**。
- `POST /admin/agents/{name}/deploy`（`deploy_agent`，~line 162）— 把 yaml **写入** `paths.agent_home_dir(name)/agent.yaml`。

`deploy_agent` 用的是旧布局 `paths.agent_home_dir(name)`（= `agents/<name>/`），但 tenant-first 后 runtime 从 `tenants/<tenant>/agents/<name>/` 读，故其产物不会被加载；同时它让 platform 写 agent home，违反决策 A。无 spec 定义、无产品消费者（仅测试）。

## Goals / Non-Goals

**Goals:**
- 删除死代码端点 `deploy_agent` 及其测试。
- 把"platform 不写 agent home"固化为 `platform-control-plane` 的 spec 断言。

**Non-Goals:**
- 不动 `export_agent_yaml` 与 `_build_agent_yaml`（只读回显，无害且仍被使用）。
- 不碰 `rename-admin-cli-to-platform` 的 CLI 改名范围。
- 不改 agent home 物化的现有实现（node reconcile / CLI init 已是唯一 owner）。

## Decisions

### D1 — 只删 `deploy_agent`，保留 `_build_agent_yaml` + `export_agent_yaml`

`_build_agent_yaml` 有两个调用方；`export_agent_yaml`（GET 回显）不写盘、不违反决策 A，保留。仅删 `deploy_agent`（写盘那个）+ 它独占的写盘逻辑（`dest = ...; dest.write_text(...)` + audit `agent.deploy`）。
**为何**：精准移除违规面，不误伤只读投影。

### D2 — spec 落点：`platform-control-plane` 新增 ADDED requirement

与既有 `Agent execution endpoints are not on the platform`（不服务 /chat /ws /webhook）同精神——平台是纯控制面，既不执行 agent、也不物化 agent home。新增独立 requirement 而非 MODIFY 那条（执行端点 vs home 写入是两个关注点，分开断言更清晰），并显式允许只读 config 投影（给 `export_agent_yaml` 留位）。
**为何**：把决策 A 从架构文档提升为可被 spec/测试守护的断言，防再生同类端点。

## Risks / Trade-offs

- **[删 HTTP 端点是 BREAKING]** → 无产品消费者（前端无、仅测试调），实际零影响；移除测试即可。
- **[误删 `_build_agent_yaml` 会打断 export_agent_yaml]** → D1 明确只删写盘端点，保留共享 helper；apply 时跑 `export_agent_yaml` 相关测试确认仍绿。
- **[负向 spec 断言难测]** → 可加一条断言"platform app 无 `POST /admin/agents/{name}/deploy` 路由"（404）的测试，把 spec scenario 落成可执行守护。

## Migration Plan

- 纯删除 + spec 断言，无数据/schema 迁移、不留 shim。
- 回滚：恢复 `deploy_agent` 函数与路由即可。

## Open Questions

- 无。
