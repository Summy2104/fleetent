# sandbox-secret-injection Specification

## Purpose
TBD - created by archiving change sandbox-secret-injection. Update Purpose after archive.
## Requirements
### Requirement: 敏感名称环境变量不传入容器

环境变量过滤规则 SHALL 将名称（大小写不敏感）包含 `TOKEN`、`KEY`、`SECRET`、`PASSWORD`、`PASSWD`、`CREDENTIAL`、`PRIVATE` 或 `AUTH` 任一子串的变量判定为敏感。该敏感子串清单为可扩展的最小集、非穷尽。被判定为敏感的变量 MUST NOT 传入沙箱容器。

#### Scenario: 含敏感子串的变量被识别
- **WHEN** 判定名称为 `API_TOKEN`、`db_secret` 或 `MyKey`
- **THEN** 均被判定为敏感

#### Scenario: PASSWORD 被识别为敏感
- **WHEN** 判定名称为 `DB_PASSWORD`、`MYSQL_PASSWD`、`AWS_CREDENTIAL`、`PRIVATE_PEM` 或 `BASIC_AUTH`
- **THEN** 均被判定为敏感

#### Scenario: 无害变量不被误判
- **WHEN** 判定名称为 `PATH`、`HOME`、`LANG`
- **THEN** 均不被判定为敏感

### Requirement: 仅按变量名过滤，不扫描变量值

过滤规则 SHALL 仅作用于环境变量的**名称**，MUST NOT 扫描或解析变量的**值**。值内嵌密钥（如连接串中的口令）不在本能力的检测范围，属本 change 的非目标。

#### Scenario: 仅名过滤、值不扫描
- **WHEN** 注入一个名称不敏感但值内嵌密钥的变量（如 `DATABASE_URL=postgres://user:pass@host`）
- **THEN** 该变量因名称不敏感而通过过滤、进入容器；其值中内嵌的口令不被检测、不触发剔除

### Requirement: 三层来源统一过滤后注入

沙箱环境变量 SHALL 由三层来源合并：宿主机进程环境、agent 配置注入的变量、运行时显式传入的变量。合并后的全部变量 MUST 统一应用同一名称过滤规则，敏感变量一律剔除；通过过滤的变量 SHALL 经 `docker run` 的环境注入参数传入容器。宿主机进程环境默认 MUST NOT 整体透传。

agent 配置注入的变量 SHALL 仅来自 agent 定义的 `features.sandbox_env` 预声明。运行时/AI 在 `run_code` 调用时提供的 env MUST NOT 被接受为注入来源（限制攻击面）。

#### Scenario: 任一来源的敏感变量都被剔除
- **WHEN** agent 配置或运行时来源中显式写入名称含 `KEY`/`TOKEN`/`SECRET`/`PASSWORD` 的变量
- **THEN** 该变量不出现在传入容器的环境中

#### Scenario: 通过过滤的变量被注入
- **WHEN** 注入一个名称不敏感的变量（如 `DATA_DIR`）
- **THEN** 该变量经环境注入参数进入容器，可在容器内读取

#### Scenario: 注入来源仅限 agent 预声明
- **WHEN** AI 在 `run_code` 调用时尝试提供一组 env
- **THEN** 该 env 不被接受为注入来源；进入容器的变量仅来自 agent `features.sandbox_env` 预声明

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

