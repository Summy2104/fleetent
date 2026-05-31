## ADDED Requirements

### Requirement: 敏感名称环境变量不传入容器

环境变量过滤规则 SHALL 将名称（大小写不敏感）包含 `TOKEN`、`KEY` 或 `SECRET` 子串的变量判定为敏感。被判定为敏感的变量 MUST NOT 传入沙箱容器。

#### Scenario: 含敏感子串的变量被识别
- **WHEN** 判定名称为 `API_TOKEN`、`db_secret` 或 `MyKey`
- **THEN** 均被判定为敏感

#### Scenario: 无害变量不被误判
- **WHEN** 判定名称为 `PATH`、`HOME`、`LANG`
- **THEN** 均不被判定为敏感

### Requirement: 三层来源统一过滤后注入

沙箱环境变量 SHALL 由三层来源合并：宿主机进程环境、agent 配置注入的变量、运行时显式传入的变量。合并后的全部变量 MUST 统一应用同一名称过滤规则，敏感变量一律剔除；通过过滤的变量 SHALL 经 `docker run` 的环境注入参数传入容器。宿主机进程环境默认 MUST NOT 整体透传。

#### Scenario: 任一来源的敏感变量都被剔除
- **WHEN** agent 配置或运行时来源中显式写入名称含 `KEY`/`TOKEN`/`SECRET` 的变量
- **THEN** 该变量不出现在传入容器的环境中

#### Scenario: 通过过滤的变量被注入
- **WHEN** 注入一个名称不敏感的变量（如 `DATA_DIR`）
- **THEN** 该变量经环境注入参数进入容器，可在容器内读取

#### Scenario: 默认不透传宿主环境
- **WHEN** 未显式选择透传宿主机进程环境
- **THEN** 宿主机环境变量不进入容器（保持干净环境）

### Requirement: 宿主机敏感变量绝不泄漏进沙箱

无论经哪一层来源、哪条路径，宿主机的敏感变量（如 `ANTHROPIC_API_KEY`）MUST NOT 进入沙箱容器。即使调用方误将敏感变量传入容器创建接口，注入前 MUST 再次过滤剔除。

#### Scenario: 显式透传宿主环境仍剔除敏感变量
- **WHEN** 显式选择透传宿主机进程环境，其中含 `ANTHROPIC_API_KEY`
- **THEN** 传入容器的环境中不含 `ANTHROPIC_API_KEY`

#### Scenario: 容器创建接口防御性二次过滤
- **WHEN** 调用方误将含 `KEY` 子串的变量传给容器创建接口
- **THEN** 容器创建命令中不出现该变量

### Requirement: 沙箱客户端按需注入已过滤环境变量

沙箱客户端创建容器时 SHALL 支持接收一组环境变量并经 `docker run` 注入；未提供环境变量时 MUST 与现状等价（不注入任何变量，容器为干净环境）。注入前 MUST 对变量名再次过滤，敏感名不进入容器。

> 归属说明：本需求是 Docker 后端新增能力，落在本 change 的新 capability `sandbox-secret-injection` 下以 ADDED 表达。既有 `openspec/specs/sandbox-client/spec.md` 主 spec 仍为 microsandbox 历史版本，属既有技术债，不在本 change 范围。

#### Scenario: 提供环境变量则注入
- **WHEN** 创建容器时提供一组非敏感环境变量
- **THEN** 这些变量经环境注入参数出现在创建命令中

#### Scenario: 不提供则干净环境
- **WHEN** 创建容器时不提供环境变量
- **THEN** 创建命令不含任何环境注入参数，与现状一致
