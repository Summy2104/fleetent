## ADDED Requirements

### Requirement: 死容器自愈（复用前校验 + 执行失踪恢复）

`SandboxManager.acquire` 在注册表命中时 SHALL 先校验该容器存活；容器已不存在/不可用时 MUST 丢弃该注册项并按"收养或新建"路径取得新容器，MUST NOT 把死容器 id 交给执行层。执行层命中容器失踪类错误（如 `No such container`）时 SHALL 注销对应注册项并重试一次（重新 acquire 新容器）；重试仍失败 MUST 返回明确的沙箱基础设施错误。workspace 为 host 挂载，容器重建后此前写入 workspace 的文件 MUST 对新容器可见。

#### Scenario: 复用命中死容器时自动重建
- **WHEN** 注册表中登记的容器已被外部销毁（OOM/手工 rm/daemon 重启），同会话再次请求沙箱执行
- **THEN** acquire 丢弃失效注册项并创建新容器，本次调用在新容器中正常执行

#### Scenario: 执行时容器失踪自愈
- **WHEN** acquire 校验通过后、命令执行前容器死亡，执行返回容器失踪类错误
- **THEN** 该注册项被注销，本次调用经一次重试在新容器中完成；连续失败则返回明确的沙箱不可用错误

#### Scenario: 容器重建不丢工作区文件
- **WHEN** 容器死亡前已有文件写入 workspace（如 IM 入站附件），容器经自愈重建
- **THEN** 该文件在新容器的 `/workspace` 下仍可读取

## MODIFIED Requirements

### Requirement: session scope 会话内复用、会话结束销毁

在 `session` scope 下，同一会话内多次请求沙箱执行 SHALL 复用同一**存活**容器（已存在且存活则不新建；已死则按「死容器自愈」requirement 重建）；会话结束时该容器 MUST 被销毁。

#### Scenario: 同一会话内复用容器
- **WHEN** 同一会话内第二次请求沙箱执行且首次创建的容器仍存活
- **THEN** 复用首次创建的同一容器，不新建容器

#### Scenario: 会话结束销毁容器
- **WHEN** 会话结束并触发释放
- **THEN** 该会话的 `session` scope 容器被销毁并从登记中移除，不影响其它会话的容器
