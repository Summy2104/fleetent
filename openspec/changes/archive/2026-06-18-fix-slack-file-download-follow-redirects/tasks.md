# Tasks

> 每个实现 task 严格 TDD：先写测试跑最窄命令**见红** → 写实现**见绿** → 可选 refactor。
> 测试任务排在对应实现任务之前。基线对照 main（门禁判据＝无新增失败）。
> 最窄命令：`uv run pytest tests/unit/test_slack_file_download.py -x -q`

## 1. 前置核实（不改产线代码，定 scope）

- [x] 1.1 复读 `src/fleetent/im_gateway/slack.py` 的 `_download_attachments`（~285-343），确认图片分支（~307）与文件分支（~316）共用 `httpx.AsyncClient()`（~301），及失败降级 / size 上限的现有结构
- [x] 1.2 确认现有 `tests/unit/test_slack_file_download.py` 的 `_FakeClient` / `_Resp` 夹具结构与 `_patch_client`（`patch("httpx.AsyncClient", return_value=client)`），定 `_Resp` 需补 `headers` 字段的最小适配点

## 2. 跟随重定向（TDD：红 → 绿）

- [x] 2.1 **测试先行**：在 `test_slack_file_download.py` 新增 `test_client_follows_redirects` —— 用捕获 kwargs 的 patch（`side_effect` 记录 `httpx.AsyncClient(**kwargs)` 调用并返回 `_FakeClient`），下载任一文件后断言捕获到的 kwargs 含 `follow_redirects is True`。跑最窄命令 **见红**（现状未传该参数）
- [x] 2.2 **实现**：`_download_attachments` 的 `httpx.AsyncClient()` → `httpx.AsyncClient(follow_redirects=True)`。跑 2.1 命令 **见绿**

## 3. HTML 响应兜底（TDD：红 → 绿）

- [x] 3.1 **测试先行**：给 `_Resp` 加 `headers`（默认空 dict 或可传入）。新增两条用例：
  - `test_html_response_file_degrades_to_placeholder`：文件分支响应 `content-type: text/html; charset=utf-8`、body 为 HTML → 断言 `out[0].data is None`、`out[0].note != ""`、且 `out[0].data` 不是 HTML body
  - `test_html_response_image_skipped`：图片 url 响应 text/html → 断言该图片不进 out（被跳过）
  跑最窄命令 **见红**（现状无 content-type 判断，会把 HTML 当字节）
- [x] 3.2 **实现**：两分支在 `raise_for_status()` 之后取 `resp.headers.get("content-type","")`，`.split(";")[0].strip()` 以 `text/html` 开头时——文件分支记 warning + `FileAttachment(data=None,...,note=...)`；图片分支记 warning + `continue`。不取/不返回 HTML 字节，不抛异常。跑 3.1 命令 **见绿**

## 4. 既有用例回归 + lint

- [x] 4.1 跑整文件 `uv run pytest tests/unit/test_slack_file_download.py -q`：原 5 个用例（含 `_Resp` 加 headers 后）+ 新增用例全绿
- [x] 4.2 `uv run ruff check src/fleetent/im_gateway/slack.py tests/unit/test_slack_file_download.py` 通过；`uv run ruff format` 受影响文件无 diff

## 5. spec 同步

- [x] 5.1 确认 `openspec/changes/fix-slack-file-download-follow-redirects/specs/im-file-attachment/spec.md` 的 MODIFIED 要求与实现一致（跟随重定向 + HTML 兜底两条），scenario 覆盖 302/HTML/200-无副作用/图片跳过

## 6. 收尾验证

- [x] 6.1 `make test-pr`：3197 passed，仅 1 个**预先存在且无关**的失败 `test_config.py::test_observability_logging_defaults`（`data/logs == ''` 环境断言，与本 change 无关、不引用下载路径）——符合「无新增失败」判据；changed-vs-main ruff 全绿
- [x] 6.2 模块边界自检：`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过；确认改动未引入 `fleetent.platform.*` 反向 import
- [x] 6.3 回归确认（人读）：图片 200 直出、xlsx/csv 200 直出、size 上限、失败降级、三路径共用等既有行为均未变；仅新增「跟随 302」与「HTML 兜底」两条行为
