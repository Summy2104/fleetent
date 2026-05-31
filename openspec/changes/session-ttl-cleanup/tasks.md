## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `session_mgr.py` 现状：`SESSIONS_DIR`（行 13，可 monkeypatch）、`save()` 原子写 `.json.tmp → rename`（行 37-42，写入即刷新目标文件 mtime）、`load()` 路径构造 `SESSIONS_DIR / f"{session_id}.json"`（行 31）
- [ ] 1.2 确认 `config.py` 的 `Settings` 是否已含 `session_ttl_days`；若无则本次新增（沿用 `context_max_tokens` / `permission_gate_*_timeout_seconds` 同类 env 字段模式）
- [ ] 1.3 确认带 `/` 的 session_id（如 `u123/dm:U08XYZ`）落盘为子目录文件，清理需用 `rglob` 递归并由相对路径还原 session_id

## 2. 配置接入（Settings + _default_config，对齐 context_mgr 模式）

- [ ] 2.1 Write failing tests：`Settings` 含 `session_ttl_days`（默认 30）；`session_mgr._default_config()` 返回 `ttl_seconds`（= 30 * 86400）且可被参数覆盖。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement：`config.py` 的 `Settings` 增加 `session_ttl_days: int = 30`（若尚无）；`session_mgr.py` 增加 `_default_config()`（惰性 `from fleetent.config import Settings`，同 context_mgr）。运行 `uv run pytest -x -q` 看到绿

## 3. 过期判定（is_expired 纯函数）

- [ ] 3.1 Write failing tests for `is_expired(mtime, now, ttl_seconds)`：`now - mtime > ttl` 返回 True，否则 False；边界（恰好等于 ttl）不算过期。看到红
- [ ] 3.2 Implement `is_expired()` 纯判定函数，看到绿

## 4. 清理函数 cleanup_expired —— 基本删除

- [ ] 4.1 Write failing tests（monkeypatch `SESSIONS_DIR → tmp_path`，用 `os.utime` 伪造过期/未过期 mtime）：过期文件被删、未过期文件保留、返回被删 session_id 列表。看到红
- [ ] 4.2 Implement `cleanup_expired(ttl_seconds=None)`：`rglob("*.json")` 扫描、`is_expired` 判定、`unlink` 删除、回落 `_default_config()`、返回 session_id 列表。看到绿

## 5. 清理函数 —— 排除临时文件与子目录 session_id 还原

- [ ] 5.1 Write failing tests：目录含 `.json.tmp` 时不被删除；带 `/` 的 session_id（子目录文件）过期时被删且返回值还原为含 `/` 的原始标识。看到红
- [ ] 5.2 Implement：扫描显式排除 `.json.tmp`；由相对 `SESSIONS_DIR` 的路径去 `.json` 后缀还原 session_id。看到绿

## 6. 清理函数 —— 删除容错与日志

- [ ] 6.1 Write failing tests：mock 某文件 `unlink` 抛异常，验证整批不中断、其余过期文件仍被删、不向上抛异常。看到红
- [ ] 6.2 Implement：单文件删除 try/except 捕获后 `logger.warning` 继续；成功删除 `logger.info`；整批结束记汇总日志。看到绿

## 7. TTL 参数覆盖集成

- [ ] 7.1 Write failing tests：显式传 `ttl_seconds` 时覆盖 Settings；不传时回落 `_default_config()`（monkeypatch `_default_config` 注入，不实例化真 `Settings`）。看到红
- [ ] 7.2 Implement：`cleanup_expired` 的 `ttl_seconds` 参数解析优先级（参数 > Settings > 字段默认）。看到绿

## 8. 收尾

- [ ] 8.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`，项目要求）确认无回归
- [ ] 8.2 我的文件 `uv run ruff format src tests && uv run ruff check src tests` 全绿；`uv run mypy src` 不新增错误模式
- [ ] 8.3 复核 `load()` / `save()` / `session_lock()` 既有行为与原子写契约未受影响（既有测试仍绿）
