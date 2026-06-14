# Tasks — unified-file-exchange

> 每个实现任务严格 TDD：先写测试见红，再实现见绿。测试任务排在对应实现任务之前。
> 分层：纯逻辑（命名空间解析/风险真值表/前缀改写）= unit；涉及真实 sqlite/文件系统/容器 = integration（tmp_path 隔离）。

> **⚠️ WIP（2026-06-12 自动执行）**：本 change 体量最大且深集成层（MCP 咽喉 session_id 穿线、沙箱 Docker 挂载）在无人值守夜跑中风险高，已完成「foundation + MCP 约定注入 + callable risk」的自洽低风险部分（§1 全部、§2.1+2.2 核心注入层、§5 全部），其余 §2.3-2.6/§3/§4/§6/§7 留给有人值守续做。**未达全勾选，不合并 main**。原因与边界详见 `docs/file-exchange-series-apply-decisions.md` ③ 节「范围与进度声明」。
> §2.2 备注：约定注入纯函数（`_subprocess_env`/`_convention_env`/`_convention_cwd`）已实现+单测，但 stdio 启动处 cwd 接线未做（需 transport 层 agent_home 解析），故 2.2 暂不勾选。
> **⚠️ 架构修正（2026-06-13，D0）**：归属轴由「裸 session_id 独立轴」改为「继承 workspace scope key」。已合入 main 的 §1.5/1.6 休眠代码（`resolve(path, session_id)`/`list_by_session`/`_find_by_path` 按路径取最新）按 D0 重做——见新增 §0。续做必须先完成 §0，§1.5/1.6 的产物被 §0 取代（休眠脚手架，零现网风险）。

## 0. 归属轴重构（D0，续做前置，必须先做）

- [x] 0.1 测试：单一 key 派生权威 `workspace_scope_key(scope, session_id, agent_name)`（SESSION→session_id / AGENT→agent_name），且与 `SandboxManager.workspace_host_path` 同源（同输入同 key）——unit，先红
- [x] 0.2 实现：抽 `workspace_scope_key`（sandbox 与 exchange 共用，杜绝两处各自推导 scope）——绿
- [x] 0.3 测试：迁移 v33 给 `artifacts` 追加 `scope_key` 列（migrate-on-open、user_version 递增、既有数据无损）——integration，先红
- [x] 0.4 实现：`agent_state_migrations.py` append v33——绿
- [x] 0.5 测试：`artifact_exchange` 改为 scope_key 轴（`register(...scope_key, session_id, user_id)` 记审计列；`resolve(path, scope_key, *, approved)` 按 `(server_id, rel_path, scope_key)` 命中；同 `(server_id, rel_path)` 跨 scope 各自命中不串味、不误拒；`list_by_scope`；`approved=True` 跨 scope 豁免并记审计）——unit/integration，先红
- [x] 0.6 实现：重做 `artifact_exchange` 签名与查找（`_find_by_path`→按 scope_key 过滤；`resolve`/`register`/`list_*` 改 scope_key 轴）——绿

## 1. 台账与命名空间核心（artifact_exchange.py）

- [x] 1.1 测试：agent_state.db 嵌入式迁移新增 `artifacts` 表（migrate-on-open、user_version 递增、旧数据无损）——integration，先红
- [x] 1.2 实现：`agent_state_migrations.py` 新版本号 + `artifact_exchange.py` store 骨架（`set_state_db` 注入、named parameters、register/get/list_by_session）——绿
- [x] 1.3 测试：有效文件根解析（未配置→约定根 `<agent_home>/exchange/<id>/data`；显式 XDG→原地收编；`file_root` 显式声明优先）——unit，先红
- [x] 1.4 实现：`effective_root(server_config)` 解析与注册期映射表——绿
- [x] 1.5 测试：`/exchange/<server_id>/<rel>` 命名空间解析真值表（合法解析/两根外拒绝/`..` 越界拒绝/未登记拒绝/归属不符拒绝/审批授权豁免/文件已删报"工件已不存在"）——unit，先红
- [x] 1.6 实现：`resolve(path, session_id, *, approved=False)` 归属校验解析——绿

## 2. MCP 注入与登记（integrations/mcp）

- [x] 2.1 测试：`_subprocess_env` 合并序 白名单<约定注入<显式 env；约定注入 XDG 三件套+cwd 指向分区树；`file_isolation: off` 跳过注入——unit，先红
- [x] 2.2 实现：约定注入层 + `McpServerConfig` 新增 `file_root`/`file_isolation` 字段 + stdio 启动 cwd 设置——绿
- [x] 2.3 测试：结果路径确定性改写（有效根内 host 绝对路径→`/exchange` 规范路径并登记，归因到当前 run 的 scope_key；根外路径不动）——unit，先红
- [x] 2.4 实现：咽喉层结果改写 + 登记挂接（scope_key 经 dispatch→咽喉穿线，审计列记 session_id/user_id）——绿
- [x] 2.5 测试：调用窗口 diff 兜底登记（新文件登记归因到当前 run scope_key、点文件/`*.tmp` 跳过、per-server 锁下并发归因不错乱、diff 异常不影响结果）——integration，先红
- [x] 2.6 实现：快照 diff + per-server `asyncio.Lock` 包裹调用窗口——绿

