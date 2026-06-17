# Tasks

> 每个实现 task 严格 TDD：先写测试跑最窄命令**见红** → 写实现**见绿** → 可选 refactor。
> 测试任务排在对应实现任务之前。基线对照 main（门禁判据＝无新增失败）。

## 1. 前置核实（不改产线代码，定 scope）

- [x] 1.1 复读 `src/fleetent/tools/builtin_tools.py` 的 `send_im_message`（~829-913）与 `send_file`（~968-1034），确认投递目标解析点与 `_record_delivery` 调用结构
- [x] 1.2 核实 `fleetent.outbound.send_file_to` 与 `send_to` 的签名是否已支持 `target_type` / `thread` 关键字（`send_file` 已这样调用）：`grep -n "def send_file_to\|def send_to" src/fleetent/outbound*.py src/fleetent/outbound/*.py 2>/dev/null` —— 若文件投递缺 `thread`/`target_type`，记为 task 4 的最小补齐项；若已支持，task 4 仅透传
- [x] 1.3 核实 `conversation_address` 的可用字段（`chat_type` / `chat_id` / `thread_id` / `target_type`）来源（`im_gateway/slack.py` 的 `ConversationAddress` 构造），确认以 `chat_type == "channel"` 判频道、不依赖 `address.target_type`

## 2. 纯函数决策助手（TDD：红 → 绿）

- [x] 2.1 **测试先行**：新增 `tests/unit/test_send_im_self_dm_routing.py`，覆盖 `_resolve_self_dm_redirect(target, target_type, address, sender_id)` 全分支（`address` 用 `SimpleNamespace` 构造，无 DB/HTTP）：
  - 频道会话 + `target==sender` + `target_type=="user"` → 返回 `{"recipient": chat_id, "target_type": "channel", "thread": thread_id}`
  - `target != sender`（他人）→ `None`
  - `target_type == "channel"` → `None`
  - DM 会话（`chat_type != "channel"`）→ `None`
  - `address is None` → `None`
  - `target`/`sender_id` 含首尾空白仍能正确匹配；任一为空 → `None`
  运行 `uv run pytest tests/unit/test_send_im_self_dm_routing.py -x -q` **见红**（函数未实现/导入失败）
- [x] 2.2 **实现**：在 `builtin_tools.py` 新增模块级纯函数 `_resolve_self_dm_redirect(...)`（只读入参、无 I/O，完整类型注解 + Google docstring）。再跑 2.1 命令 **见绿**

## 3. 接线进 send_im_message（TDD：红 → 绿）

- [x] 3.1 **测试先行**：在 `tests/unit/test_send_im_self_dm_routing.py`（或同层新文件）补一条覆盖 `send_im_message` 投递路由的用例——mock `fleetent.outbound.send_to` / `send_file_to`（`unittest.mock`），构造"频道会话 + 发起人 user 投递"的 `ToolContext`（fake `session_context`/`conversation_address`/`outbound_connectors`），断言：
  - `send_to` 收到的 `target == 频道 chat_id`、`target_type == "channel"`
  - `send_file_to` 收到 `target == 频道 chat_id` 且带 `target_type="channel"` + `thread=<thread_id>`
  - 对照用例：`target=他人 user` 时 `send_to`/`send_file_to` 仍收到原 `target`（不改写）
  运行最窄命令 **见红**
- [x] 3.2 **实现**：在 `send_im_message` 投递前调用 `_resolve_self_dm_redirect` 求 `eff_recipient/eff_target_type/eff_thread`（命中取覆盖、未命中取原值），并把 `eff_target_type`/`eff_thread` **一并透传**给文本分支（`send_to`）与文件分支（`send_file_to`）。不改审批判级逻辑、不改 `_record_delivery` 结构。跑 3.1 命令 **见绿**

## 4. outbound 透传核实/最小补齐（依据 1.2）

- [x] 4.1 若 1.2 显示 `send_file_to` 已支持 `target_type`/`thread`：本步仅确认透传无误（无代码改动），跳到 task 5；否则在 outbound 侧最小补齐这两个关键字（不改既有调用方默认行为），并补/跑相应最窄测试见绿

## 5. docstring 收紧（②）

- [x] 5.1 编辑 `send_im_message` docstring：明确"用于**主动给其他用户 / 其他频道**发消息；回复当前对话请用 `send_file` 或直接文本回复"。仅文档措辞，不改签名/参数。运行 `uv run ruff check src/fleetent/tools/builtin_tools.py` 通过

## 6. integration 端到端（条件：可在不接真实 Slack 下用 fake connector 验证）

- [x] 6.1 新增 integration 用例（`tests/integration/`）：以 fake outbound connector 走"频道会话 → agent 调 `send_im_message(target=发起人, user, files=[...])`"，断言文本+文件落**频道线程**（connector 收到 channel target + thread），且 footer/receipt 的 target 为频道；并保留一条"他人外发仍走 DM 且仍 medium"对照。运行 `uv run pytest tests/integration/<new_file> -q` 见绿（若现有 outbound fake 设施不足以黑盒断言投递面，则在本步落地最小 fake，不接真实网络）

## 7. 收尾验证

- [x] 7.1 `make test-pr`：3194 passed，仅 1 个**预先存在且无关**的失败 `test_config.py::test_observability_logging_defaults`（`data/logs == ''`，在 clean main 上同样失败，与本 change 无关）——符合"无新增失败"门禁判据；层边界 + changed-vs-main ruff 全绿
- [x] 7.2 受影响层 integration（`test_send_im_files` + `test_send_im_channel_self_dm` + `test_delivery_ledger`）9 passed，无新增失败
- [x] 7.3 模块边界自检：`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过；确认改动未引入 `fleetent.platform.*` 反向 import
- [x] 7.4 回归确认（人读）：他人外发（`target != 发起人`）行为与审批级未变；纯 DM 会话未变；仅"频道→发起人本人 user-DM"投递面从 DM 改为频道线程
