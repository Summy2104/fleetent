## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `run_code` 输出拼装点：`tools.py` 行 227-234 把 `result.stdout` / `result.stderr` 直接 `rstrip()` 后 join 返回，无长度约束；`SandboxClient.exec`（`sandbox_client.py` 行 235-252）的 `ExecResult.stdout` / `stderr` 为 `docker exec` 输出 `.decode()`，无大小限制
- [x] 1.2 核实字节口径与 T4 及既有计量一致：`tools.py` 行 220-221 trace 已用 `len(result.stdout.encode("utf-8"))` / `len(result.stderr.encode("utf-8"))`；兄弟 change T4 同口径 `len(s.encode("utf-8"))`。本 change 截断阈值与切分一律用字节口径，不用字符数 / token
- [x] 1.3 确认截断只作用于返回 AI 的拼装副本：`ExecResult` 不改、trace（行 220-221）仍记原始字节；stdout 与 stderr 各自阈值（默认 50KB / 10KB，对应 sandbox.md）；阈值常量可 `monkeypatch`，不引入全局可变状态

## 2. 截断函数与默认阈值（sandbox_output_truncation.py）

- [x] 2.1 Write failing tests for 截断函数：阈值内输入原样返回；超阈值输入被截断且字节数（`len(encode("utf-8"))`）不超过阈值；未传阈值时按调用方传入的流别常量。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement `truncate_stream(text, max_bytes=None)` 与模块级 `MAX_STDOUT_BYTES = 50 * 1024` / `MAX_STDERR_BYTES = 10 * 1024`（安全默认、可 monkeypatch），看到绿

## 3. 头尾保留 + 截断说明策略（sandbox_output_truncation.py）

- [x] 3.1 Write failing tests for 头尾 + 说明：截断结果以原始头部开始、原始尾部结束，中间含标明「原始字节数 / 省略字节数」的截断说明；头 + 尾 + 说明之和不超过阈值。看到红
- [x] 3.2 Implement 头尾保留 + 截断说明占位（预算分配保证不反超阈值），看到绿

## 4. 多字节字符安全切分（sandbox_output_truncation.py）

- [x] 4.1 Write failing tests for 多字节边界：字节预算边界落在多字节字符（如中文）中段时回退到完整字符边界，截断结果为合法 UTF-8、不含半个字符。看到红
- [x] 4.2 Implement 切点回退到完整 UTF-8 字符边界，看到绿

## 5. 阈值可注入、stdout/stderr 各自限额（sandbox_output_truncation.py）

- [x] 5.1 Write failing tests for 阈值可注入与各自限额：按次传入更小阈值生效；`monkeypatch MAX_STDOUT_BYTES` / `MAX_STDERR_BYTES` 改变默认行为；stdout 超限而 stderr 在限内时仅 stdout 被截、互不影响。看到红
- [x] 5.2 Implement 按次阈值覆盖 + 两流各自限额，看到绿

## 6. 接入 run_code 拼装点（tools.py）

- [x] 6.1 Write failing tests for run_code 输出截断：`run_code` 返回的 stdout 经 `MAX_STDOUT_BYTES` 截断、stderr 经 `MAX_STDERR_BYTES` 截断（字节数不超各自阈值、含截断说明），而同一次运行 trace 记录的 stdout/stderr 字节为**原始**大小、`ExecResult` 未被改。Docker CLI mock、路径隔离 tmp_path。看到红
- [x] 6.2 Implement：`run_code`（行 227-234）拼装前对 `result.stdout` 用 `MAX_STDOUT_BYTES`、`result.stderr` 用 `MAX_STDERR_BYTES` 分别调 `truncate_stream`；trace 记录（行 220-221）仍记原始字节，看到绿
- [x] 6.3 Write failing test for run_code 对 T4 豁免：`run_code` 声明 `self_truncates`、经 T4 的 opt-out 被 T4 跳过，输出不经 T4、不被二次截断（SB6 独占 `run_code` 截断）。看到红/绿确认边界

## 7. 收尾

- [x] 7.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [x] 7.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [x] 7.3 `uv run mypy src` 无新增错误