## 3. fence 双根与 file 工具

- [x] 3.1 测试：file 工具 path 解析双根（相对→/workspace 不变；`/exchange` 本 scope 放行/跨 scope 拒绝/同路径跨 scope 不串味/未登记拒绝；其余越界拒绝语义不变）——integration，先红
- [x] 3.2 实现：`file_sandbox_io` 围栏扩双根，read/write/edit/search 接入 `artifact_exchange.resolve`——绿

## 4. 沙箱归属视图

- [x] 4.1 测试：视图目录维护（`.views/<scope_key>/` 按 scope_key 分组；登记补硬链接保持 `<server_id>/<rel>` 结构、重登记刷新链接、容器创建前确保目录存在、跨文件系统降级标记+日志）——integration，先红
- [x] 4.2 实现：`artifact_exchange` 视图管理（view_dir/链接增补/刷新）——绿
- [x] 4.3 测试：`BackendCapabilities` 新增 `exchange_mount`（Docker=true）；容器创建携带视图 ro 挂载到 `/exchange`；同 scope_key 复用同视图；无能力后端不传挂载+降级日志——integration，先红
- [x] 4.4 实现：capability 位 + Docker 后端第二卷 ro 挂载 + manager 接线——绿
- [x] 4.5 测试：容器内 `/exchange` 只读 + 挂载后新增链接即时可见——以 **mock docker run 命令组装等价覆盖**（断言 `-v 视图:/exchange:ro` 选项装配 + 复用同视图）；真机断言加 `@pytest.mark.skipif`（无 docker 跳过），先红
- [x] 4.6 实现：补齐挂载选项装配与文档注释（mock 覆盖通过）——绿
- [ ] 4.7 测试：无 `exchange_mount` 后端的 staging 降级（exec 前扫描代码 `/exchange/…` 引用、归属校验通过者复制进容器、记录降级日志）——integration，先红
- [ ] 4.8 实现：staging 降级路径——绿

## 5. 权限门参数化风险

- [x] 5.1 测试：registry `risk_level` 接受 callable（调用期求值驱动同等 gate 行为；返回 low 直跑/medium 走审批；callable 抛异常 fail-closed 按 medium）——unit（gate 用 `PermissionGate(medium_timeout=0.1)`），先红
- [x] 5.2 实现：`tools/registry.py` + `governance/permission_gate.py`/loop 接入 callable 求值——绿

## 6. send_file 升级语义

- [ ] 6.1 测试：send_file 风险函数真值表（四条件全满足→low，含单人 agent scope 本 scope 文件 DM 直发；频道/跨 scope 工件→medium；`session_context=None` 仍 fail-closed 不升级）——unit，先红
- [ ] 6.2 实现：send_file 接 `/exchange` 路径 + callable risk + 升级审批路径（批准后 `approved=True` 解析发送），替换原 fail-closed 拒绝文案——绿
- [ ] 6.3 测试：免审批直发与升级审批端到端（DM 本会话工件直发回显收件人；频道场景批准后发出、拒绝后不发）——integration，先红
- [ ] 6.4 实现：修复联动（EGRESS 提示文案更新指向新语义）——绿

## 7. send_im_message 附件能力

- [ ] 7.1 测试：`files` 参数（批准后文本+附件投递；跨会话工件批准即授权；无效条目逐文件降级不中断；任意参数组合恒过 medium gate；不带 files 行为与现状一致）——integration，先红
- [ ] 7.2 实现：`files` 参数 + 共享投递内核（与 send_file 同一解析/发送核）——绿

## 8. 收尾

- [ ] 8.1 `uv run pytest tests/unit -q` 与 `uv run pytest tests/integration -q`（不带 -x，对照 main 基线无新增失败）
- [ ] 8.2 `make test-pr` 全绿；`uv run mypy src` 无新增错误
- [ ] 8.3 文档：AGENTS.md Gotchas 补 exchange 条目（命名空间/归属/约定注入/逃生门）；agent.yaml.example 注释 `file_root`/`file_isolation`
- [ ] 8.4 验证：my-bot 事故场景**等价持久层/装配验证**（真实 sqlite artifacts 登记→resolve→send_file 解析链路 + mock docker/MCP/LLM 重建；真机断言 `skipif` 跳过）；真机重放留用户环境补跑，决策文档记入「真机待补」
- [ ] 8.5 收口：全部 checkbox `[x]` 后 `opsx:archive` + `opsx:sync`（功能分支归档+同步 specs），最终 bb-pr 合 main
