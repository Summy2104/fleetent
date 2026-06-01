## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `cron_scheduler._fire`（cron_scheduler.py 行 25-28）现状：仅构造 user 消息并调用 `agent_loop.run`，**不**传 `session_id`、**不** load/save session；确认接入点
- [ ] 1.2 核实 `schedule_store` 建表语句（行 21-36）现有列，`create` 签名（行 39-47）、`list_tasks` 用 `SELECT *` + `dict(row)`；确认增列 `session_id TEXT` 与 `create` 增可选参数的落点
- [ ] 1.3 核实 `session_mgr` 接口：`load(session_id)` 文件不存在返回空列表、`save(session_id, messages, user_id, agent_name)` 原子写并刷新元数据、`session_lock(session_id)` per-session 锁；确认 session_id 含 `/` 时 `save` 自动建子目录
- [ ] 1.4 核实 `load_cron_yaml`（cron_scheduler.py 行 31-52）的字段映射结构，确认增加 `session_id` 解析（缺省 None）不破坏既有静态任务加载

## 2. scheduled_tasks 承载 session_id（schedule_store.py）

- [ ] 2.1 Write failing tests for session_id 持久化：建表后 `create(..., session_id="cron/daily")` → `list_tasks` 返回字典含 `session_id="cron/daily"`；未传 `session_id` → 字典 `session_id` 为 None。`monkeypatch schedule_store.DB_PATH` 到 tmp_path。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement：建表语句增列 `session_id TEXT`（可空）；`create` 增可选参数 `session_id: str | None = None` 写入并纳入返回字典；`list_tasks` 经 `SELECT *` 自动带出。看到绿

## 3. 静态任务 YAML 承载 session_id（cron_scheduler.py）

- [ ] 3.1 Write failing tests for YAML 承载：`load_cron_yaml` 对声明了 `session_id` 的 job 返回含该字段的字典；未声明的 job `session_id` 为 None。`monkeypatch _CRON_YAML_PATH` 到临时文件。看到红
- [ ] 3.2 Implement：`load_cron_yaml` 增加 `"session_id": entry.get("session_id")` 映射。看到绿

## 4. 绑定语义——固定复用 vs 每次独立（cron_scheduler._fire）

- [ ] 4.1 Write failing tests for 独立语义：未配置 `session_id` 的任务触发两次，派生两个互不相同、形如 `cron/{task_id}/{run_uuid}` 的 session_id，每次 `load` 返回空。mock `agent_loop.run`、`monkeypatch session_mgr.SESSIONS_DIR` 到 tmp_path。看到红
- [ ] 4.2 Write failing tests for 固定语义：配置 `session_id="cron/daily"` 的任务先后触发两次，两次都用同一 session_id，第二次 `load` 读到第一次 `save` 的历史。看到红
- [ ] 4.3 Implement `_fire`：解析 `sid = task["session_id"] or f"cron/{task['id']}/{uuid.uuid4().hex}"`；在 `session_mgr.session_lock(sid)` 下 `load` → 拼接 user 消息 → `agent_loop.run` → 追加 assistant 回复 → `save(sid, messages, user_id=..., agent_name=...)`。看到绿

## 5. 触发接入 session_mgr load/save 与 per-session 锁

- [ ] 5.1 Write failing test for load/save 接线：固定语义触发时 `session_mgr.load` 被以正确 sid 调用、传入 `agent_loop.run` 的 messages 含历史+本次 user 消息、`session_mgr.save` 以 sid + 更新后 messages + `user_id`/`agent_name` 被调用。看到红
- [ ] 5.2 Write failing test for 同一固定 session 并发触发串行：两次并发触发同一固定 sid，经 per-session 锁串行，两次写入不互相覆盖（最终历史含两次的消息）。看到红
- [ ] 5.3 Write failing test for 元数据刷新：`save` 调用传入任务的 `user_id` 与 `agent_name`。看到红
- [ ] 5.4 Implement / 调整 `_fire` 使 5.1–5.3 通过（若 4.3 已覆盖则确认绿，必要时补全锁与 save 参数）。看到绿

## 6. 收尾

- [ ] 6.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [ ] 6.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 6.3 `uv run mypy src` 无新增错误
