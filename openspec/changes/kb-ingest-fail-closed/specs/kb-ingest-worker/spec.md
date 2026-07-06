# kb-ingest-worker — Delta

## ADDED Requirements

### Requirement: sync job 失败可观测与终态语义

sync 类 job（`sync_directory` / `connector_sync`，覆盖 local / google_drive / confluence 全部源）执行中，单文件失败 SHALL NOT 中断整批（既有语义保留），但每个失败 SHALL 被记录：结构化日志（含 source path 与异常栈）+ 错误文本经 `structured_logging.redact_text` 脱敏后收入 sync summary（带上限截断，防超长）。MUST NOT 存在无日志、无错误文本的裸吞异常。

job 终态 SHALL 反映实际结果：**完败**（`failed > 0 ∧ ingested == 0 ∧ scanned > 0`，典型 = embedding 服务不可用）SHALL 落 `failed` 终态且 `last_error` 携带错误摘要；**部分失败**（`0 < failed` 且有成功导入）SHALL 落 `done` 但 `last_error` 携带失败明细摘要（done + last_error 非空 = 部分失败语义）。二者均经既有 kb-serve `GET /status`（近期 job 含 status / last_error）对运维可见。

#### Scenario: embedding 不可用时完败落 failed（dogfooding 复现场景）
- **WHEN** embedding 服务不可达或模型不存在，此时上传文档触发 `sync_directory` job
- **THEN** job 终态为 `failed`，`last_error` 含脱敏后的 embedding 错误摘要
- **AND** 文档不出现在该 KB 的文档列表，库中无 chunk / FTS / 向量残留
- **AND** `GET /status` 能读到该 job 的 failed 状态与错误

#### Scenario: 部分失败 done 但错误可见
- **WHEN** 一批多个文件同步，其中少数文件失败（如个别文件解析异常）、其余成功导入
- **THEN** job 终态为 `done`，summary 的 failed 计数与错误明细如实反映
- **AND** `last_error` 携带失败文件的脱敏错误摘要，`GET /status` 可见

#### Scenario: 逐文件失败必留痕
- **WHEN** 任一文件在同步中抛出异常
- **THEN** 出现一条含 source path 的结构化异常日志
- **AND** summary 的 errors 收集含该文件的脱敏错误文本（超出上限时截断并计数）

#### Scenario: 错误文本不泄密
- **WHEN** connector 异常文本内嵌凭据（如带 token 的 URL / 鉴权失败详情）
- **THEN** 进入 summary / `last_error` / 日志的文本已经 `redact_text` 脱敏，不含明文凭据
