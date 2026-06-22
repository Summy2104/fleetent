## ADDED Requirements

### Requirement: node service key 持久化失败必须暴露

登记 node 时，系统除哈希存储 service key（用于入站 node→platform 鉴权）外，还 SHALL 持久化
该 key 的可解密副本（经 secret store 加密），供 platform→node 出站鉴权（拨 node forwarder）使用。
该持久化 MUST NOT 被静默吞掉：当持久化失败（如缺 master key、secret 后端异常）时，系统 SHALL
log 明确错误并使登记**整体失败**，MUST NOT 返回一次性明文 key、报告"登记成功"却留下无法被
platform 取用的 node。

#### Scenario: 持久化失败则登记失败而非假成功

- **WHEN** 登记 node 时 service key 的可解密持久化失败（例如 master key 缺失）
- **THEN** 系统 log 明确错误并使该次登记失败（抛出可诊断错误）
- **AND** 不返回一次性明文 key、不在 `nodes` 表留下一个 platform 永远拨不通的 node

#### Scenario: 持久化成功则 platform 可取用 key

- **WHEN** 登记成功且 master key 就绪
- **THEN** platform 后续可解密取回该 node service key，用于向其 forwarder 出站鉴权
