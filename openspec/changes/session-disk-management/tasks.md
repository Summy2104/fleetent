## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `session_mgr.py` 现状：`SESSIONS_DIR`（行 13，可 monkeypatch）、`save()` 原子写刷新目标文件 mtime（行 37-42）、路径含子目录的 session_id（如 `u123/dm:U08XYZ`，需 `rglob` 递归 + 相对路径还原 session_id）
- [ ] 1.2 确认 `config.py` 的 `Settings` 是否已含 `session_max_total_mb` / `session_max_count`；若无则本次新增（沿用既有 env 字段模式）
- [ ] 1.3 确认是否已有 `session_mgr._default_config()`（若 `session-ttl-cleanup` 已建则扩展，否则新建）

## 2. 配置接入（Settings + _default_config，对齐 context_mgr 模式）

- [ ] 2.1 Write failing tests：`Settings` 含 `session_max_total_mb`（默认 1024）、`session_max_count`（默认 10000）；`session_mgr._default_config()` 返回 `max_total_bytes`（= mb * 1024 * 1024）与 `max_count` 且可被参数覆盖。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement：`config.py` 的 `Settings` 增加两字段；`session_mgr._default_config()` 增加/扩展返回两上限（惰性 `from fleetent.config import Settings`，同 context_mgr）。看到绿

## 3. 扫描与超限判定（纯函数）

- [ ] 3.1 Write failing tests for 扫描辅助 + `is_over_capacity(total_bytes, count, max_total_bytes, max_count)`：任一有效维度超限返回 True；均未超限返回 False；维度为 0（关闭）时不参与判定。看到红
- [ ] 3.2 Implement 扫描辅助（收集 `(session_id, size, mtime)`，排除 `.json.tmp`）+ `is_over_capacity()` 纯判定。看到绿

## 4. LRU 淘汰 —— 基本淘汰至阈值

- [ ] 4.1 Write failing tests（monkeypatch `SESSIONS_DIR → tmp_path`，构造不同 size 与 `os.utime` mtime）：超总大小时按最旧优先删除至回落阈值、返回被删 session_id 列表、不过度淘汰。看到红
- [ ] 4.2 Implement `enforce_capacity(max_total_bytes=None, max_count=None)`：扫描 → 按 mtime 升序排序 → 逐个删除并扣减累计 → 双约束满足即停 → 回落 `_default_config()`。看到绿

## 5. LRU 淘汰 —— 数量维度与维度关闭

- [ ] 5.1 Write failing tests：超数量上限按最旧优先淘汰至数量回落；某维度上限为 0 时该维度不触发/不停止；两维度均为 0 时不淘汰任何 session。看到红
- [ ] 5.2 Implement：数量维度判定与停止条件；维度为 0 时跳过该维度。看到绿

## 6. LRU 淘汰 —— 排除临时文件与子目录 session_id 还原

- [ ] 6.1 Write failing tests：目录含 `.json.tmp` 时不被删除；带 `/` 的 session_id（子目录文件）超限被淘汰时返回值还原为含 `/` 的原始标识。看到红
- [ ] 6.2 Implement：扫描排除 `.json.tmp`；由相对 `SESSIONS_DIR` 路径去 `.json` 后缀还原 session_id。看到绿

## 7. 删除容错与日志

- [ ] 7.1 Write failing tests：mock 某文件 `unlink` 抛异常，验证整批不中断、其余待淘汰文件仍被删、不向上抛异常；日志记录触发原因（超大小 / 超数量）。看到红
- [ ] 7.2 Implement：单文件删除 try/except 捕获后 `logger.warning` 继续；触发时记原因与被淘汰数量汇总日志。看到绿

## 8. 收尾

- [ ] 8.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`，项目要求）确认无回归
- [ ] 8.2 我的文件 `uv run ruff format src tests && uv run ruff check src tests` 全绿；`uv run mypy src` 不新增错误模式
- [ ] 8.3 复核 `load()` / `save()` / `session_lock()` 既有行为与原子写契约未受影响（既有测试仍绿）
