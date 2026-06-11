## Why

真机事故（2026-06-11，my-bot Slack DM）：用户上传 xlsx，文件已正确落盘到 host 工作区 `uploads/`，但 agent 回复"所有位置都找不到该文件"。完整 transcript 还原：会话的沙箱容器在一次 `find /` 超时后死亡（OOM/回收），此后 ① `SandboxManager.acquire` 复用注册表中的死容器 id（代码注释自述 "trust it (no inspect)"），`run_code` 报 `No such container`；② 文件工具 `_ContainerBackend.probe` 不检查 exec 退出码，死容器的空 stdout 被解析为 `missing`，`read_file /workspace` 都谎报「路径不存在」，把基础设施故障伪装成文件丢失，误导模型让用户重传。同会话 40 秒前（容器存活时）同路径 txt 读取成功，证明落盘与挂载本身无误。host 挂载使文件天然幸存于容器死亡——重建容器即可完全恢复，当前实现却让会话永久瘫痪。

## What Changes

- **acquire 复用前存活校验**：注册表命中后校验容器存活；已死 → 丢弃注册项，落回"重新收养或新建"路径（对 session/agent 两种 scope 一致）。workspace 为 host 挂载，新容器看到同一目录，文件零丢失
- **exec 遇容器失踪自愈**：执行命中 `No such container` 类错误时注销该注册项并重试一次（覆盖"校验后、执行前容器死亡"的竞态窗口）；重试仍失败则返回明确的基础设施错误
- **文件工具错误诚实化**：`_ContainerBackend` 的 probe/list/search 必须区分「exec 基础设施失败」与「路径不存在/无匹配」——exec 非正常退出（容器失踪、daemon 错误）时返回明确的沙箱错误文案，MUST NOT 谎报为 missing/无匹配
- 不在本 change 内（记录为后续）：`$SKILLS_DIR` 未注入沙箱容器导致 skill 脚本在容器内不可用（事故中的次要环节，独立能力域）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `sandbox-lifecycle`: 新增「死容器自愈」requirement（复用前存活校验 + exec 失踪注销重试）；「session scope 会话内复用」requirement 的复用语义限定为"存活容器"
- `file-tools-sandbox-execution`: 新增「基础设施错误不得谎报为路径状态」requirement

## Impact

- 受影响代码：`integrations/sandbox/manager.py`（acquire 存活校验 + exec 自愈）、`tools/file_tools.py`（ContainerBackend 错误分类）
- 受影响测试：`tests/unit`/`tests/integration` 沙箱 manager 与 file_tools 用例（mock backend）
- 无 schema / 配置 / 依赖变更；agent 侧自包含
- 关联 Jira：AAA-8053 验证期间发现的衍生缺陷（文件读取链路可靠性）
