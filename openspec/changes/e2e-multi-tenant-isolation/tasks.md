## 1. 定位真实落盘点（探针，先于断言）

- [ ] 1.1 **探针**：用既有 `managed_stack` 起单 tenant 单 agent，经真实写入路径（KB ingest 或对话产生记忆）落一条数据，然后在文件系统/`tenant_router` 解析下定位该数据的真实物理路径（`<data_dir>/<tenant>/...` 还是 agent home）。记录结论，据此确定隔离断言观测点。**不写死假设**。

## 2. `managed_stack_two_tenants` fixture

- [ ] 2.1 **测试（红）**：在 `tests/e2e/_tenant_helpers.py` 写 `managed_stack_two_tenants` fixture——起一个 node、注册两个不同 `tenant_id` 的 agent（各指向 LLM stub）、各 pin 到该 node、都健康。先写一个"两 tenant agent 均就绪 + 两 tenant 数据根目录独立存在"的最小测试。先跑见红。
- [ ] 2.2 **实现（绿）**：实现该 fixture（复用 `managed_stack` 的起栈步骤，**不改核心 fixture**）。跑见绿。

## 3. E2E-1 跨租户查询零串数据

- [ ] 3.1 **测试（红）**：用 `managed_stack_two_tenants`：向 tenant-a 写入一条可检索数据 → 经 tenant-b 的检索/读取路径查同一内容 → 断言 tenant-b 零命中；反向再验一次。先跑见红。
- [ ] 3.2 **绿**：让它过（若红，定位是路由/隔离哪段——这正是 e2e 要抓的隔离回归）。

## 4. E2E-2 文件级物理隔离

- [ ] 4.1 **测试（红）**：用 `managed_stack_two_tenants`：两 tenant 各产生持久化数据后，断言文件系统上存在分属两 tenant 的独立 SQLite 文件，且任一 tenant 的库文件不落在另一 tenant 目录下。先跑见红。
- [ ] 4.2 **绿**：让它过。

## 5. 收尾 + lane

- [ ] 5.1 `make test-e2e` 跑这批（含新 fixture + 2 测试）；确认**不在** `make test-pr` 里。
- [ ] 5.2 `make test-pr` 仍全绿（本 change 纯 test 侧、不碰 src，对照 main 基线无新增失败）。
- [ ] 5.3 边界自检：仅新增 `tests/e2e/_tenant_helpers.py` + 本 change 的 test 文件；**未改** `tests/e2e/conftest.py::managed_stack`、未改任何 src。如确需改核心 fixture 或 src，停下说明（违反并行纪律）。
