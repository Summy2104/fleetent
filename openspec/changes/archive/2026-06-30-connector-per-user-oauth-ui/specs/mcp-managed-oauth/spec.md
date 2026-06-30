## ADDED Requirements

### Requirement: managed 运行时授权链接经 directed-reach DM 投递

managed（node 托管）运行时下，当 per-user OAuth（authorization_code）授权链接需要送达用户本人时，授权链接投递接缝 SHALL 在无 live IM connector 可用时，经 node-managed 的 directed-reach 出站通道（按内部 user_id 入队 DM 意图）投递，与 per-user api-key 凭证表单链接的投递路径对称。该投递 MUST NOT 因 managed 下无 live connector 而静默丢弃（即不得只返回未投递、令用户收不到链接）。agent 运行时 MUST NOT 因此 import platform、MUST NOT 直连 platform——投递经既有出站接缝完成。投递失败 SHALL 返回未投递信号但不抛异常、不中断工具调用降级链。

#### Scenario: node-managed 运行时无 live connector 时经 directed-reach 投递

- **WHEN** managed 运行时下某 per-user OAuth MCP 服务被调用且该用户三元组无有效 token，需投递授权链接，而当前无 live IM connector
- **THEN** 授权链接投递接缝经 node-managed directed-reach 通道（按 user_id 入队 DM 意图）投递该链接给用户本人，返回已投递

#### Scenario: 与 per-user api-key 凭证链接投递对称

- **WHEN** 对比授权链接投递接缝与 per-user api-key 凭证表单链接投递接缝在 managed 运行时的行为
- **THEN** 二者采用同一形态的 node-managed fallback（`is_node_managed_runtime()` → 按 user_id 入队 directed-reach DM），无一者在 managed 下缺失 fallback

#### Scenario: 投递不可达时不抛异常

- **WHEN** 既无 live connector、也非 node-managed 运行时（如 dev `agent run`）
- **THEN** 投递接缝返回未投递信号且不抛异常，工具调用的「需授权」降级结果照常返回
