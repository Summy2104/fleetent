> **[历史记录]** 本文档为 file-exchange 功能的执行计划过程产物，该功能已落地（`artifact_exchange.py`）。内容以落地代码为准。

# file-exchange ③ 自动化执行工作流（待审核 — 审核通过后才执行）

> 生成 2026-06-13。基线：`feat/unified-file-exchange`（= main `4ffa31c` + 本会话未提交的 D0 修订）。
> 目标：完成 `unified-file-exchange`（③）剩余实现，9 spec / tasks §0–§8，含 2026-06-13 的 D0 归属轴修订。
> 约束：无人值守夜跑，**晨起审 diff**。核心 MCP/沙箱子系统改动，安全 > 速度。

---

## 0. 范围

**做**：③ 的 tasks §0–§8 **全部**（Docker/live 任务改 mock/可跳过形式，使全部 checkbox 可勾 → 可 archive）。
**不做**：
- ④ delivery-receipts-postcondition（独立 change，硬依赖 ③ §7 内核，③ 收口后另起）。

**Docker/live 任务的 mock 化处理**（2026-06-13 决策：改可跳过/mock 以便 archive）：
- §4.5 容器内 `/exchange` 只读 + 链接即时可见：以 **mock docker run 命令组装等价覆盖**（断言挂载选项装配正确）+ `@pytest.mark.skipif` 标记真机断言；真机决定性验证留用户环境补跑。
- §4.6 挂载选项补齐：同上，mock 装配覆盖。
- §8.4 my-bot 真机重放：改为**等价持久层/装配验证**（真实 sqlite + mock docker/MCP/LLM 重建链路），真机重放留用户环境。
- 三者均在决策文档写明「mock 覆盖 + 真机待补」，archive 不代表真机已验证。

---

## 1. ⚠️ 执行前必须由你确认的 2 个 gating 决策

1. **产文件的 MCP server 是 stdio 本地进程吗？**（如本地 `google-workspace-mcp`）
   - 是 → 本套「本地文件交换区」机制成立，按计划执行。
   - 若云端 HTTP server（文件不在本地）→ **整套机制不适用，③ 需推翻重议**，不应启动本计划。
2. **discovery 两层都做吗？**（设计 D2：咽喉确定性改写 + 调用窗口 diff 兜底）
   - 默认：**都做**（diff 是正确性兜底，结果未提路径时的安全网；结构成独立可测层）。
   - 若只做咽喉改写 → §2.5/2.6 跳过，diff 兜底缺失（结果不带路径的产物会漏登记）。

---

## 2. 起点

- **step 0**：把本会话未提交的 D0 修订（design.md / 6 specs / tasks.md / HANDOFF.md / 本计划）提交为 1 个 `docs(file-exchange): D0 归属轴修订 + 自动化计划` commit，分支 clean 后再进实现。

---

## 3. 依赖 DAG（task 区段）

```
                 ┌─────────────────────────────────────────────┐
   §0 地基 ──────┤ workspace_scope_key 权威 + v33 + 重做 exchange │  (阻塞全部)
                 └───────────────┬─────────────────────────────┘
                                 │
            §2.2残留: MCP agent_home 解析 + stdio cwd + register_server_root
                                 │  (解锁 server-root → §2.3/§3/§4)
        ┌────────────────────────┼───────────────────────────────┐
        │                        │                                │
   §2.3/2.4 咽喉改写+登记     §3 fence 双根                  §4.3/4.4 backend
        │  (改 mcp/client)     (改 file_sandbox_io/         exchange_mount 能力
   §2.5/2.6 diff 兜底          file_tools)                  (改 backend/docker/manager)
        │                        │                                │
        └──── §4.1/4.2 视图管理 (改 artifact_exchange) ────────────┘
                                 │  (与 §2.3/2.4 同改 exchange，串行)
                                 ▼
                §6 send_file → §7 send_im_message files  (同改 builtin_tools，串行)
                                 ▼
                §8.1/8.2 全量门禁 + §8.3 文档   [§8.4 真机→defer]
```

- §5 permission-gate（callable risk）**已实现**（main 已含），但要等 §6 接入才真正生效。

---

## 4. 阶段编排

| Phase | 任务 | 关键文件 | 依赖 | 备注 |
|---|---|---|---|---|
| **P0 地基** | §0.1–0.6 | `manager.py`(scope_key 权威)、`agent_state_migrations.py`(v33)、`artifact_exchange.py`(重做) | — | **阻塞全部**；签名固化后才允许下游并行 |
| **P1 MCP 地基** | §2.2 残留 | `integrations/mcp/client.py`(+ agent_home 解析) | P0 | **最高风险**（owner-task / anyio cancel scope，见 §6） |
| **P2 登记** | §2.3/2.4 → §2.5/2.6 | `mcp/client.py`、`artifact_exchange.register` | P0+P1 | scope_key 经 dispatch→咽喉穿线 |
| **P3 fence 双根** | §3.1/3.2 | `file_sandbox_io.py`、`file_tools.py` | P0+P1 | 只读用 `resolve` |
| **P4 沙箱视图+挂载** | §4.1/4.2 视图；§4.3/4.4 能力+挂载；§4.7/4.8 staging | §4.1/4.2→`artifact_exchange`；§4.3/4.4→`backend.py`/`docker.py`/`manager.py` | P0(+P1) | §4.5/4.6 Docker→**defer** |
| **P5 send 工具** | §6.1–6.4 → §7.1/7.2 | `builtin_tools.py`、`registry` | P0+P3+P4视图 | 同文件串行 |
| **P6 收尾** | §8.1/8.2 门禁；§8.3 文档 | `AGENTS.md`、`agent.yaml.example` | 全部 | §8.4 真机→**defer** |

