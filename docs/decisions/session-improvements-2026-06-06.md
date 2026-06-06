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
