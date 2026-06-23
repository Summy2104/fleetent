## 1. 探针：先验四个可行性点（先于任何断言，不写死假设）

- [x] 1.1 **探针 · agent_state.db 路径**：用既有 `managed_stack` 起栈，定位 placed agent 的 `im_outbound_queue`（agent_state.db）真实物理路径（`<home>/agents/<name>/...` 还是经 tenant_router 落 `<data_dir>/<tenant>/<agent_id>/`）。记录跨进程只读该库的稳定路径。
- [x] 1.2 **探针 · `/im/route` 达点 + Principal 头**：确认 `/im/route` 是经 platform forwarder 转发还是直达 agent 进程端口；确认 `X-Fleetent-Principal` 头如何构造（`decode_ingress_principal` 能解的格式）；确认是否需要 `/nodes/{id}/identity/resolve` 在场。记录最小可达姿势。
- [x] 1.3 **探针 · 无 connector 下 fan-out 可观测点**：往 `im_outbound_queue` 注一条 directed user_id 行，观察 node drain 行为——是否触发 `/nodes/{id}/identity/addresses` 反查、队列行 status 从 pending 推进到 sent/failed、平台侧/ node 侧哪个可观测点最稳。记录断言锚点。
- [x] 1.4 **探针 · `im_users` 绑定建法**：确认在平台侧为某 user_id 建好至少一条 IM 绑定的入口（`im_gateway_management.resolve_or_provision` / 经 `/nodes/{id}/identity/resolve` 或 admin API），使 `resolve_user_addresses` 反查能命中。记录建绑定姿势。
- [x] 1.5 把 1.1–1.4 探针结论沉淀进 `tests/e2e/_im_helpers.py`（本 change 独占文件）的注释/常量与 helper 雏形：构造 Principal 头、注 directed 队列行、读 `im_outbound_queue`、建 IM 绑定。

## 2. E2E-1：IM 入站经 `/im/route` 同步回复

- [x] 2.1 **测试（红）**：在新 e2e 文件用 `managed_stack` + `_im_helpers`，向 placed agent `/im/route` 发一条 `ImRouteRequest`（带合法 Principal 头），断言 200 且 `replies` 非空、内容含确定性 stub 标记。先跑见红（`uv run pytest tests/e2e/<file>::<test> -x -q`）。
- [x] 2.2 **绿**：补齐 helper / 请求姿势让它过。跑同一命令见绿。

## 3. E2E-2：审批 DM 入队 + `approve <id>` 恢复 run

- [x] 3.1 **测试（红）· 审批通知入队**：触发一次高危工具进入审批挂起，`wait_for_condition` 轮询 agent 侧 `im_outbound_queue` 出现 `status=pending` 审批通知行，断言其 platform/address/payload 形状。先跑见红。
- [x] 3.2 **绿**：让 3.1 过。
- [x] 3.3 **测试（红）· `approve <id>` 恢复**：取 3.1 的 approval_id，经 `/im/route` 发 `approve <id>`，断言审批被解析为 approved 且挂起 run 恢复（断言点按探针 1.2/1.3 结论选最稳的：回复 / 审批状态 / 队列状态）。先跑见红。
- [x] 3.4 **绿**：让 3.3 过。

## 4. E2E-3：`notify_user` fan-out 投递原语

- [x] 4.1 **测试（红）**：先用 helper 在平台侧为某 user_id 建好 IM 绑定（探针 1.4），再向 agent 侧 `im_outbound_queue` 注一条 directed 行（`platform=directed`、`address_json={"target_type":"user_id","user_id":...}`）；`wait_for_condition` 断言：node drain 拾取该行 → 发生对 `/nodes/{node_id}/identity/addresses` 的反查（按探针 1.3 的可观测点）→ 队列行 status 从 pending 推进。同时断言注入行各列形状符合 directed-reach 契约。先跑见红。
- [x] 4.2 **绿**：让 4.1 过。注意：**只断言入队形状 + 反查发生 + status 推进，不断言真渠道送达**（无真 connector）。

## 5. 收尾 + lane + 边界自检

- [x] 5.1 `make test-e2e` 跑这批（含 `_im_helpers` + E2E-1/2/3）；确认它们**不在** `make test-pr` 里（slow lane）。
- [x] 5.2 `make test-pr` 仍全绿（本 change 纯 test 侧、不碰 src，对照 main 基线无新增失败）。
- [x] 5.3 **边界自检**：仅新增 `tests/e2e/_im_helpers.py` + 本 change 的 e2e test 文件；**未改** `tests/e2e/conftest.py::managed_stack` / conftest 核心、**未改任何 src**、**未碰 reflection**（A4b 归 D5）。如确需改核心 fixture 或 src，停下说明（违反并行纪律）。
