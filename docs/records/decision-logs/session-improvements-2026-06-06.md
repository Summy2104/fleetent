# Session 系统改进决策记录（2026-06-06）

本文档记录基于对标 hermes-agent / claude-code / openclaw / opencode 后，对 fleetent session 系统的系列改进中的关键决策与遇到的问题。供后续审核。

## 任务总览

| # | 任务 | change 名 | 状态 |
|---|------|----------|------|
| 1 | session 日志迁移 + index 幽灵记录 + 分页 | session-reliability-baseline | ✅ 已合并归档 (PR #128/#129) |
| 2 | P0-3 压缩检查点 | session-compaction-checkpoint | ✅ 已合并 (PR #134) |
| 3 | P0-4 跨进程文件锁 | session-cross-process-safety | ✅ 已合并 (PR #135) |
| 4 | P1-3 Token 累计持久化 | session-token-tracking | ✅ 已合并 (PR #137) |
| 5 | P1-1 重启后 session 恢复 | session-restart-recovery | ✅ 已合并 (PR #139) |
| 6 | Tool result 外部化 | session-tool-result-extern | ✅ 已合并 |

---

## 关键决策

### D1：文件锁方案（P0-4）
**决策**：使用 `fcntl.flock()`（POSIX 原生），不引入 `filelock` 第三方库。
**理由**：
- 零依赖，符合 CLAUDE.md「新依赖必须讨论」原则
- fleetent 定位企业 on-premises Linux 部署，无 Windows 需求
- session 文件存本地磁盘（非 NFS），flock 完全可靠
- 双层锁：文件锁（跨进程）+ asyncio.Lock（同进程协程）

### D2：压缩检查点注入位置（P0-3）
**决策**：checkpoint 在 `maybe_compress`/`compress_for_context_overflow` 中注入，不在纯函数 `_compress` 内部。
**理由**：保持 `_compress` 纯算法特性，不依赖持久化层。

### D3：session_meta 列而非 session JSON meta（P0-3）
**决策**：压缩记录写入 SQLite session_meta 表（migration 054），而非 session JSON 文件的 meta 字段。
**理由**：管理控制台需要按 session 查询压缩历史，SQLite 可索引、可聚合查询。

### D5：token / resume 标记加在 session_meta（Alembic）而非 index.py sessions 表（P1-3/P1-1）
**决策**：token 累计列、resume_pending 列均加到 session_meta（Alembic 管理），不加到 index.py 的 sessions 表。
**理由**：index.py 的 sessions 表用 CREATE TABLE IF NOT EXISTS 自建，不归 Alembic，无法用 migration ALTER（全新 DB 只跑 migration 时表不存在会失败）。session_meta 是 Alembic 管理的正规表，符合 CLAUDE.md「schema 归 Alembic」。与 P0-3 compaction meta 一致。

### D6：重启恢复扫描挂 agent_app._start_infra，非 server.py lifespan（P1-1）
**决策**：resume_pending 启动扫描在 agent_app._start_infra 的 start_session_maintenance() 之后调用。
**理由**：platform server 已不维护 session（server.py 注释 platform-control-plane）；session 维护任务本身就在 _start_infra 启动，恢复扫描与之同址，职责一致。agent run 进程才是 session 宿主。
**窗口**：120 秒（对标 hermes-agent）；标记式恢复（不保存 loop 状态），下次请求靠已落盘 session 文件 + resume_pending 标记由上层决定续接。本 change 只建机制，消费逻辑（normalizer/loop 续接）属后续 wiring。

### D7：tool result 外部化路径与引用（Tool result extern）
**决策**：>50KB（_TOOL_RESULT_INLINE_LIMIT）的 role=tool 字符串 content 外部化到 `{session_id}.tool_outputs/{tool_call_id}.txt`，消息存 `[stored:{id}.txt]` 引用。
**理由**：对标 claude-code（>50KB 单独持久化），减少 session JSON 体积和 LLM context 占用。externalize/rehydrate 为纯函数（不 mutate 入参），与 message_hygiene/压缩风格一致。cleanup 连带删除 .tool_outputs 目录，扫描跳过该目录。文件缺失时 rehydrate 保留引用占位（容忍解耦删除）。
**范围**：本 change 建 externalize/rehydrate 能力 + 清理；save/load 路径接入（何时调用）属后续 wiring，不破坏现状。

---

### D8：resume_pending 消费闭环（wiring 接入点 1，PR 见总结）
**决策**：normalizer 在 load 后、跑 loop 前检测 resume_pending，命中则记 session_resumed 日志 + 立即 clear（非 save 后），整段 best-effort。
**理由**：标记是「本次请求是中断恢复」的一次性提示，请求开始处理即完成使命；run 失败时 session 文件仍完整、下次正常 load，无需靠标记重试；立即清除避免误报循环。仅 IM 路径。续接数据基础是已落盘 session 文件，标记仅运营可见性。

### D9：token usage wiring 不改 run() 返回类型（wiring 接入点 2，已实现）
**决策**：run() 当前返回纯 str 且被 run_sync/normalizer/cron/大量测试调用，改返回类型破坏面大。改为给 run() 加可选参数 usage_out: list | None = None，run 内部拿到 usage 后若非 None 则 append (prompt_tokens, completion_tokens)；normalizer 传入空 list，run 后读取传给 save(token_usage=...)。零破坏现有调用方。

## wiring 完成说明
原「建机制」的三项渐进 wiring 已接入运行路径：
- 接入点 3（tool 外部化 save/load）：PR #158 已合并
- 接入点 1（resume_pending 消费）：本批接入
- 接入点 2（token usage）：本批接入完成（D9 方案，PR 见下）


## 遇到的问题与解决

### P1：tasks 文档写"sessions 表"但实际表名是 session_meta（P0-3）
- session_admin_store 管理的表是 `session_meta`，不是 index.py 的 `sessions` 表
- 解决：migration 054 正确地向 `session_meta` 加列

### P2：Logger 是 frozen dataclass，无法 monkeypatch 方法
- 测试中 `monkeypatch.setattr(_logger, "warn", ...)` 报 FrozenInstanceError
- 解决：改用 `patch("module._logger")` 替换整个 logger 对象

### P3：unit 测试 monkeypatch DB_PATH 触发测试层检查告警
- check_test_layers.py 禁止 unit 测试 mutate 生产 DB_PATH
- 解决：测试已 mock delete_batch，移除多余的 DB_PATH monkeypatch

### P4：_database() 不支持 context manager 协议
- session_admin_store 中应使用 `_database().transaction()` 而非 `with _database()`
- 解决：统一用 `.transaction()`


## Agent/Platform 解耦返工（2026-06-07）

发现并修复：此前 token/compaction/resume 三类 agent 运行时数据被写入 platform 的 session_meta 表，违反 Agent/Platform 解耦（agent 独立运行时该表不存在，功能静默失效）。

### D10：resume_pending 迁移到 agent 侧 .resume 标记文件
**决策**：resume_pending 从 platform session_meta 列迁移到 agent 侧 `{session_id}.resume` 兄弟标记文件（与 .pre-compact.json / .tool_outputs 同模式）。mark=touch、is=exists、clear=unlink、scan 基于 session 文件 mtime。
**理由**：纯 agent 侧、零 DB、零 platform，agent 独立运行天然可用；独立标记文件零副作用（不刷新主文件 mtime）。

### 返工结果：4 处违规依赖全部清除
- token usage（PR #163 返工 1/2）：回退，走 observability trace
- compaction stats（PR #163）：回退 session_meta 写入，保留 .pre-compact.json，走 trace
- resume_pending（返工 2/2）：迁移到 agent 侧 .resume 标记文件
- migration 058（降 token×2+compaction×4 列）+ 059（降 resume_pending 列）
- 验证：runtime/session/im_gateway 不再 import platform.chat_management，agent 可真正脱离 platform 独立运行