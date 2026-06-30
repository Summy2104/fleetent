## Why

KB 缺口审计的**头号硬阻断**:平台侧文档 import 退役后,把一批本地/手头文档灌进 KB **没有任何可用入口**——只剩 Drive/Confluence connector(需云凭据 + 改 yaml + 重启 + 等 sweep)。而处理本地目录的执行层(`LocalDirectoryDataSource` + `sync_local_directory` + worker `sync_directory` job)**已齐全且测试通过,只是没有 producer 入队 = 孤儿代码**。

本 change 补一个**命令式 ingest 动作**(不是新数据源类型,不进 connector 框架):一条 KB 服务侧 CLI,把本地目录/文件推进 KB。复活孤儿执行层,解最硬阻断,且**纯 KB 服务侧、不依赖 platform**(与 KB 独立部署线一致)。

> 范围克制:HTTP ingest 端点 + 管理 UI 是**另一套**(放 KB 服务侧、admin UI 跨服务调,涉及寻址/鉴权),单独 change;声明式"本地目录 source type"(进 SourceType、被 sweep 定时同步)也另议。本 change 只做 CLI 一次性推送。

## What Changes

- **新 CLI** `fleetent kb-ingest --config <kb-service.yaml> --kb <kb_id> <path> [--wait]`(顶层,与 `kb-worker`/`kb-serve` 同级):
  - 从 `--config` 读 tenant_id + 队列路径(复用 `load_kb_service_config`),**纯 KB 服务侧、零 platform 依赖**。
  - `<path>` 支持**目录(递归)或单文件**;格式覆盖 `LocalDirectoryDataSource` 现有集合(txt/md/html/pdf/docx/pptx/xlsx)。
  - 校验 KB 存在(`_require_active_kb`),不存在 → 清晰报错(提示经平台 `POST /admin/kb` 先建 KB;`--create-kb` 便利项留待后议)。
  - `enqueue_job(job_type="sync_directory", tenant_id, kb_id, connector_ref={"path": <abs>}, database_url=<queue>)` 入队;`--wait` 阻塞轮询该 job 状态、打印 `scanned/ingested/skipped/failed`,并在超时未被消费时提示"kb-worker 是否在运行"。
- **复活 `sync_directory` 执行分支**(`worker.py:207`)去孤儿状态:它本就是 worker 唯一消费者模型的一部分,本 change 只是补上 producer——**ingest 仍由 kb-worker 单写者执行**(CLI 只入队,不在进程内直写 kb.db)。
- **`LocalDirectoryDataSource` 支持单文件**:`root_path` 为文件时退化为只扫该文件(现在仅接受目录,line 27 硬性)。
- **example 连接器默认 `enabled: false`**:`kb-service.yaml.example` 的 `drive-shared`/`confluence-shared` 现为 `enabled: true` + 占位凭据 → `make kb-worker` 一起来 sweep 就去连真 Google 然后失败。改默认关,开箱不踩雷。

不做:HTTP ingest 端点、管理 UI、声明式 local source type、`import_document` 路径(text-only,格式窄,本 change 统一走 `sync_directory`/LocalDirectoryDataSource 的宽格式路径)、embedding 两端一致性(由配套 change B 解)。

## Capabilities

### Modified Capabilities
- `kb-standalone-ingest`:新增**手动本地 ingest 命令**(CLI 入队 `sync_directory` job;worker 仍唯一消费者;幂等;目录+单文件);example 连接器默认禁用。

## Impact

- **owning area**:`knowledge_base/`(新 CLI 入口 + `worker.py` sync_directory 去孤儿 + `connectors/local.py` 支持单文件)、`__main__.py`(顶层 `kb-ingest` 分发)、`kb-service.yaml.example`。**不碰 platform、不碰 connector SourceType 框架、不碰检索**。
- **public surface**:新增 CLI `fleetent kb-ingest`;无 HTTP/API 变更。
- **owned tables**:无新增;写既有 `kb_ingest_queue.db`(入队)+ 由 worker 写 `kb.db`。
- **config namespace**:复用 `kb-service.yaml`(`--config`);example 默认值改 `enabled: false`。
- **cross-module 依赖**:不新增;解耦基线不变(纯 KB 服务侧,无 platform)。
- **migration / shim**:无 schema 迁移。
- **依赖关系**:A 只解决"灌进去";端到端检索还需配套 change B(embedding 两端一致)。A 可独立先落。
- **测试**:新增 CLI 入队 + sync_directory 复活 + 单文件 ingest 单测/集成测;`make test-pr` + `make test-integration-ci` 全绿。
