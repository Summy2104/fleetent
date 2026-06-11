## Context

事故 transcript（session `…:1781154552.587189`）逐步还原：

1. `bash_exec` 调 skill 脚本 → `$SKILLS_DIR` 在容器内为空，路径解析为 `/common-office-reader/...` 不存在（次要缺陷，本 change 不修）
2. `bash_exec` `find / -name …` → 30s 超时；容器（内存受限 tier）随之死亡——确切死因（OOM-kill / docker 回收）无法事后取证，但修复不依赖具体死因
3. `run_code` → `Error response from daemon: No such container: 0d22badd…`——`acquire` 注册表命中即返回（"trust it (no inspect)"），把死容器 id 给了执行层
4. `read_file uploads/…` / `/workspace` 全部「路径不存在」——`_parse_probe` 只看 stdout，死容器 exec 的空输出被解析为 `missing`
5. 模型基于"文件不存在"的假信号建议用户重传

对照：同会话 40 秒前容器存活时 `read_file uploads/bug-8053-verify.txt` 成功；xlsx 文件全程存在于 host 工作区。

## Goals / Non-Goals

**Goals:**
- 容器死亡（任何原因）不再使会话的沙箱类工具永久瘫痪——下一次调用自动重建并继续
- 基础设施失败如实呈现给模型（明确的沙箱错误），不得伪装成「路径不存在/无匹配」
- 自愈对 session / agent 两种 scope 一致生效

**Non-Goals:**
- 不修 `$SKILLS_DIR` 注入缺失（独立能力域：sandbox-secret-injection / skill 挂载，记录为后续 change）
- 不改容器死因侧（资源上限、`find /` 类命令的防护已有 exec-timeout / resource-limits spec 管辖）
- 不做容器状态持久化/跨进程恢复（重启进程注册表本就重建）

## Decisions

**D1：acquire 复用前存活校验（verify-on-reuse）。**
注册表命中后调后端存活检查（docker inspect 级，毫秒级开销，每次工具调用一次）；不存活 → 删除注册项，落回既有"按名收养或新建"路径。否决的备选：「注册表命中直接信任 + 仅靠 exec 失败修复」——会让每次故障都先烧掉一次用户可见的失败回合。

**D2：exec 容器失踪自愈（deregister + retry once）。**
D1 后仍存在「校验通过 → 执行前死亡」的竞态窗口；执行层识别 container-missing 类错误时注销注册项并重试一次（重新 acquire → 新容器）。仅重试一次：连续两次失踪说明 docker 本身异常，如实报错。

**D3：文件工具错误分类。**
`_ContainerBackend` 各操作先判 exec 结果：container-missing/daemon 错误 → 抛 `_BackendError`（文案指明沙箱不可用），不进入 stdout 解析；`probe` 的 `missing` 只能来自容器内命令的真实判定。否决的备选：「probe 失败一律按 missing」——正是本次事故把模型引向错误结论的根源。

**D4：workspace host 挂载是自愈的前提，明确为既有保证。**
文件存活与容器生命周期解耦（`workspace_host_path` host 目录 bind-mount），换容器即恢复——本 change 不改它，但 spec 场景中显式断言"重建后此前写入的文件可见"。

## Risks / Trade-offs

- [每次 acquire 复用多一次 inspect] → 毫秒级、本地 daemon 调用；相比一次用户可见失败可忽略
- [container-missing 错误指纹依赖后端文案] → 识别放在 backend 层（按各自错误类型/文案），manager 只消费分类结果；microsandbox 后端同口径实现
- [重试一次仍失败] → 如实返回基础设施错误，模型可向用户解释"沙箱暂不可用"而非"文件丢失"——错误语义本身就是修复的一部分
