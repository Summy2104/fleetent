# Tasks

> 每个实现 task 严格 TDD：先写测试跑最窄命令**见红** → 写实现**见绿**。
> 测试任务排在对应实现任务之前。基线对照 main（门禁判据＝无新增失败）。
> 最窄命令：`uv run pytest tests/unit/test_mcp_exchange_injection.py -x -q`

## 1. 前置核实

- [ ] 1.1 复读 `_translate_workspace_arg`（client.py，#280 现状）与 `_translate_workspace_args` 递归；确认 client.py 已 `import os`；确认 chokepoint 已对 stdio+scope_key 调用翻译（#280/#282）

## 2. 相对路径翻译（TDD：红 → 绿）

- [ ] 2.1 **测试先行**：`tests/unit/test_mcp_exchange_injection.py` 加：
  - `test_translate_relative_workspace_file`：tmp 下建 `generated/x.png`，断言 `_translate_workspace_arg("generated/x.png", tmp)` == `str(tmp/generated/x.png)`
  - `test_translate_relative_nonexistent_unchanged`：`nope.png`（不存在）原样
  - `test_translate_relative_plaintext_unchanged`：`可爱小狗`、`"Hi,\n\n正文"` 原样
  - `test_translate_relative_escape_blocked`：`../outside.png` 不翻译（即便构造 tmp 外真实文件）
  - `test_translate_args_relative_in_list`：`_translate_workspace_args({"attachments":["generated/x.png"],"subject":"可爱小狗"}, tmp)` → 附件翻译、subject 不变
  跑最窄命令 **见红**（相对路径当前 no-op）
- [ ] 2.2 **实现**：`_translate_workspace_arg` 增补相对路径分支（`not startswith('/')` + 无换行 + normpath containment + `os.path.isfile`）。跑 2.1 **见绿**

## 3. 回归 + lint

- [ ] 3.1 整文件回归：`uv run pytest tests/unit/test_mcp_exchange_injection.py tests/unit/test_mcp_workspace_arg_translation.py -q` 全绿（含 #280 绝对路径用例不回归）
- [ ] 3.2 `uv run ruff check` + `ruff format --check` 受影响文件通过

## 4. spec 同步

- [ ] 4.1 确认 `specs/file-exchange/spec.md` 既有翻译要求 MODIFIED 与实现一致（绝对 + 相对真实文件均翻译；非真实文件/逃逸/http 不动），含相对路径 scenario

## 5. 收尾验证

- [ ] 5.1 `make test-pr`：全绿或仅预先存在且无关失败（判据＝无新增失败）
- [ ] 5.2 模块边界自检通过；无 `fleetent.platform.*` 反向 import
- [ ] 5.3 回归确认（人读）：`/workspace` 绝对翻译、http、非 workspace 串均未变；仅新增「相对真实文件→宿主路径」
