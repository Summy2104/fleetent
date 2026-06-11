# Tasks

> 项目 TDD 硬门:每个实现 task 前必须有对应测试 task(先写测试见红 → 再实现见绿)。
> 测试分层:unit = mock,不碰真实 DB/FastAPI;涉及真实容器/挂载/SQLite/多模块协作走 integration。不向 tests/ 根目录新增 test_*.py。

## 1. skills 挂载进容器(sandbox-skill-mount)

- [ ] 1.1 写 unit 测试(red):`tests/unit/integrations/sandbox/test_docker_skill_mount_flags.py` —— `DockerBackend._skill_mount_flags(skill_mount)` 在 read_only 默认时产出 `-v <src>:/workspace/skills:ro`,read_only=false 去掉 `:ro`;None 不产出挂载;`SKILLS_DIR=/workspace/skills` 进入 env flags 且与 `sandbox_env` 并存。
- [ ] 1.2 实现(green):`backends/docker.py` 增 `_skill_mount_flags` 并接入 `create_workspace`;`SKILLS_DIR` 经 `_env_flags` 注入(平台注入优先于 sandbox_env 同名)。`backend.py` 的 `create_workspace` 抽象签名追加可选 `skill_mount`(默认 None)。
- [ ] 1.3 写 unit 测试(red):`tests/unit/integrations/sandbox/test_config_hash_skill_mount.py` —— skills 挂载源/(ro|rw)模式纳入 `config_hash`:源或模式不同 → hash 不同;相同 → hash 相同。
- [ ] 1.4 实现(green):`hardening.config_hash` 把 skills 挂载源 + 模式纳入摘要(扩入参或经 manager 拼入),保持既有 workspace/env 摘要不变。
- [ ] 1.5 写 unit 测试(red):`tests/unit/integrations/sandbox/test_skill_mount_blocked.py` —— skills 宿主源落在 `is_blocked_mount` 敏感根下时,解析/创建路径拒绝并抛明确错误,不创建带该挂载的容器。
- [ ] 1.6 实现(green):`manager.acquire`(或其调用的 skills 源解析辅助)对 skills 源先过 `is_blocked_mount`,命中即拒。
- [ ] 1.7 写 integration 测试(red):`tests/integration/integrations/sandbox/test_skill_mount_container.py` —— Docker 后端下创建容器,断言 `/workspace/skills` 已挂入、容器内可读、ro 时写被拒;容器内 `echo $SKILLS_DIR` == `/workspace/skills`;挂载源变更触发 config_hash 失配重建。(无 docker 环境用现有 sandbox integration 跳过约定。)
- [ ] 1.8 实现(green):打通 `manager.acquire` → `create_workspace` 的 skills 挂载端到端,使 integration 绿。

## 2. 双物理根:单一有效根 + builtin 物化(sandbox-skill-mount / sandbox-workspace-root)

- [ ] 2.1 写 unit 测试(red):`tests/unit/skills/test_effective_skill_root.py` —— 有效根解析返回用户 skills 根(`FLEETENT_SKILLS_DIR`/默认),而非包内 `BUILTIN_SKILLS_DIR`;builtin 物化为幂等、不覆盖用户同名 skill(沿用「用户覆盖 builtin」语义)。
- [ ] 2.2 实现(green):新增有效根解析 + builtin 物化辅助(`skills/registry.py` 或 sandbox skills 源解析处);物化幂等、失败 log 不静默。
- [ ] 2.3 写 integration 测试(red):`tests/integration/skills/test_builtin_materialized_in_workspace.py` —— 一个包内 builtin skill(带同目录资源)经物化后,容器内 `$SKILLS_DIR/<name>/<资源>` 可读。
- [ ] 2.4 实现(green):在挂载/创建前按需物化将被挂载的有效根,使 integration 绿。

## 3. 单根 /workspace + 相对路径不变式(sandbox-workspace-root)

- [ ] 3.1 写 unit 测试(red):`tests/unit/tools/test_ws_relative_resolution.py` —— 相对路径经 `resolve_ws_path` 落 `/workspace` 下、越界绝对路径被拒;`resolve_host_path(root, rel)` 对同一相对路径落 root 下同一物理位置(纯解析,mock/tmp,不起容器)。
- [ ] 3.2 实现(green):确认 generated/uploads 解析复用 `resolve_ws_path`/`resolve_host_path`(若有新增解析点则统一收口到这两函数),不另起路径逻辑。
- [ ] 3.3 写 integration 测试(red):`tests/integration/tools/test_relative_path_invariant.py` —— 容器模式写某相对路径、降级(host fence)模式按同一相对路径读到同一文件;反向亦然(相对路径不变式)。
- [ ] 3.4 实现(green):保证容器/降级共用 `workspace_host_path` 单一目录解析点,使不变式 integration 绿。

## 4. generate_image / uploads 迁入 /workspace(image-generation-tool / vision-as-tool)

