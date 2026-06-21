## Why

目前 agent 的人格与行为只能由 `agent.yaml` 的 `system_prompt` 静态定义,部署后终端用户无法在对话中按需补充长期偏好(如「永远用中文简短回答」)。`memory/` 模块虽能提取隐式语义记忆,但它不是用户显式、可读、可编辑的指令。缺少一个「用户显式可控的长期指令」入口。

## What Changes

- 新增 **per-agent 的 `user.md` 用户指令文件**,位于 `agents/<agent_id>/user.md`,与 `agent.yaml` 同目录。内容作为 stable prefix 的一部分注入 system prompt(拼在 `system_prompt` 之后、`<available_skills>` catalog 之前),独立于 `memory/` 的隐式语义记忆,两者并存各管一摊。
- 新增 **`/user` 命令命名空间**,让用户在对话中显式管理 `user.md`:
  - `/user` —— 回显当前 `user.md` 内容(为空则提示尚未设置)
  - `/user <内容>` —— 追加一条指令(原子写,下一轮重新组装时生效)
  - `/user clear` —— 清空 `user.md`
  - 不提供「删除单条」(IM 无行号交互);追加 + 清空即够用。
- `/user` 命令在 **CLI / Slack / Telegram / TUI 各入口**均可用,经一个共享的命令处理函数统一实现,各入口仅做命令面接线。
- `user.md` 设字符截断上限,避免拖垮可缓存前缀。
- `user.md` 独立于 `agent.yaml` 读取(不经 `AgentConfigIndex` 缓存),写入后下一轮直接重读文件即生效。

## Capabilities

### New Capabilities
- `user-instructions`: per-agent 用户指令文件(`user.md`)的存储、加载与截断、注入 system prompt 的位置,以及 `/user` 命令在各入口的查看/追加/清空行为。

### Modified Capabilities
<!-- 无:user.md 注入到既有 stable prefix 之内,不改变 prompt-cache-optimization 的「稳定前缀在前」要求,也不改变 memory-layer 的隐式记忆要求。 -->

## Impact

- **owning package**:`runtime`(prompt 组装与共享命令处理)、新增轻量加载/命令模块(暂定 `runtime/user_instructions.py`)。
- **public API surface**:`user.md` 的加载函数(读取 + 截断)、`/user` 命令的处理函数(`handle_user_command(agent_id, text) -> str | None`)。
- **owned tables**:无(纯文件,落 agent 侧 `agents/<id>/user.md`)。
- **config namespace**:无(不新增 `agent.yaml` 配置项;字符上限用硬编码常量)。
- **cross-module dependencies**:`paths.py`(定位 agent 目录)、`runtime/loop.py`(`_assemble_prompt` 组装链路);`im_gateway`(Slack/Telegram 命令面)、`tui`(`commands.py` + `dispatch.py`)、CLI 入口接线。
- **migration / shim plan**:无(纯新增能力,不移动现有模块)。
- **解耦约束**:`user.md` 是纯 agent 侧产物,严禁触碰 platform 表,符合 Agent/Platform 单向依赖契约。
