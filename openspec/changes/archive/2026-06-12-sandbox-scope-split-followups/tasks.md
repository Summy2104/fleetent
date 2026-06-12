## 1. multi_user 显式配置信号接入

- [x] 1.1 写 unit 测试(red):`SandboxSettings.multi_user` 默认 `False`、可解析 `true`、`extra="forbid"` 下未知字段仍拒;platform sandbox 配置同字段(若适用)
- [x] 1.2 实现(green):`agent_config.SandboxSettings` 新增 `multi_user: bool = False`
- [x] 1.3 写 unit 测试(red):`init_sandbox_manager` 以 `resolved.sandbox.multi_user` 构造 `SandboxManager(multi_user=...)`(monkeypatch 验证传入值)
- [x] 1.4 实现(green):`builtin_tools.init_sandbox_manager` 读 `resolved.sandbox.multi_user` 传入 manager
- [x] 1.5 写 integration 测试(red):`multi_user=True` + 配 `workspace_scope: agent` → 启动期生效 scope 纠正为 `session` 并告警;`multi_user=False` 时 `agent` 保留
- [x] 1.6 跑通 1.5,确认护栏端到端生效

## 2. agent 加固档收紧为与 session 同档

- [x] 2.1 写 unit 测试(red):`build_resources_by_scope` 的 agent 档 `read_only=True`、`run_as_user` 非 None(非 root)、`cap_add` 为空(不补 caps);非加固字段(memory/cpus/network)仍可经 `sandbox.agent_scope` 覆盖
- [x] 2.2 实现(green):去掉 agent 档的 `read_only=False`/`cap_add=_AGENT_CAP_ADD`/`run_as_user=None` 三处放松,继承 base;清理"writable rootfs for docker commit"陈旧注释;`_AGENT_CAP_ADD` 若无引用则删除
- [x] 2.3 更新既有 hardening 测试(red→green):断言 agent 档补 caps/root 的既有用例(test_sandbox_config / test_sandbox_docker_backend / test_sandbox_container_hardening 等)按新档更新——agent 档现 `--cap-drop ALL` 不补、`--user 65534:65534`、`--read-only`
- [x] 2.4 写 integration 测试(red):agent 档容器以非 root + 只读 rootfs 创建,且 agent 向 `/workspace` 写文件成功(只读 rootfs 不阻挡可写 bind mount)
- [x] 2.5 跑通 2.4,确认声明式 deps 镜像在只读运行期仍可用(deps 在 build 期烤入)

## 3. 边界与收尾

- [x] 3.1 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` EXIT 0(integrations/sandbox/tools/agent_config 无 import platform);冒烟:无 platform 下 `fleetent agent run` 加载、默认 multi_user=False/session
- [x] 3.2 `check_test_layers.py` + ruff(仅改动文件) + `mypy src` 无新增
- [x] 3.3 `make test-pr` 无新增失败 + sandbox 全量 integration 无回归(重点回归 #1-#5)
- [x] 3.4 `openspec validate sandbox-scope-split-followups --strict` 通过
