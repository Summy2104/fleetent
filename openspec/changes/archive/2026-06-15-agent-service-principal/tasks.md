# Tasks — agent-service-principal（P4）

> 依赖 P0 已 archive。TDD：测试任务前置。触及 DB 的测试放 integration。

## 1. service-principal 铸造

- [x] 1.1 写测试（integration）：为 agent 幂等 get-or-create service-principal（id=`agent:<id>`, role=service），重复调用返回同一行、不重复建。
- [x] 1.2 写测试（integration）：service principal 不可经 set_role 提权；不被签发人类会话 / INBOUND key。
- [x] 1.3 实现：身份层 get-or-create service-principal helper（无 schema 迁移）。运行 1.1–1.2 见绿。

## 2. run_as 凭证解析

- [x] 2.1 写测试（integration）：run_as=user → 以调用用户解析；run_as=agent → 以 service-principal 解析；两 principal 凭证互不串用；agent principal 无凭证 → NeedsConsent 短路。
- [x] 2.2 写测试（unit）：run_as 不出现在 `get_schemas()` 的 LLM 可见 schema。
- [x] 2.3 实现：dispatch 凭证解析读 grant.run_as 选 principal。运行 2.1–2.2 见绿。

## 3. 生命周期清理

- [x] 3.1 写测试（integration）：delete_agent 后 best-effort 清理该 agent service-principal 的 external_credentials（舱壁化，不改退出码）。
- [x] 3.2 实现：delete_agent 清理钩子（best-effort）。运行 3.1 见绿。

## 4. 收尾

- [x] 4.1 `make test-pr` 全绿；`scripts/check_module_boundaries.py` 通过；`uv run pytest tests/integration -q` 无新增失败。
