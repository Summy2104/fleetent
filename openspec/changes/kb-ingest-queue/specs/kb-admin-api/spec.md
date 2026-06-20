## MODIFIED Requirements

### Requirement: Connector sync 经队列异步执行

`kb_admin_api` 的 connector sync 与文档导入端点 SHALL 经 `kb-ingest-queue` 入队执行,SHALL NOT 在控制面请求线程内同步 `asyncio.run` 跑完整 ingest(parse/chunk/embed)。dry-run(仅出 plan、不写)可保持同步;execute(真实写)SHALL 入队。admin sync 端点 SHALL 提供"入队 + 等该 job 完成"语义,使运维拿到结果。

#### Scenario: execute sync 入队

- **WHEN** admin 调用 connector sync(execute,非 dry-run)
- **THEN** 端点入队 ingest job 并返回 job id(或入队+等完成的结果),不在请求线程内跑完整 ingest

#### Scenario: dry-run 仍同步出 plan

- **WHEN** admin 调用 connector sync `--dry-run`
- **THEN** 端点同步返回 plan summary(不写、不入 execute 队列)

#### Scenario: 输出仍脱敏

- **WHEN** 端点返回 sync / 入队结果
- **THEN** 输出不含 token、secret、credential payload 或完整文档正文