- [ ] 4.1 写 unit 测试(red):`tests/unit/tools/test_generate_image_workspace_ref.py` —— `generate_image` 落盘到 per-scope workspace `generated/`,返回相对引用 `generated/<name>.png`,不含 base64、不含宿主绝对路径;trace 不含 base64。(mock 后端落盘 + tmp workspace。)
- [ ] 4.2 实现(green):`builtin_tools.generate_image` / `_save_image` 改为经 tool_context 定位 per-scope workspace 落 `generated/`,返回相对引用。
- [ ] 4.3 写 unit 测试(red):`tests/unit/tools/test_analyze_image_workspace_readback.py` —— 入站图片落 per-session workspace `uploads/`,`analyze_image` 经 workspace 解析回读有效引用成功;无效引用返回错误文本不抛异常;历史绝对引用兜底可读。
- [ ] 4.4 实现(green):`_save_upload`/`_read_upload`/`UPLOADS_DIR` 改为 workspace 解析(+历史绝对兜底);`im_gateway/normalizer` 入站图片落盘对齐 `_save_file_to_workspace`。
- [ ] 4.5 写 integration 测试(red):`tests/integration/im_gateway/test_inbound_image_workspace.py` —— 含图入站消息:图片落 per-session workspace `uploads/`,主上下文携带相对引用、不含 base64/绝对路径,analyze_image 在该 workspace 回读成功。
- [ ] 4.6 实现(green):打通归一化链入站图片 → workspace 落盘 → analyze_image 回读,使 integration 绿。

## 5. 执行面收敛(sandbox-exec-face)

- [ ] 5.1 写 unit 测试(red):`tests/unit/tools/test_exec_face_convergence.py` —— 断言注册工具集中「容器内执行」唯一为 `run_code`(不存在 `sandbox_exec` 或任何第二个完成容器获取+容器内执行的工具);并断言 `run_code` 的 `risk_level` 为 `medium`(免审批边界由 action-gate 决定、无更低 risk 的等价执行旁路)。
- [ ] 5.2 实现(green):确立 run_code 为容器内唯一执行面——**不新增 sandbox_exec**;`<available_skills>`/`read_skill` 指令层确保模型经 run_code 内 subprocess 运行 skill 脚本(脚本路径以 `$SKILLS_DIR` 为根)。

## 6. 指令层:bash_exec 首行 + read_skill/目录渲染指引(builtin-shell-tool / skill-read-on-demand)

- [ ] 6.1 写 unit 测试(red):`tests/unit/tools/test_bash_exec_docstring_first_line.py` —— 经 `schema_builder` 取 `bash_exec` 的 description(docstring 首行),断言首行表明「宿主执行、看不到 /workspace 与会话文件、会话文件用 run_code」。
- [ ] 6.2 实现(green):改 `shell_tool.bash_exec` docstring 首行为该世界观(确保 schema_builder 取到的首行命中)。
- [ ] 6.3 写 unit 测试(red):`tests/unit/skills/test_catalog_and_read_skill_guidance.py` —— `available_skills_prompt` 的指令段含「脚本经 run_code 运行、路径以 `$SKILLS_DIR` 为根」固定文本且不破坏稳定前缀字节稳定性(同一 skill 集两次渲染逐字节一致);`read_skill` 返回附带同一指引;`location` 渲染以 `$SKILLS_DIR` 为根而非宿主绝对路径。
- [ ] 6.4 实现(green):`registry.available_skills_prompt` 指令段 + `location` 渲染调整;`builtin_tools.read_skill` 返回拼接指引。

## 7. 配置:sandbox.skill_mount 命名空间(sandbox-skill-mount)

- [ ] 7.1 写 unit 测试(red):`tests/unit/test_sandbox_skill_mount_config.py` —— `SandboxSettings` 新增 `skill_mount`(`enabled` 默认 true、`read_only` 默认 true、可选 `source`);`extra="forbid"` 下合法字段通过、未知字段拒;platform `sandbox.*` 同字段解析。
- [ ] 7.2 实现(green):`agent_config.SandboxSettings`(及 platform sandbox 配置)新增 `skill_mount` 子模型;factory/manager 读取该配置决定挂载与 ro/rw。

## 8. 收尾(change / PR 门禁)

- [ ] 8.1 跨包 internal import 护栏:`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`,确认 `tools`/`integrations.sandbox`/`skills`/`im_gateway` 无 `import fleetent.platform.*`、无跨包 internal import。
- [ ] 8.2 无-platform 冒烟:在 platform 表不存在的环境下 `uv run fleetent agent run`(或等价 CLI 对话冒烟),验证含 skill 脚本(经 run_code,`$SKILLS_DIR` 可达)与 generate_image(相对引用)在 standalone agent 跑通。
- [ ] 8.3 改动文件层边界:`uv run python scripts/check_test_layers.py` 通过(无新增越界 unit)。
- [ ] 8.4 `uv run ruff format src tests` + `uv run ruff check src tests`(本分支 changed 文件)无问题。
- [ ] 8.5 `uv run mypy src` 对改动模块通过(公开 API 完整类型注解)。
- [ ] 8.6 `make test-pr` 全绿(unit + 层边界 + 改动文件 ruff);`uv run pytest tests/integration -q` 对照 main 基线无新增失败。
- [ ] 8.7 `openspec validate "sandbox-execution-world" --strict` 通过。
- [ ] 8.8 全部 checkbox 为 [x] 后,在功能分支 `opsx:archive` 并同步 specs(archive 表示实现完成,不代表上线 main)。
