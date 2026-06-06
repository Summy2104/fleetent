## ADDED Requirements

### Requirement: sandbox.client 记录容器生命周期与 Docker 探测

`integrations/sandbox/client.py` SHALL 使用 `get_logger("sandbox.client")` 记录沙箱容器操作。

#### Scenario: Docker 探测失败记录 warn
- **WHEN** Docker 守护进程探测失败
- **THEN** 以 `warn` 级别记录，fields 包含 `error`

#### Scenario: Docker 探测返回非零记录 warn
- **WHEN** Docker 探测返回非零退出码
- **THEN** 以 `warn` 级别记录，fields 包含 `returncode`

#### Scenario: 容器创建成功记录 info
- **WHEN** 沙箱容器创建成功
- **THEN** 以 `info` 级别记录，fields 包含 `name`、`container_id`（截取前 12 字符）

#### Scenario: 容器销毁成功记录 info
- **WHEN** 沙箱容器销毁完成
- **THEN** 以 `info` 级别记录，fields 包含 `container_id`（截取前 12 字符）

#### Scenario: 容器列举失败记录 warn
- **WHEN** Docker 列举容器命令失败
- **THEN** 以 `warn` 级别记录，fields 包含 `prefix`、`error`

#### Scenario: 代码执行完成记录 debug
- **WHEN** 沙箱代码执行完成
- **THEN** 以 `debug` 级别记录，fields 包含 `exit_code`、`duration_ms`

### Requirement: sandbox.config 记录配置加载与验证异常

`integrations/sandbox/config.py` SHALL 使用 `get_logger("sandbox.config")` 记录配置解析异常与加载结果。

#### Scenario: 配置加载成功记录 info
- **WHEN** agent sandbox 配置成功加载
- **THEN** 以 `info` 级别记录，fields 包含 `agent`、`cpu_limit`、`mem_limit_mb`

#### Scenario: scope 无效记录 warn
- **WHEN** sandbox scope 字段值非法，fallback 到默认值
- **THEN** 以 `warn` 级别记录，fields 包含 `value`、`falling_back`

#### Scenario: YAML 解析失败记录 warn
- **WHEN** settings YAML 文件解析失败
- **THEN** 以 `warn` 级别记录，fields 包含 `path`、`error`

#### Scenario: 资源字段无效记录 warn
- **WHEN** 资源配置字段（cpu、mem 等）值非法，fallback 到默认
- **THEN** 以 `warn` 级别记录，fields 包含 `field`、`value`、`falling_back`

### Requirement: sandbox.cleanup 记录清理操作结果

`integrations/sandbox/cleanup.py` SHALL 使用 `get_logger("sandbox.cleanup")` 记录孤儿容器清理。

#### Scenario: 跳过非前缀容器记录 warn
- **WHEN** 清理过程发现非预期前缀容器
- **THEN** 以 `warn` 级别记录，fields 包含 `name`

#### Scenario: 清理完成记录 info
- **WHEN** 孤儿容器清理完成
- **THEN** 以 `info` 级别记录，fields 包含 `count`、`destroyed`

### Requirement: sandbox.enablement 记录模式解析异常

`integrations/sandbox/enablement.py` SHALL 使用 `get_logger("sandbox.enablement")` 记录启用模式解析异常。

#### Scenario: 模式值无效记录 warn
- **WHEN** sandbox mode 配置值无法解析，fallback 到默认
- **THEN** 以 `warn` 级别记录，fields 包含 `value`、`falling_back_to`

#### Scenario: YAML 解析失败记录 warn
- **WHEN** settings YAML 文件解析失败
- **THEN** 以 `warn` 级别记录，fields 包含 `path`、`error`
