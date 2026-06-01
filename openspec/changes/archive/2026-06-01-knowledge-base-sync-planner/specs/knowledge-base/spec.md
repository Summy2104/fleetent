## ADDED Requirements

### Requirement: Knowledge-base sync planner public API
系统 SHALL 提供 knowledge-base sync planner public API，用于在执行 source sync 前生成确定性的同步计划。

#### Scenario: Sync planner API is importable
- **WHEN** 调用方从 `fleetent.intelligence.knowledge_base` 导入 `SyncAction`、`SyncPlan`、`SyncPlanItem`、sync summary dataclasses、`plan_local_directory_sync` 和 `execute_sync_plan`
- **THEN** 导入成功

#### Scenario: Empty source plan
- **WHEN** local source 目录没有支持或不支持的文件，且没有历史 source state
- **THEN** planner 返回空 plan items
- **AND** summary 中 scanned、planned、unsupported 均为 0

### Requirement: Sync plan separates planning from execution
sync planner SHALL 在写入 KB documents、chunks、vector index 或 source state 前产出计划。

#### Scenario: Planning does not mutate knowledge base
- **WHEN** 调用 `plan_local_directory_sync()`
- **THEN** 系统可以列举、读取和 hash source documents
- **AND** 不调用 `ingest_parsed()`、`delete()` 或 vector_store mutation
- **AND** 不写入 `knowledge_source_states`

#### Scenario: Execution applies a plan
- **WHEN** 调用 `execute_sync_plan()`
- **THEN** 系统只按 plan items 执行 ingest、reingest、delete 或 skip

### Requirement: Local sync action planning
系统 SHALL 为 local directory source documents 生成 new、changed、unchanged 和 unsupported actions。

#### Scenario: New file is planned for ingest
- **WHEN** local source 包含支持格式文件，且 `knowledge_source_states` 中没有该 source path
- **THEN** planner 为该文件生成 `ingest_new` plan item

#### Scenario: Changed file is planned for reingest
- **WHEN** local source 文件的 mtime 或 content hash 与 source state 不一致
- **THEN** planner 为该文件生成 `reingest_changed` plan item

#### Scenario: Unchanged file is planned for skip
- **WHEN** local source 文件的 path、mtime 和 content hash 均与 source state 一致
- **THEN** planner 为该文件生成 `skip_unchanged` plan item

#### Scenario: Unsupported files are counted
- **WHEN** local source 包含不支持后缀
- **THEN** planner summary 记录 unsupported 数量
- **AND** unsupported 文件不会生成 ingest 或 reingest item

### Requirement: Missing-source delete planning
系统 SHALL 检测之前同步过但当前 source listing 中缺失的 local source path，并计划删除对应 KB document。

#### Scenario: Missing source file is planned for delete
- **WHEN** `knowledge_source_states` 中存在某 source path
- **AND** 当前 local source listing 不再包含该 path
- **THEN** planner 生成 `delete_missing` plan item

#### Scenario: Delete plan item includes target document
- **WHEN** planner 生成 `delete_missing` item
- **THEN** item 包含 source_id、tenant_id、kb_id、source_path 和 document_id

### Requirement: Sync plan execution
系统 SHALL 幂等执行 sync plan items，并在单个 item 失败时继续处理其他 items。

#### Scenario: Execute ingest new
- **WHEN** executor 处理 `ingest_new` item
- **THEN** 系统解析 source content，调用 `ingest_parsed()`
- **AND** ingest 成功后写入 `knowledge_source_states`

#### Scenario: Execute reingest changed
- **WHEN** executor 处理 `reingest_changed` item
- **THEN** 系统删除旧 document
- **AND** 解析并 ingest 新 document
- **AND** 成功后更新 `knowledge_source_states`

#### Scenario: Execute delete missing
- **WHEN** executor 处理 `delete_missing` item
- **THEN** 系统调用 `delete(document_id)`
- **AND** 删除对应 `knowledge_source_states` 记录

#### Scenario: Execute skip unchanged
- **WHEN** executor 处理 `skip_unchanged` item
- **THEN** 系统不调用 parser、`ingest_parsed()` 或 `delete()`
- **AND** summary 记录 unchanged / skipped

#### Scenario: Per item failure isolation
- **WHEN** 某个 plan item 执行失败
- **THEN** executor 记录 failed count
- **AND** 继续执行后续 plan items

### Requirement: Local sync delegates to planner
`sync_local_directory()` SHALL 通过 sync planner 和 executor 完成同步，而不是直接边扫描边写入 KB。

#### Scenario: Local sync summary matches plan execution
- **WHEN** 调用 `sync_local_directory()`
- **THEN** 返回 summary 反映 planner 和 executor 的 scanned、ingested、skipped、failed、unsupported、unchanged 和 deleted 计数

#### Scenario: Repeated sync remains idempotent
- **WHEN** 对同一 local source 连续调用两次 `sync_local_directory()`
- **THEN** 第二次 sync 对未变化文件返回 unchanged / skipped
- **AND** 不重复创建 KB documents 或 chunks

#### Scenario: Removed local file is deleted from KB
- **WHEN** 某文件已同步到 KB
- **AND** 该文件随后从 local source 删除
- **AND** 再次调用 `sync_local_directory()`
- **THEN** 对应 KB document 被删除
- **AND** search 不再返回该 document 的 chunks

### Requirement: Sync planner excludes advanced connector runtime
sync planner SHALL NOT introduce scheduler、background worker、remote connector、sync run persistence 或 connector-specific credential lifecycle。

#### Scenario: No scheduler or worker dependency
- **WHEN** sync planner change 完成
- **THEN** 系统不要求新增 scheduler、queue、worker 或动态 job runtime

#### Scenario: No remote connector behavior
- **WHEN** sync planner change 完成
- **THEN** 系统不包含 Confluence、Google Drive 或其他 remote connector 实现