---

## 5. 并发规划（可选）

P0 + P1 完成、`artifact_exchange` 签名固化后，以下三条**文件不相交**，理论可并发：

- **Track A**：P2（`mcp/client.py`）
- **Track B**：P3（`file_sandbox_io.py` / `file_tools.py`）
- **Track C**：P4 能力位 §4.3/4.4（`backend.py` / `docker.py` / `manager.py`）

冲突约束：**§4.1/4.2 视图管理改 `artifact_exchange.py`，与 Track A 的 `register` 同文件 → 必须串行**（紧随 P0 或 Track A 之后，不与 A 并发）。P5 需三 Track join 后做。

**推荐：默认串行。** 理由：①核心基建 + 无人值守，墙钟不是夜间约束；②串行 git 历史线性、逐 task 一 commit，**晨审最容易**；③并发省墙钟但增冲突/审核成本。并发作为你可选开关，若选并发则按上面三 Track 编排、P0/P1 后扇出、P5 前 join。

---

## 6. TDD 与门禁纪律（每 task 强制）

- **红 → 绿**：`uv run pytest <file>::<test> -x -q`，先见红再实现见绿（直接绿=测试没覆盖目标，先修测试）。
- **每 task 收尾**：受影响层（unit 或 integration）无新增失败。
- **每 Phase 收尾**：commit（`type(scope): 描述`，逐 task 或逐 phase 粒度）。
- **全程收口**：`make test-pr` 全绿 + `uv run pytest tests/integration -q`（不带 -x，对照 main 基线无新增失败）+ `uv run mypy src` 无新增（基线 89）。
- 门禁判据 = **无新增失败**（非零失败；预存 ~2 unit + ~19 integration 失败非本次责任）。

---

## 7. 风险控制 / STOP 条件（无人值守关键）

1. **MCP owner-task / anyio 契约（P1 最高优先级）**：§2.2 改 transport 启动**必须**守「enter/exit 同 task」「禁模块级 AsyncExitStack 持活资源」（2026-06-11 事故区，护栏强制）。agent_home 解析走 `scope→agent_id→paths.agent_home_dir`，确认能干净拿到再动。
2. **硬 STOP**：任一 task 多次尝试仍红，或触发 MCP/沙箱核心回归 → **停下、如实记录现状、不 hack、不跳步**（沿用上次夜跑的稳健策略）。
3. **不越界改休眠代码**：除 §0 计划内重做，不动其它已合入脚手架。
4. **逐 Phase 合 main**：每 Phase 绿 → `bb-pr` 合 main（CI 门控，CI 不过不合）；main 始终可构建。最终 Phase 收口 archive + sync specs。**不在 main 不可构建状态下推进**。
5. **真机任务 mock 化**：§4.5/4.6/§8.4 以 mock/可跳过形式实现（见 §0），不在无人值守跑真 Docker/live。

---

## 8. 执行载体

- **主循环自主驱动 + 逐 Phase bb-pr**：`bb-pr` 是主循环技能（双 remote / yang.zhang 开 PR + admin 合并 / CI 轮询 / 冲突处理），不可塞进脱离会话的后台子代理。故由我在主循环按 Phase 串行驱动：每 Phase「TDD 开发 → 门禁绿 → `bb-pr` 合 main → 记录决策 → 下一 Phase」，全程自主、不停下问，硬 STOP 时记录。
- Phase 内若有大块可并行实现，可临时 dispatch 聚焦子代理，但 merge 始终回主循环。

---

## 9. 终态与审批交付物（你在 main 上审）

- **main 分支**：§0–§8 全部实现并逐 Phase 合入；change 完成后 **archive + sync specs**（Docker/live 以 mock 覆盖使 checkbox 可勾）。
- **决策文档** `docs/file-exchange-series-apply-decisions.md` ③ 节：每 Phase 的问题、自做决策/偏离、门禁结果、STOP（如有）、**真机待补清单**（哪些是 mock 覆盖、需你环境补真机）。
- **审批**：你在 main + 决策文档上复核，需要时我跟进修。

---

## 10. 已锁定的执行参数（2026-06-13 用户确认）

1. ✅ 产文件 server = **stdio 本地**（可执行）→ 机制成立，按计划执行。
2. ✅ discovery **两层都做**（咽喉改写 + diff 兜底，含 §2.5/2.6）。
3. ✅ **串行**（默认推荐）。
4. ✅ 载体 = **Workflow 后台 + 串行管线**（journaled / resumable，夜跑晨审）。
5. ⏳ 待最终「启动」确认。

启动序列（GO 后）：① 提交 D0 修订 docs commit（分支 clean）→ ② 编排并启动后台 Workflow（P0→P1→P2→P3→P4→P5→P6，串行，§7 STOP 条件全程生效）→ ③ 夜间无人值守 → ④ 晨起审 `feat/unified-file-exchange` 分支 + 执行报告（不 archive/不 PR）。
